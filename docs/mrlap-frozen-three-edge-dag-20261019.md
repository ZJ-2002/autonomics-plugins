# Official MRlap: frozen three-edge technical acceptance

This supplements, and does not replace, the publication repair record. The native
Rust MRlap implementation remains **FORBIDDEN**. Use the explicit `mrlap` plugin
with three file inputs and four file outputs, not the legacy native DataFrame
interface. This is already-seen technical reproduction, not independent research
replication or scientific/G0 approval.

## Bound implementation

- Manifest SHA256: `8dcc2b973b844150f660b9fcd9209b564d4642f118ed716fc219cc4a072c81c6`.
- Entry SHA256: `7d0e4b458fa90b4804f26948f2cd837f921616b92aaad544e0a26721328cc14a`.
- Image: `ghcr.io/zj-2002/mrlap-official@sha256:78f195b862a3b7c5f8d96a96576cfb2c66b08f9bd31a739da59a017726cd063d`.
- Author MRlap 0.0.3.3, `do_pruning=FALSE`, explicit frozen IV lists, seed 1.
- Original real LD panel digest: `sha256:c1bdd30eabb9d821fe06ff5647bf6a08f9db29f80223762cfc6b3eb285c6d065`;
  all 49 declared files checked before each container.

## Results and failure propagation

The XM, XY and MY full result RDS files are byte-identical to the retained staged
author-software references. All 51 summary fields are checked: 48 finite values
have zero absolute difference; the three missing `rg_se` values are recorded
explicitly rather than treated as numeric matches. Retained IV counts are 7, 7,
and 97. Each complete summary is read and written through the engine I/O nodes.

An occupied result port preserves the foreign file's identity and bytes, fails
the MR task, and skips both downstream I/O tasks. An altered input SHA is refused
before graph/container execution. Fresh owned containers are confirmed stopped.

XM's statistical task succeeded in a parent session whose collector subsequently
failed because a physical sink path was passed as a VFS path. Its four complete
outputs and successful task identity were retained and verified. Only the I/O
layer was recovered with the corrected virtual sink. The failed parent session
remains failed. The final batch reused that sealed XM component and recovery,
without re-estimating XM or repeating its recovered I/O; XY and MY were freshly
executed. This is not three fresh estimations in the final batch.

## Limits

The graphs bind current plugin sources to a retained engine dependency ABI, not
an entire newly built engine or a resident-daemon deployment. The author reference
was retained, not independently recompiled in a new environment. This does not
certify all inputs, parameter branches, online APIs, or method assumptions.
Installed ieugwasr 1.1 does not meet TwoSampleMR's declared >=1.2 dependency;
qualification is restricted to this tested offline route. No production restart,
research eligibility decision, frozen-family change, or G0 sign-off is implied.

The sealed private execution record is identified by session
`2cce168b036143bda99d893babe73f68`, seal
`682a16d21208d8dc35c3709e1adda8100e8e9cef5d6fb560d4012b8def3515db`.
Private study inputs, outputs and launcher logs are not published here.
