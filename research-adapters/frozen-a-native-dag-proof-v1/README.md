# A native SDK bridge: sealed synthetic request

The final managed proof passed **two new boundary cases**: the connected native
SDK/container bridge with complete output readback, and one missing upstream
File rejected by native graph admission. It reused the previous sealed synthetic
request and the unchanged frozen source definitions. No MR fit, true study
execution, qualification decision, production installation or G0 was performed.
This README and `evidence-index.json` were added **after** the final tests as
documentation. The tested source was `prove_native.py` alone, SHA256
`6c87e1f28e6b72aaf1ffbded7db58e63e56c7d5cf2f878743f3b6133dddb7ef2`.

## What actually ran

The existing SJTU-built `official_plugin_dag` consumer was reused without
compilation. Its binary SHA256 is
`e289d372b8d0abd84e4371ce48b9091eb41965d5de1985865286a2f5bb09537a`, and its
source SHA256 is
`290e615b725b7e663ed1449e415f9499dfd4203e5993fc460cdc7cd3f48db272`.
The actual current source path is
`/home/zj-normal/Work/autonomics/crates/container-plugin/examples/official_plugin_dag.rs`;
the sealed source is `artifacts/permanent/sjtu-consumer-collection/official_plugin_dag.rs`
inside the collection session below. This is a different source file from the
plugin repository's `tools/probes/official_plugin_dag.rs`, which is not the
consumer used for this proof.
Both were rehashed in sealed collection session
`3de5533e881144d1b1643c4fd648ef7b`, seal
`835bcb4368da6bccf05abf5dac61e51f88e71cfafa510851d2d6ac99d0082314`.
Its recorded 13 directly linked libraries belong to exact engine/SDK commit
`864b3a75a5e27c81cba0d78cbe834e796f51df26`; the current consumer source matches
that sealed source byte for byte. This proves this exact compiled SDK path,
not the entire later mutable checkout or production engine.

The consumer already supports multiple explicit plugin manifests. It used its
existing original manifest/script byte checks, safe local source read, loader
implementation identity check, distinct plugin/kind registration, native
`NodeRegistry::build_node`, `DAG::add_node_with_spec`, `DAG::add_edge` and
`InputHashing::ContentRequired`. No old topology admission ID was relabelled.
The generated assembly manifest retained SHA256
`c12c9f045075678cf29b8b6504131e0ee1a8475ae5690043c57af6964fc20199`; the official
manifest retained SHA256
`cb31abd78e4fbc9e5c014622842b150783d3e648009c132b92d10db8e3e40daa`.
All eight previously tested wiring files, four V1 source files, and 59 members
of the three reused archives were checked before execution.

The positive DAG had **22 real nodes and 24 real edges**: 20 ordinary File
producers, unchanged assembly through its File bridge, and unchanged official R
through its four required Files. There were exactly two SDK container workers,
one fixed Python image and one fixed R image. Each was observed with network
`none`, pull `never`, read-only root filesystem, one CPU, 1,073,741,824 bytes of
memory and PID limit 64. The existing qualified image store route was used
without modifying its profile. The managed shim tracked every container intent
inside the service cgroup and proved zero containers remaining before cleanup.

The actual images were:

- Python: `docker.io/library/python@sha256:7bf6c3111fe094f8ee1a1cbcdc63c4cfb345b0e3df42d5aa9a90b3b4b022ab6d`,
  runtime Python **3.14.7**.
- R: `ghcr.io/zj-2002/mrlap-official@sha256:e6e10cddfa1cba8046ee6fbc1492b94cbd70d66b097f5f415845d56f9f925434`,
  runtime R/stats **4.6.1**, jsonlite **2.0.0**; `sh`, `sha256sum`, `cut` and `cp`
  were all found and used. The inspected config ID was
  `294152508a320bf7bbefa9ba53a095a121535cc3643e79a842950609843ea84c`.

## Input and complete output identities

The exact earlier synthetic request was reconstructed with its sealed original
path labels and matched SHA256
`de2dce1af95b3fc4614cb2153da57cd16e2e2ecf6945021765d17bf7bf051626`.
Only File locations were then relocated into the owned technical evidence root;
all three source/history/opaque RDS dependency bytes were checked against the
old closure. The nine actual frozen source files and two decision files were
checked by the unchanged preparer and again by the container bridge. The closure
used **3 unique request dependencies, 20 assembly inputs and 11,992,721 bytes**.
The unchanged limits remain 239 unique dependencies and 128 MiB; no real-data
request size or larger-family transport is claimed.

