# A real-intake V1: stable bundle File interface

This is a transport adapter, not an MR implementation or a primary-qualification
authority. It replaces the request-specific port list of the earlier explicit
File candidate with one stable ordinary File input. The original four analysis
modules and nine frozen source identities in `source-lock.json` are unchanged.
The manifest embeds the exact lock bytes as a runtime file; that value is literal
content, not a host pathname. No original host data path is opened in a worker.

## Contract

Input 0 is a deterministic, uncompressed ZIP archive prepared with:

```sh
python3 -B bundle.py --request /absolute/request.json \
  --study-root /absolute/frozen-study --adapters-root /absolute/research-adapters \
  --output /absolute/new-request.zip
```

Run packaging/acceptance under the repository's managed validation lifecycle.
The archive includes private study inputs: do not commit or publish it. Persist
required scientific inputs/results outside disposable scratch. Archive timestamps
are fixed for byte reproducibility and are explicitly not result-viewing history.

The archive contains `closure.json`, followed by exactly ordered `files/NNNN.bin`
members: nine frozen sources, original request, two O2 decision files, four pinned
implementation files and every unique declared source/history/RDS dependency.
Each member has an exact role, SHA256 and byte count. Unknown/duplicate/reordered
members, symlinks, compression, unsafe materialization paths, conflicting hashes,
changed source files and output overwrites are refused. Verification precedes
materialization; files are not unpacked using general-purpose extractall.

Limits: 276 sources, 276 edges, 276 history records, at most 828 unique request
dependencies, 32 MiB per member, 4 MiB request/closure, 128 MiB total member
payloads and 133 MiB archive. These bound this interface; they do not certify
all request combinations or inputs. The transport test with 276 distinct toy
dependencies proves removal of the old 239-dependency port ceiling, not 276
scientific analyses or qualification of additional edges.

| Output | Meaning |
| --- | --- |
| 0 `real-family.tsv` | Unchanged complete family assembly |
| 1 `real-vectors.tsv` | Unchanged full ordered correction vectors |
| 2 `real-assembly.json` | Original assembly semantics and eligibility receipt |
| 3 `bundle-transport.json` | Bundle, closure, original/relocated request and output identities |
| 4 `frozen-methods.R` | Byte-identical frozen R methods, not a new implementation |
| 5 `adjust-real.R` | Byte-identical pinned official adjustment driver |

Connect ports 1, 2, 4, 5 to inputs 0, 1, 2, 3 of
`frozen-a-real-intake-official-v1/frozen_a_real_intake_adjust_v1`.
The resulting graph has one bundle producer and two workers: 3 nodes, 5 edges.
Both workers pin existing images, one CPU, 1 GiB, isolated network, read-only root,
pull-never and PID limit 64. No new image or native statistical algorithm is used.

## Evidence and limits

Managed session `ecb88e95e9de4dc18ac7fda32545d156`, seal
`e19c15e7f4806332fb0fda583e03d938f518d83c51b79ac0b81465f20932e1ed`:
`~/.local/state/autonomics/validation-archives/ecb88e95e9de4dc18ac7fda32545d156/artifacts/permanent/a-bundle-native-intake/verification.json`,
SHA256 `c354a35a14f7ea3550e26d8ff96b99f6469455eaa30143cabb532d9f7f987f54`.
Exit 0, CLEANED. Twelve self-cleaning toy tests and one real, previously seen
X01-to-M06 transport DAG ran. All 9 declared output files were captured; family,
vector and adjusted TSVs were byte-identical to the prior sealed real chain.
564 family rows remain complete, all primary values missing, 275 decisions pending
and one locked O2. This did not run a new MR fit or search for a more favorable P.

The reused native SDK is commit `864b3a75a5e27c81cba0d78cbe834e796f51df26`,
consumer binary SHA256
`e289d372b8d0abd84e4371ce48b9091eb41965d5de1985865286a2f5bb09537a`.
It is not a claim of current resident-daemon DAG submission. A Git-pinned
installation, current resident identity and scientific qualification are separate
gates. No existing selected node address is silently rebound; the old publisher
does not newly accept these receipts. The two other historical precise carriers
remain missing. Finite-primary admission still requires a versioned, scientifically
approved qualification contract; this adapter cannot manufacture it.

Test entry: `python3 -B -m unittest tests.test_a_bundle_transport -v` from repository root.
Technical evidence, source publication and successful execution do not grant G0.
