# Third-party notices and research attribution

Original unified SDK code, explanatory documentation and synthetic data use the root [MIT license](LICENSE), preserving both MCC Developer Toolkit and MCS Developer Toolkit contributor notices.

The MIT license applies to original toolkit/SDK code, explanatory documentation and synthetic data. No rights in manufacturer software, firmware, recipes or trademarks are granted. Included third-party material retains its own terms and notices.

The unmodified official Gradle wrapper is the included third-party build bootstrap. Its Apache 2.0 license and notices are retained under `android/gradle/wrapper`; [Android third-party notices](android/THIRD_PARTY_NOTICES.md) identify the wrapper, pinned distribution checksum and externally resolved Kotlin/Android/JUnit dependencies. Dependency terms are not replaced by the SDK's MIT license. Python, Tcl/Tk, JDK, Android SDK/emulator, Gradle distribution and resolved build dependencies are externally obtained tools, not bundled runtime distributions in this source tree.

The base Python runtime has no third-party package dependencies. Optional extras
are separately obtained, not vendored or included in source archives:

| Extra | External packages | Upstream terms |
|---|---|---|
| `serial` | pyserial | BSD license; retain the upstream notices when redistributing it |
| `analysis` | pyelftools, Capstone | pyelftools public-domain dedication/upstream notices; Capstone BSD license and included architecture notices |

Installing an extra does not replace its upstream terms with the SDK MIT license.
The owner-supplied MCC Backup/mtkclient GPL-3.0 tool remains a separate external
distribution. The adapter verifies and invokes that copy; no original GPL source,
driver or executable is included in the SDK packages. Provisioning a user's
private external tool installation does not make it an SDK release asset.

Research references remain attributed, with examined revisions and observed licensing scope, in [MCC references](docs/devices/mcc/third-party-references.md) and [MCS community references](docs/devices/mcs/research/en/community.md). Those projects are references, not vendored code. Public repository visibility alone does not authorize copying code or media.

No OEM APK/DEX/Smali/decompiled method body, firmware, partition dump, proprietary database, recipe catalog, photographs, credentials or signing keys is included. Hashes and class/method names identify research artifacts without distributing their contents. Historical screenshots in device research show the original independent toolkit applications; current unified screenshots are separately identified.

Monsieur Cuisine, Silvercrest, Lidl, Android and other product names identify their respective subjects and owners. The independent SDK from [blackstufflabs.com](https://blackstufflabs.com) makes no claim of vendor affiliation, endorsement or approval.
