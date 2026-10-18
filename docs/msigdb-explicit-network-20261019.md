# MSigDB: explicit network admission

The strict node still calls the same pinned Python/requests image and exact
official HTTPS resource. No method, manifest, frozen request, parser or resource
content was changed for this network verification.

The local host's inherited proxy points to host loopback. In the container,
the inherited route fails with `ProxyError`. The documented
`host.containers.internal` alias was also tested and failed; it was not adopted
as an unverified automatic rewrite.

For this isolated verification only, the DAG runner child environment appends
`data.broadinstitute.org` to both `no_proxy` and `NO_PROXY`, retaining prior
exception lists. Proxy URLs and credentials remain in the existing environment,
not command arguments or public evidence. Neither the parent environment nor
host/service configuration files are modified. The container keeps its declared
egress/default profile, CPU/memory limits, digest and TLS certificate checking.

One real two-node/one-edge SDK fetch exits zero. Its seven actual output files
match the frozen 2025.1.Hs Hallmark symbols resource and independent complete
reader: 48,689 raw bytes, 50 sets, 7,322 membership occurrences. The input JSON
and expected SHA/bytes/ordered set axis/counts were not regenerated from the
new response. The old materialized membership reference is reused explicitly;
no new SQL materialization is claimed in this verification.

This is a scoped available network configuration, not certification of the
broken inherited-proxy route or the running daemon. Production still requires
an explicit operator-approved transport configuration, actual deployment
identity verification and the separate study admission. A mandatory enterprise
proxy must not be silently bypassed; use its approved reachable endpoint
instead. No global proxy disabling, host-network mode, automatic fallback or
scientific release is introduced.

Evidence: `evidence/msigdb-explicit-network-fetch-20261019.json`.

Podman documents proxy inheritance and `no_proxy` in its
[run reference](https://docs.podman.io/en/latest/markdown/podman-run.1.html#http-proxy).
Resource-format agreement is not statistical-method certification; the format
contract is the [official GSEA GMT definition](https://docs.gsea-msigdb.org/GSEA/Data_Formats/#gmt-gene-matrix-transposed-file-format-gmt).
