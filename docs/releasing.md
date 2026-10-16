# Release preparation and GitHub publication

The unified source is published at [antrea/monsieur-cuisine-developer-sdk](https://github.com/antrea/monsieur-cuisine-developer-sdk), with [executed hosted verification](tests.md). This guide describes how to reproduce preparation and publish future releases. Check the actual [release list](https://github.com/antrea/monsieur-cuisine-developer-sdk/releases) for published assets. The predecessor repositories are separate products.

## Freeze and verify source

Confirm the intended version in `pyproject.toml`, the Python package, Android metadata, [release notes](../RELEASE_NOTES.md) and [changelog](../CHANGELOG.md). The unified 0.1.0 history is independent of the earlier 0.2.0 toolkits. Review the current source commit and local changes before selecting a candidate.

Run from the checkout after installation:

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
mc-sdk --model mcc conformance
mc-sdk --model mcs conformance
mc-sdk --model mcs conformance --corpus envelope
python -m monsieur_cuisine_sdk --model mcc --smoke-test
python -m monsieur_cuisine_sdk --model mcs --smoke-test
python tools/audit_release.py --runtime
```

The full suite and GUI smoke commands require working Tk and a display. Linux CI uses Xvfb; headless API/CLI checks do not require Tk. Repeat relevant Android JVM, packaged-consumer, build and actual-runtime checks from [android/README.md](../android/README.md) and [Android integration](android.md). A build-only result must not be labeled an ART/activity pass.

Update [RELEASE_AUDIT.md](../RELEASE_AUDIT.md) with actual results, environments, skipped/unrun work and remaining limits. Confirm all required current guides, funding metadata, notices, original MIT credits, independent specs/fixtures and current screenshots exist. Historical research remains marked as historical. The content audit checks selected files, links, syntax, structured data, excluded material and common secret/private-path patterns; manual provenance/license review is still necessary.

Freeze source after those updates. Any later source or documentation change invalidates the old source manifest: rerun the audit and rebuild/reseal the affected artifacts. Do not attach a ZIP or checksum from an earlier tree merely because code tests still pass.

## Build outside the checkout

The release builder refuses an output directory inside the public checkout. Choose a fresh external directory, for example a sibling `sdk-release-0.1.0` folder, and run:

```sh
python tools/build_release.py --output ../sdk-release-0.1.0 --wheel --verify-wheel --verify-gui
```

This selects audited public source, creates a deterministic source ZIP and source manifest, builds the wheel from a clean selected-source stage, and installs/tests it in a fresh isolated environment outside the checkout. Installed checks exercise both models, compatibility imports, actual `mc-sdk` entrypoints/package resources and, with the flags above, both native GUI smoke paths. Review `wheel-build.log` and `installed-wheel-check.json` in the output.

To export already-built original SDK/demo artifacts, pass explicit paths from this project's build output:

```sh
python tools/build_release.py --output ../sdk-release-0.1.0 --wheel --verify-wheel --verify-gui \
  --android-sdk-jar android/sdk/build/libs/sdk-0.1.0.jar \
  --demo-apk android/demo/build/outputs/apk/debug/demo-debug.apk
```

The continuation syntax above is POSIX; use one line or your shell's continuation syntax on Windows. The builder exports only the selected SDK JAR and developer debug APK, not private host-test/codec-probe JARs, OEM applications, a signed release or a toolchain. The SDK consumer needs Kotlin stdlib; retain the relevant [notices](../THIRD_PARTY_NOTICES.md).

Review the generated `ARTIFACT_MANIFEST.json`, source manifest and `SHA256SUMS.txt`. Check that the exact intended files are present, hashes match and installed behavior comes from the isolated environment rather than the checkout. Keep private audit logs/toolchain paths outside the public source. Archive hashes identify bytes; they do not certify legal provenance or physical behavior.

## Publish only after target authorization

First obtain the intended owner/repository, visibility and permission to create/push/publish. Inspect existing remotes; never repoint or replace a predecessor repository implicitly. If authorized, create a new empty repository named for this unified product, preserving the prepared history and files. Do not add a conflicting generated README/license on GitHub.

The following is a **template**, not an executed operation. Replace `OWNER` and artifact paths with the approved target and reviewed output before running it:

```sh
git status --short
git remote -v
gh repo create OWNER/monsieur-cuisine-developer-sdk --public --source . --remote origin
git push -u origin HEAD
git tag -a v0.1.0 -m "Monsieur Cuisine Developer SDK 0.1.0"
git push origin v0.1.0
gh release create v0.1.0 --repo OWNER/monsieur-cuisine-developer-sdk --draft \
  --title "Monsieur Cuisine Developer SDK 0.1.0" --notes-file RELEASE_NOTES.md \
  ../sdk-release-0.1.0/monsieur-cuisine-developer-sdk-0.1.0-source.zip \
  ../sdk-release-0.1.0/monsieur-cuisine-developer-sdk-0.1.0-source-manifest.json \
  ../sdk-release-0.1.0/SHA256SUMS.txt ../sdk-release-0.1.0/ARTIFACT_MANIFEST.json
```

If a remote/repository/tag already exists, inspect its identity and contents instead of blindly rerunning creation commands. Add the reviewed wheel/JAR/debug APK as desired draft assets, then check asset hashes, notes, license notices, model names and version. Drafting and making a release public are separate actions. Release signing, PyPI upload and publishing an Android application are not implied by this guide.

After a push, require successful hosted workflow results for the exact release commit. Record failures or skips honestly. Review all reachable public history, filenames, image metadata and nested archive contents for private development details. Keep logs, credentials and absolute workstation paths outside public source and assets; select uploads by explicit filename rather than uploading an entire build directory. Review the draft, then publish when the release owner has authorized the final action. Funding metadata in [`.github/FUNDING.yml`](../.github/FUNDING.yml) points to the [Ko-fi page](https://ko-fi.com/blackstufflabs) for [blackstufflabs.com](https://blackstufflabs.com).
