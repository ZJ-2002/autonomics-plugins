# Survey official adapters: output-ownership repair

## Finding and change

Existing-file checks did not protect dangling output symlinks. The old wrapper
could follow a diagnostic symlink to create a foreign target or remove a normal
output symlink during error cleanup. Eight actual entry-point cases reproduced
the defect: five survey outputs and three hash-binder outputs.

The statistical entry and the binder now share the same verified publisher AST:
refuse existing paths, dangling links and input/output aliases; compute in a
private staging directory; publish with exclusive hard links; and roll back only
files whose device/inode identity still matches a file created by this invocation.
The old failure handler can clean only the private staging paths, not foreign
destinations. Writer status is returned before publication and converted to the
actual process exit afterward. All statistical helper definitions remain global,
so the publisher does not introduce a new enclosing method environment.

No official method, manifest, parameter, port or image changes. The raw-byte JSON
hash binder remains unchanged: it fills only the one explicit source-hash token
without reserializing frozen floating-point literals.

## Evidence and limits

- Eight dangling-output counterexamples are preserved separately from the fix.
- Twenty-four actual R output-protection controls pass across both entry points:
  existing files, every dangling output position, input aliases, invalid-contract
  diagnostics, an audit publication race and foreign replacement during rollback.
- Thirty pre-existing helper/function ASTs match the frozen pre-repair source;
  this includes the statistical, input, design and raw-JSON helpers. The two new
  publisher ASTs match each other.
- Five Python source/manifest binding checks pass. These are engineering checks,
  not five scientific method validations.
- The fixed `survey` 4.5 image and the original independent author-reference
  packet remain the method evidence baseline. The package's scope is documented
  in the [official survey manual](https://cran.r-project.org/web/packages/survey/survey.pdf).

Current repaired-wrapper DAG requalification remains pending. Historical
189-DAG evidence is not described as 189 new executions. Formal survey eligibility,
study population weights, scientific implementation locks and current production
deployment are not inferred from the existence of these adapters. A typed
downstream boundary must preserve string identifiers and explicit missing states;
automatic TSV inference is not evidence of that contract.

The nine statistical alternatives still require their own current scoped DAG
records. The design builder and hash binder are engineering dependencies, not two
additional repaired statistical candidates. These controls invoke no statistical
method on actual research data. B-S remains `CONDITIONAL_NOT_READY`, GS01 remains
`OPEN`, 276/288/696 are unchanged, and no G0 is granted.
