# Contributing

Use Python 3.11+ and the repository's editable install. Run `python -m unittest discover -s tests -v` and the CLI conformance checks for any changed profile. Android changes also need the `sdk` JVM tests and relevant demo build/lifecycle checks described in [android/README.md](android/README.md).

Keep one shared API, GUI, owner and optional network adapter. New profile facts belong to the selected device's codec/spec; do not change a common abstraction to invent shared RPM, ACK, timer or firmware behavior. Preserve unknown bytes and distinguish structural validation from semantic evidence. Add focused regressions for demonstrated bugs; state what changed, why and which checks ran.

Document evidence as static host observation, isolated offline comparison, synthetic model choice, inference or unknown. Identify build/hash and source symbol for new wire claims. Never promote a model test to physical validation. Record skipped or unavailable checks explicitly.

Contribute only material you may redistribute. Do not add OEM APKs, decompiled methods, firmware, extracted databases/recipes/media, device identifiers, credentials, private paths or signing material. Use newly written synthetic traces and preserve included notices. Community links are attribution, not permission to copy unlicensed content.

Current public instructions are in English; historical device research should remain accessible. Validate relative documentation links when moving content. Use [migration](docs/migration.md) to describe compatibility changes instead of silently breaking old helper imports.

This source preparation does not authorize remote publication or release signing. Keep build output, caches, local SDK locations and diagnostic logs out of the source distribution.
