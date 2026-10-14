"""Generate only synthetic method-test contracts; never open study data."""
import csv
import hashlib
import json
from pathlib import Path

CODE_SHA = "f7e334db38e331acc30cd0117ca9f2b82831523d1c07ce742382eacbd3aff1cd"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def generate(destination, noise):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    fields = ["SNP", "beta.exposure", "beta.outcome", "se.exposure", "se.outcome",
              "eaf.exposure", "eaf.outcome", "effect_allele.exposure", "other_allele.exposure",
              "effect_allele.outcome", "other_allele.outcome", "id.exposure", "id.outcome",
              "exposure", "outcome", "mr_keep", "action", "palindromic", "ambiguous", "remove",
              "source_INFO", "frequency_difference", "F_exposure", "chr37", "pos37", "eligibility_reason"]
    with (destination / "input.tsv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for i, (x, residual) in enumerate(zip([.12,.18,.22,.28,.32,.37,.41,.47], [-2,1,0,2,-1,1,-2,1])):
            row = dict(SNP=f"rsSynthetic{i+1}", action=2, palindromic="FALSE", ambiguous="FALSE", remove="FALSE",
                       source_INFO=.99, frequency_difference=0, F_exposure=(x/.01)**2,
                       chr37=6 if i == 0 else 5 if i == 1 else 1,
                       pos37=25000000 if i == 0 else 2000000 if i == 1 else 10000000+i,
                       eligibility_reason="QUALIFIED", mr_keep="TRUE")
            row.update({"beta.exposure":x,"beta.outcome":.4*x+noise*residual,"se.exposure":.01,"se.outcome":.04,
                        "eaf.exposure":.2,"eaf.outcome":.2,"effect_allele.exposure":"A","other_allele.exposure":"C",
                        "effect_allele.outcome":"A","other_allele.outcome":"C","id.exposure":"GCST90652391",
                        "id.outcome":"GCST90002393","exposure":"X01_BMFF_residual_INT","outcome":"M06_monocyte_transformed"})
            writer.writerow(row)
    cfg = dict(status="LOCKED",version="4.3.2",analysis_id="G0_V432_A_X01_M06",enabled_edge="A_X01_M06",
               scientific_code_sha256=CODE_SHA,exposure_role="LEGACY_EXPLORATORY",overlap_class="O2",
               primary_p_source="NA",ordinary_ivw_parallel="EXPLORATORY_ONLY",seed=432202610,bootstrap_n=1000,
               harmonise_action=2,methods=["mr_ivw","mr_egger_regression","mr_weighted_median"],
               n_independent_IV=8,program_sha256=sha(destination / "input.tsv"),technical_scope="SYNTHETIC_METHOD_TEST")
    cert = dict(status="G0_V432_MINIMUM_COMPLETE",version="4.3.2",technical_scope="SYNTHETIC_METHOD_TEST",
                A=dict(allowed=True,analysis_id=cfg["analysis_id"],role="LEGACY_EXPLORATORY_O2_PRIMARY_NA",confirmatory_allowed=False))
    (destination / "config.json").write_text(json.dumps(cfg,indent=2)+"\n")
    (destination / "certificate.json").write_text(json.dumps(cert,indent=2)+"\n")
    (destination / "lock.tsv").write_text("package\tversion\nTwoSampleMR\t0.7.11\n")
    proof = dict(scope="SYNTHETIC_METHOD_TEST",input_sha256=[sha(destination/name) for name in
                 ["input.tsv","config.json","certificate.json","lock.tsv"]],scientific_code_sha256=CODE_SHA,
                 R="4.6.1",TwoSampleMR="0.7.11",scientific_authorization_granted=False,generator_sha256=sha(__file__))
    (destination / "proof.json").write_text(json.dumps(proof,indent=2)+"\n")
