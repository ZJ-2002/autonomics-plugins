# Native node tests

Node unit and integration tests belong to this workspace. Run builds and tests
in an admitted build environment using the pinned engine SDK and dependency lock.
Offline fixtures are synthetic. Live tests remain ignored by default.

To run a live provider test, explicitly supply `AUTONOMICS_NATIVE_LIVE_FIXTURE`
as the path to a private JSON object keyed by provider name. Each provider object
contains the string and integer fields requested by `fixture.text(...)` and
`fixture.number(...)` in its test. There are no default study, participant,
dataset or accession selections. Keep inputs and live results outside this
repository; the exact equality and shape assertions remain active.

The ignored MinerU test additionally requires `MINERU_API_KEY` and
`AUTONOMICS_MINERU_SYNTHETIC_PDF`. Supply a synthetic plot PDF containing
`TOY A`, `12` and `34`; the test checks extracted figures and text through VFS.
Never use private research documents as public fixtures or commit credentials.
