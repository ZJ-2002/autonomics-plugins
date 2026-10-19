# Unregistered adapter development

These implementations have no runnable plugin manifest yet. They are excluded
from the registered `plugins/` and `research-adapters/` catalogs, not silently
accepted as node families. Their presence is not deployment, scientific
certification or permission to execute a study.

`ieugwasr-official/` contains a direct-author R adapter, offline controls, and an
unbuilt dependency-image recipe. Its immutable derived-image digest is still
null. Promote it to the registered adapter namespace only after building and
verifying the actual image, adding a real pinned manifest, and proving its
engine interfaces and isolated workflow. Do not weaken catalog checks or use a
placeholder image identity to make a staged implementation appear installed.
