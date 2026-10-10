# Isolated guarded lme4 wrapper

`cachexia_lme4_fit` is staged separately from the production `lme4` symlink and
does not replace or register `lme4_fit`. The immutable image contains R 4.4.1,
lme4 1.1.35.5, lmerTest 3.1.3, pbkrtest 0.5.3 and broom.mixed 0.2.9.6.

Gaussian models delegate to `lmerTest::lmer`; `summary(..., ddf=...)` and
`broom.mixed::tidy(..., ddf.method=...)` use the selected Satterthwaite or
Kenward–Roger convention. Poisson/binomial delegate to `lme4::glmer` with the
declared bobyqa/nAGQ convention and Wald-z inference. This does not imply
equivalence to another optimizer, package version, weighting scheme or estimator.

The additional study preflight rejects missing/nonfinite original or transformed
model data, rank-deficient fixed designs, nonpositive residual degrees of freedom
and silently omitted observations. These are explicit study restrictions, not
claims about the defaults of official lme4.

The production wrapper was reproduced silently dropping a duplicated fixed term
while reporting `status: ok`; this remains a production gap until an authorized
deployment is completed. This staged wrapper blocks that input before fitting.

Three declared output ports contain fixed effects, random-parameter SD/correlation
estimates, and the model/status log. Singular/nonconverged fits retain diagnostic
outputs; a successful DAG is not a clean scientific pass. Downstream formal
adapters must read the status. No daemon registration, bootstrap certification,
nonconvergence injection, longitudinal death handling, design-weight or full
method-domain acceptance is claimed.