All seven declared output Files were copied from their actual SDK output ports
under managed TMPDIR into permanent evidence before cleanup. Complete family
TSV (564 rows), vector TSV (840 rows), and adjusted TSV (840 rows) bytes matched
the old sealed synthetic carriers. A separate isolated R container opened the
new RDS and old RDS, compared all six vector objects, all ordered analysis IDs,
all 840 numerical values, frozen function text and R/stats versions, and checked
the corresponding new TSV/receipt memberships.

The new RDS SHA256 is
`1f6d304e56c70420941c674d94efee239e45f5f53992fdc5e48f763b4605413b`; the separately
read old RDS SHA256 is
`9e4feed348439f71dc644a59aebc3da771a93a2b5b999b0b1427d666e1b40191`.
The R readback explicitly observed different `input_sha256` provenance fields
while the six vector objects and frozen definition matched. It does not claim
that this is the sole cause of every serialized-byte difference. The old RDS
was mounted only in the independent readback container, not supplied to the new
official adjustment worker.

The negative case removed only the edge feeding assembly input 19. The actual
consumer exited 1 with
`PortDisconnected { node: "assemble", port: 19 }` before scheduling. It published
no DAG report or output File and created no additional worker. The final session
thus contains **2 runner invocations, 1 actual scheduler run, 2 SDK container
workers and 5 total container executions** (two preflights and one R readback).

## Final permanent evidence

Final session: **`59576b13533a4fc5a12ecb8062e73f5c`**, CLEANED,
worker/launcher exit **0**, two cases passed. All **152** archived members were
rehashed after cleanup without mismatch.

- Manifest: `/home/zj-normal/.local/state/autonomics/validation-archives/59576b13533a4fc5a12ecb8062e73f5c/artifacts/MANIFEST.json`.
- Manifest seal: `cdcce82048601e116be06cc5b2efebddf7a510e8b572bf07878fedd0b43cbc1b`.
- Verification: `/home/zj-normal/.local/state/autonomics/validation-archives/59576b13533a4fc5a12ecb8062e73f5c/artifacts/permanent/a-native-dag/verification.json`.
- Verification SHA256: `68cae0dc1aeeffbd351f21115d34a53855a7d086940df3415665a58f40a066a3`.

`connected/dag-report.json`, `connected/output-capture.json`,
`connected/outputs/{assemble,official}/`, `R-full-readback.stdout`,
`missing-upstream-file/runner.stderr`, `native-creates.jsonl` and the managed
`container-stoppage.json` give the concrete execution, output and stoppage proof.
The final session's native task receipts are under its permanent `task-receipts/`.

## Retained failed attempts and exact cumulative count

Four earlier sessions remain failed, with their exact source snapshots and
permanent error records. Their successful subprocesses do not make the whole
sessions pass. `evidence-index.json` records every seal, verification SHA and
source SHA, plus corrected counts based on actual runner/container evidence:

| Session | Overall exit | SDK scheduler runs | Started containers | Driver issue |
| --- | ---: | ---: | ---: | --- |
| `b269f7aa6ecf49aa9b94a1e257d3dcae` | 1 | 0 | 0 | Podman CLI rejected new driver's `1Gi` memory spelling before start |
| `eea534b0ecf0426f8bfa8ae9d8c08dcd` | 1 | 0 | 1 | New preflight omitted explicit entrypoint, so Rscript received `Rscript` as a filename |
| `f9b0e880a80441d981d7e623c20b59dc` | 1 | 1 | 4 | Both SDK workers succeeded; new output collector searched the wrong directory; no complete readback claim |
| `6f84e542c5a84a7ebce25b5e09afe887` | 1 | 1 | 5 | Full readback succeeded; new negative assertion expected the wrong diagnostic substring |
| `59576b13533a4fc5a12ecb8062e73f5c` | 0 | 1 | 5 | Final complete proof |

Across all attempts: **3 actual SDK scheduler runs, 5 runner invocations,
2 admission refusals, 6 SDK container workers and 15 started containers**,
plus one Podman launch rejected before any container started. There were three
connected official adjustment R executions. There are two distinct new boundary
cases; the old 18/10/8 cases were not rerun. The initial failed report's container
counter counted an attempt, and some intermediate reports counted only direct
preflight/readback containers until final reconciliation; the table above is
the corrected total, without altering the sealed failed reports.

The scope remains engineering transport, interface and isolated DAG execution.
Production deployment, finite-primary qualification interface, signatures,
scientific review and G0 remain pending. Frozen family counts and the current
275 pending decisions plus one O2 were not changed.
