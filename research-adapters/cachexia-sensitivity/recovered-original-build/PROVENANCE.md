# Recovered original sensitivity build sources

These are exact recovered build-source bytes, not a new build or a replacement
for the previously executed official-package evidence. The original sealed
index has SHA256
`e18a16a7d683cb696355c8045163af90bf7b05a25d16b7bf5ee4f7f8e93f2180`.

- `Dockerfile`: SHA256 `e44fcda107eefaaa1e05c535102c0d41c8338b19c44e1afa30cbf4d7d81dff33`.
- `source-plan.json`: SHA256 `f057ee371d21e4703b003426422adb509b53a60a60db8238af9398e05acb1fc7`.

The source plan and Dockerfile use the same original base:
`localhost/cachexia-lcmm@sha256:602bbf79fa81124edc1d78f366a71e2f8e55f1c768377810104eb81bb03ac97a`.
That local-only base reference and the unpinned `apt-get install libfftw3-dev`
mean this is not a clean-host reproducible recipe. Do not silently modernize
these preserved files or claim that rebuilding today reproduces the old image.

The 23 frozen R source archives total 33,395,409 bytes. Their exact sizes and
SHA256 identities were checked against the original index and this source plan.
The targets are EValue 4.1.4 and metap 1.14 on R 4.6.1, including Bioconductor
3.23 dependencies. Package DESCRIPTION license declarations and bounded
package-root or `inst` license texts were inspected; this is not an exhaustive
per-file, vendored-code, or transitive-runtime license-compliance certification.
The source URLs use HTTPS without user information or query credentials. No
source tarballs, private study inputs, credentials, or execution logs are copied
into this directory.

The OCI config identity, RootFS layer identities, additional-layer private
payload review, and actual installed Debian package identities remain unverified
by this recovery. In particular, qqconf 1.3.2 declares fftw3 >= 3.1.2, but the
actual installed libfftw3-dev version and associated package/license records
still require inspection of the existing image.

These files do not authorize public image distribution, establish current
production availability, or grant scientific release or G0. Reuse the retained
numerical evidence; do not rerun metap or EValue merely because these build
sources have been restored.
