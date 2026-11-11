# Independent native nodes

This workspace owns native DAG node implementations and their statistical
helpers. The engine discovers the catalog from the `autonomics-native-nodes`
executable and starts an owned process for each invocation. Rebuilding an engine
does not require rebuilding an installed node package.

Builds require a compatible engine SDK. The admitted build assembles the frozen
node sources with the required engine libraries, verifies their source inventory,
and writes `SDK_SOURCE.json`. The build driver supplies the full node source
revision through `AUTONOMICS_NATIVE_SOURCE_REVISION` and the manifest path through
`AUTONOMICS_NATIVE_SDK_MANIFEST`. The executable embeds those identities and the
workspace dependency lock digest. Build the assembled workspace with:

```sh
cargo build --release --locked -p autonomics-native-nodes
```

Keep the engine SDK and its provenance in the private build environment. This
repository distributes the generic node sources, not that SDK. Lock changes
require a new frozen source revision before release.

An installation manifest selects measured executables and pins their source
revision, executable SHA256, dependency-lock SHA256, SDK manifest SHA256 and
protocol version. It also sets invocation deadlines, storage-handle limits and
explicit inherited environment names. Install only packages qualified against
the intended engine interface. Existing engines retain their loaded package
snapshot until their registry is reconstructed.

Node ports, schemas, descriptions, resource requests, cache dependencies and
observations cross the process interface. Arrow data and large structured values
use invocation-owned storage. File operations use the host VFS principal and
atomic publication rules. Bibliography nodes use the host's resident library
service; they do not open the library database themselves. Nodes that require
that service continue to reject unsupported remote execution.

Container manifest plugins retain their separate container runtime. Additional
native packages can coexist in the installation manifest; duplicate node
addresses are rejected.
