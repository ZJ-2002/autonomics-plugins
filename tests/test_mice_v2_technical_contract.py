import ast
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import unittest
from unittest.mock import patch
from tests.conditional_v2_baseline import published_bytes


ROOT = Path(__file__).resolve().parents[1]
FAMILY = ROOT / "research-adapters/cachexia-mice"
TYPED = ROOT / "research-adapters/cachexia-mice-typed-values"
BASE = "f3715049facecc04abf8778ac71e01abb5b4b0e4"


class MiceV2TechnicalContractTests(unittest.TestCase):
    def run_r(self, body):
        self.assertIsNotNone(shutil.which("Rscript"), "Rscript is required; missing execution is not a pass")
        with tempfile.TemporaryDirectory(prefix="mice-v2-contract-") as directory:
            script = Path(directory) / "check.R"
            script.write_text(
                "files <- " + "c(" + ",".join(json.dumps(str(FAMILY / "scripts" / name)) for name in ("mice.R", "bind_contract.R")) + ")\n"
                "environments <- lapply(files,function(filename) {\n"
                " environment <- new.env(parent=globalenv())\n"
                " for (definition in parse(filename)) if (is.call(definition)&&identical(definition[[1L]],as.name('<-'))&&is.symbol(definition[[2L]])&&as.character(definition[[2L]]) %in% c('require_value','technical_contract_profile','technical_parent_role','bind_json_hash','receipt','lexical_table')) eval(definition,environment)\n"
                " environment\n})\n"
                "stopifnot(identical(body(environments[[1]]$technical_contract_profile),body(environments[[2]]$technical_contract_profile)),identical(body(environments[[1]]$technical_parent_role),body(environments[[2]]$technical_parent_role)))\n"
                "request <- function(version=2L,role='EMPIRICAL_TECHNICAL_INPUT')list(schema_version=version,scope='TECHNICAL_ONLY_NOT_G0',scientific_qualification='NOT_GRANTED',analysis_role=if(version==1L)'SYNTHETIC_MISSINGNESS_TECHNICAL_NOT_LONGITUDINAL_QUALIFICATION' else 'MISSINGNESS_TECHNICAL_NOT_LONGITUDINAL_QUALIFICATION',input_role=role,input0_sha256=paste(rep('a',64),collapse=''))\n"
                "parent <- function(request)list(schema_version=request$schema_version,scope=request$scope,analysis_role=request$analysis_role,input_role=request$input_role,request=request,technical_lineage=list(schema_version=request$schema_version,input_role=request$input_role,analysis_role=request$analysis_role,request_input_sha256=request$input0_sha256,scientific_qualification_granted=FALSE))\n"
                "must_fail <- function(expression)stopifnot(tryCatch({force(expression);FALSE},error=function(error)TRUE))\n"
                "setwd(" + json.dumps(directory) + ")\n" + body,
                encoding="utf-8",
            )
            environment = {name: os.environ[name] for name in ("HOME", "PATH", "LANG", "LC_ALL", "TMPDIR", "R_LIBS", "R_LIBS_USER", "R_LIBS_SITE") if name in os.environ}
            result = subprocess.run(["Rscript", "--vanilla", str(script)], env=environment, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_v1_manifest_is_unchanged_and_five_v2_kinds_are_explicit(self):
        manifest = tomllib.loads((FAMILY / "manifest.toml").read_text())
        old = tomllib.loads(published_bytes("research-adapters/cachexia-mice/manifest.toml").decode())
        self.assertEqual(manifest["nodes"][:5], old["nodes"])
        self.assertEqual({key: value for key, value in manifest.items() if key != "nodes"}, {key: value for key, value in old.items() if key != "nodes"})
        self.assertEqual(len(manifest["nodes"]), 10)
        for first, second in zip(old["nodes"], manifest["nodes"][5:], strict=True):
            self.assertEqual(second["kind"], first["kind"] + "_v2")
            self.assertEqual(second["ports"], first["ports"])
            self.assertEqual(second["resources"], first["resources"])
            expected = dict(first["command"]["env"], AUTONOMICS_TECHNICAL_CONTRACT_VERSION="2")
            self.assertEqual(second["command"]["env"], expected)

    def test_v1_defaults_and_version_crossing_are_fail_closed(self):
        self.run_r("""
for (environment in environments) {
 Sys.unsetenv('AUTONOMICS_TECHNICAL_CONTRACT_VERSION')
 stopifnot(environment$technical_contract_profile(request(1L,'SYNTHETIC_TECHNICAL_INPUT'))$schema_version==1L)
 must_fail(environment$technical_contract_profile(request()))
 must_fail(environment$technical_contract_profile(request(1L,'EMPIRICAL_TECHNICAL_INPUT')))
 Sys.setenv(AUTONOMICS_TECHNICAL_CONTRACT_VERSION='2')
 must_fail(environment$technical_contract_profile(request(1L,'SYNTHETIC_TECHNICAL_INPUT')))
 for (version in c('','0','3','02')) { Sys.setenv(AUTONOMICS_TECHNICAL_CONTRACT_VERSION=version);must_fail(environment$technical_contract_profile(request())) }
}
""")

    def test_v2_accepts_explicit_roles_without_scientific_permission(self):
        self.run_r("""
Sys.setenv(AUTONOMICS_TECHNICAL_CONTRACT_VERSION='2')
for (environment in environments) for (role in c('SYNTHETIC_TECHNICAL_INPUT','EMPIRICAL_TECHNICAL_INPUT')) {
 candidate <- request(role=role);profile <- environment$technical_contract_profile(candidate)
 stopifnot(identical(profile$input_role,role),identical(profile$analysis_role,'MISSINGNESS_TECHNICAL_NOT_LONGITUDINAL_QUALIFICATION'))
 for (field in c('scope','scientific_qualification','analysis_role','input_role')) { invalid<-candidate;invalid[[field]]<-'GRANTED';must_fail(environment$technical_contract_profile(invalid)) }
 for (role in list(NA_character_,list('EMPIRICAL_TECHNICAL_INPUT'),c('EMPIRICAL_TECHNICAL_INPUT','SYNTHETIC_TECHNICAL_INPUT'))) { invalid<-candidate;invalid$input_role<-role;must_fail(environment$technical_contract_profile(invalid)) }
}
""")

    def test_parent_role_and_lineage_cannot_be_laundered(self):
        self.run_r("""
Sys.setenv(AUTONOMICS_TECHNICAL_CONTRACT_VERSION='2')
for (environment in environments) {
 candidate<-request();upstream<-parent(candidate);environment$technical_parent_role(upstream,candidate)
 invalid<-upstream;invalid$schema_version<-1L;must_fail(environment$technical_parent_role(invalid,candidate))
 invalid<-upstream;invalid$input_role<-'SYNTHETIC_TECHNICAL_INPUT';must_fail(environment$technical_parent_role(invalid,candidate))
 invalid<-upstream;invalid$request$input_role<-'SYNTHETIC_TECHNICAL_INPUT';must_fail(environment$technical_parent_role(invalid,candidate))
 invalid<-upstream;invalid$technical_lineage$input_role<-'SYNTHETIC_TECHNICAL_INPUT';must_fail(environment$technical_parent_role(invalid,candidate))
 invalid<-upstream;invalid$technical_lineage$request_input_sha256<-'wrong';must_fail(environment$technical_parent_role(invalid,candidate))
 invalid<-upstream;invalid$technical_lineage$scientific_qualification_granted<-TRUE;must_fail(environment$technical_parent_role(invalid,candidate))
 invalid<-upstream;invalid$technical_lineage<-NULL;must_fail(environment$technical_parent_role(invalid,candidate))
 synthetic<-request(role='SYNTHETIC_TECHNICAL_INPUT');must_fail(environment$technical_parent_role(upstream,synthetic))
 nested<-upstream;nested$parent<-upstream;nested$technical_lineage$parent_input_role<-candidate$input_role;environment$technical_parent_role(nested,candidate)
 nested$parent$input_role<-'SYNTHETIC_TECHNICAL_INPUT';must_fail(environment$technical_parent_role(nested,candidate))
}
""")

    def test_v2_binding_preserves_original_bytes_and_role(self):
        self.run_r("""
Sys.setenv(AUTONOMICS_TECHNICAL_CONTRACT_VERSION='2')
original<-charToRaw('{"schema_version":2,"input_role":"EMPIRICAL_TECHNICAL_INPUT","number":1.0000000000000002,"nested":{"input0_sha256":"KEEP"},"input0_sha256":"UPSTREAM_CONTENT_HASH"}')
hash<-paste(rep('b',64),collapse='')
bound<-environments[[2]]$bind_json_hash(original,hash)
stopifnot(identical(bound,charToRaw(sub('"UPSTREAM_CONTENT_HASH"',paste0('"',hash,'"'),rawToChar(original),fixed=TRUE))))
stopifnot(identical(jsonlite::fromJSON(rawToChar(bound))$input_role,'EMPIRICAL_TECHNICAL_INPUT'))
""")

    def test_full_rds_and_audit_source_role_are_preserved_by_actual_ast(self):
        self.run_r("""
Sys.setenv(AUTONOMICS_TECHNICAL_CONTRACT_VERSION='2')
definitions<-as.list(parse(files[[1]]) )
run<-Filter(function(value)is.call(value)&&identical(value[[1L]],as.name('<-'))&&identical(value[[2L]],as.name('run_mice')),definitions)[[1L]]
steps<-as.list(run[[3L]][[3L]])[-1L]
environment<-environments[[1]];environment$request<-request();environment$profile<-environment$technical_contract_profile(environment$request)
environment$ROLE<-environment$profile$analysis_role;environment$rows<-c('r1','r2');environment$columns<-'value';environment$mode<-'mice'
environment$computed<-list(data=data.frame(value=c(1,NA_real_)),status=list(table=data.frame(row_id=c('r1','r2'),status=c('OBSERVED','ITEM_MISSING'))),computed=list(requested=c(FALSE,TRUE),result=list(guard_fixture_only=TRUE)),parent=NULL)
environment$outputs<-c('values.tsv','state.rds');environment$audit<-list()
bundle_position<-which(vapply(steps,function(value)is.call(value)&&identical(value[[1L]],as.name('<-'))&&identical(value[[2L]],as.name('bundle')),logical(1)))
stopifnot(length(bundle_position)==1L)
eval(steps[[bundle_position]],environment);eval(steps[[bundle_position+1L]],environment);eval(steps[[bundle_position+2L]],environment)
restored<-readRDS('state.rds');stopifnot(identical(restored,environment$bundle),identical(restored$input_role,'EMPIRICAL_TECHNICAL_INPUT'),identical(restored$request,environment$request),identical(restored$technical_lineage$input_role,restored$input_role),identical(restored$technical_lineage$scientific_qualification_granted,FALSE))
role_audits<-Filter(function(value)is.call(value)&&identical(value[[1L]],as.name('if'))&&grepl('audit$input_role',paste(deparse(value),collapse=' '),fixed=TRUE),steps)
stopifnot(length(role_audits)==1L);eval(role_audits[[1L]],environment)
stopifnot(identical(environment$audit$technical_lineage,restored$technical_lineage),identical(environment$audit$input_role,restored$input_role))
""")

    def test_missingness_states_and_official_method_bodies_are_unchanged(self):
        source = (FAMILY / "scripts/mice.R").read_text()
        original = published_bytes("research-adapters/cachexia-mice/scripts/mice.R").decode()
        for first, last in [("receipt <- function", "set_rng <- function"), ("set_rng <- function", "run_mice <- function")]:
            self.assertEqual(source[source.index(first):source.index(last)], original[original.index(first):original.index(last)])
        self.assertIn("technical_parent_role(bundle, request)", source)
        self.assertIn("technical_parent_role(bundle, request)", (FAMILY / "scripts/bind_contract.R").read_text())

    def typed_helpers(self):
        tree = ast.parse((TYPED / "scripts/typed_values.py").read_text())
        selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in ("require", "technical_upstream_profile")]
        self.assertEqual(len(selected), 2)
        namespace = {"os": os}
        exec(compile(ast.Module(body=selected, type_ignores=[]), "actual-typed-contract", "exec"), namespace)
        return namespace, tree

    def typed_request(self, role="EMPIRICAL_TECHNICAL_INPUT"):
        request = dict(schema_version=2, scope="TECHNICAL_ONLY_NOT_G0", scientific_qualification="NOT_GRANTED", analysis_role="MISSINGNESS_TECHNICAL_NOT_LONGITUDINAL_QUALIFICATION", input_role=role, input0_sha256="a" * 64)
        lineage = dict(schema_version=2, input_role=role, analysis_role=request["analysis_role"], request_input_sha256=request["input0_sha256"], parent_input_role=None, scientific_qualification_granted=False)
        upstream = dict(schema_version=2, input_role=role, analysis_role=request["analysis_role"], technical_lineage=lineage, scientific_qualification_granted=False)
        return request, upstream

    def test_typed_v2_preserves_role_and_rejects_conflicting_audit(self):
        namespace, _ = self.typed_helpers()
        with patch.dict(os.environ, {"AUTONOMICS_TECHNICAL_CONTRACT_VERSION": "2"}):
            for role in ("EMPIRICAL_TECHNICAL_INPUT", "SYNTHETIC_TECHNICAL_INPUT"):
                request, upstream = self.typed_request(role)
                profile = namespace["technical_upstream_profile"](request, upstream)
                self.assertEqual(profile["input_role"], role)
                self.assertEqual(profile["scientific_qualification"], "NOT_GRANTED")
                for field, value in [("schema_version", 1), ("input_role", "UNDECLARED"), ("analysis_role", "GRANTED"), ("scientific_qualification_granted", True)]:
                    invalid = copy.deepcopy(upstream)
                    invalid[field] = value
                    with self.assertRaises(ValueError):
                        namespace["technical_upstream_profile"](request, invalid)
                invalid = copy.deepcopy(upstream)
                invalid["technical_lineage"]["input_role"] = "UNDECLARED"
                with self.assertRaises(ValueError):
                    namespace["technical_upstream_profile"](request, invalid)
                invalid = copy.deepcopy(request)
                invalid["input_role"] = "SYNTHETIC_TECHNICAL_INPUT" if role.startswith("EMPIRICAL") else "EMPIRICAL_TECHNICAL_INPUT"
                with self.assertRaises(ValueError):
                    namespace["technical_upstream_profile"](invalid, upstream)

    def test_typed_v1_and_v2_cannot_cross_and_manifest_appends_only(self):
        namespace, _ = self.typed_helpers()
        request, upstream = self.typed_request()
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                namespace["technical_upstream_profile"](request, upstream)
            request.update(schema_version=1, input_role="SYNTHETIC_TECHNICAL_INPUT", analysis_role="SYNTHETIC_MISSINGNESS_TECHNICAL_NOT_LONGITUDINAL_QUALIFICATION")
            self.assertEqual(namespace["technical_upstream_profile"](request, {})["schema_version"], 1)
        with patch.dict(os.environ, {"AUTONOMICS_TECHNICAL_CONTRACT_VERSION": "2"}):
            with self.assertRaises(ValueError):
                namespace["technical_upstream_profile"](request, {})
        manifest = tomllib.loads((TYPED / "manifest.toml").read_text())
        old = tomllib.loads(published_bytes("research-adapters/cachexia-mice-typed-values/manifest.toml").decode())
        self.assertEqual(manifest["nodes"][:1], old["nodes"])
        self.assertEqual(len(manifest["nodes"]), 2)
        self.assertEqual(manifest["nodes"][1]["kind"], old["nodes"][0]["kind"] + "_v2")
        self.assertEqual(manifest["nodes"][1]["ports"], old["nodes"][0]["ports"])
        self.assertEqual(manifest["nodes"][1]["command"]["env"], {"AUTONOMICS_TECHNICAL_CONTRACT_VERSION": "2"})

    def test_typed_audit_and_schema_keep_actual_v2_provenance_without_new_columns(self):
        namespace, tree = self.typed_helpers()
        request, upstream = self.typed_request()
        with patch.dict(os.environ, {"AUTONOMICS_TECHNICAL_CONTRACT_VERSION": "2"}):
            profile = namespace["technical_upstream_profile"](request, upstream)
        writer = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "write_products")
        provenance = [node for node in ast.walk(writer) if isinstance(node, ast.If) and ast.unparse(node.test) == "profile['schema_version'] == 2"]
        self.assertEqual(len(provenance), 2)
        namespace.update(profile=profile, upstream=upstream, audit={}, schema_record={})
        exec(compile(ast.Module(body=provenance, type_ignores=[]), "actual-typed-provenance", "exec"), namespace)
        for name in ("audit", "schema_record"):
            self.assertEqual(namespace[name]["input_role"], "EMPIRICAL_TECHNICAL_INPUT")
            self.assertEqual(namespace[name]["technical_lineage"], upstream["technical_lineage"])
            self.assertFalse(namespace[name]["scientific_qualification_granted"])
        old = published_bytes("research-adapters/cachexia-mice-typed-values/scripts/typed_values.py").decode()
        old_fields = next(node.value for node in ast.parse(old).body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "FIELDS" for target in node.targets))
        fields = next(node.value for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "FIELDS" for target in node.targets))
        self.assertEqual(ast.literal_eval(fields), ast.literal_eval(old_fields))


if __name__ == "__main__":
    unittest.main()
