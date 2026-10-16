> **Historical MCC profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../index.md) and [current evidence and validation](../../../evidence.md) for SDK 0.1.0.

# Research methodology and provenance

This release consolidates an existing static/offline investigation conducted on **16 October 2026**, rather than repeating device reverse engineering. Public source code, documentation, examples and tests were written for this toolkit. The reference APK, decompiled source, images, native libraries, original recipe content and raw private research logs are **not distributed**.

## Reference artifact

| Property | Recorded result |
|---|---|
| Artifact name | `MCLauncher-release-1.1.28-292.apk` |
| Package | `de.silpion.mc2` |
| Version | `1.1.28-release`, versionCode 292 |
| File size | 408,172,777 bytes |
| SHA-256 | `5e9125bb5e618e8eb989bfff8096f09cbad5e4fd3e5b08768fd624f36efc0482` |
| ZIP inventory | 2,344 entries |
| SDK declarations | min 23, target 27 |
| Native ABIs | `armeabi-v7a`, `arm64-v8a`, `x86` |
| Recorded acquisition source | [Public Simplexion update path](https://update32.simplexion.pm/4b606313-3631-4d5f-a856-ca0edecf0c13/MCLauncher-release-1.1.28-292.apk) |

CRC checks, internal DEX integrity and the v1/JAR signature were checked in the prior investigation. v2/v3 signatures were absent. The certificate SHA-256 was `c8a2e9bccf597c2fb6dc66bee293fc13f2fc47ec77bc6b2b0d52c11f51192ab8`, matching the public Android Platform certificate. A valid signature under that certificate does not establish exclusive vendor authorship; some META-INF metadata was outside v1 coverage. Byte identity with the APK installed on a particular appliance was not established.

The archive is an artifact identifier for researchers who lawfully possess their own copy, not a dependency of the toolkit. Nothing in the public package needs to download or execute it.

## Evidence classes

| Class | Meaning | Example |
|---|---|---|
| Static observation | Explicit code/data behavior in the hash-identified artifact | TX byte 3 uses `C6` for Turbo |
| Offline observation | Execution of an isolated representation or this original toolkit | A synthetic weight vector decodes to a negative integer |
| Historical reference | A claim in earlier public research, retained with source and scope | Older wording describes `C6` as a single turn |
| Inference | Reasoning consistent with observations, without full implementation proof | Low-level motor regulation likely occurs beyond the Android serializer |
| Unknown / not identified | A boundary the examined corpus does not answer | Controller watchdog or byte 24 semantics |
| Synthetic hypothesis | A chosen test/simulator behavior | Instantaneous virtual stopping or an illustrative RPM point |

“High static confidence” concerns fidelity to the examined host mapping. It does not upgrade a field name, UI label or simulator transition into a physical guarantee. Negative findings are bounded: “none identified in the examined corpus” is not a universal absence claim.

## Evidence ledger

Every row below is tied to the reference APK SHA-256 above unless an external reference is named. These are reproducible **class/method anchors**, not distributed proprietary source excerpts. Short obfuscated method names need their containing class and overload/descriptor when reproducing the analysis.

| ID | Class / method or artifact anchor | Fact supported |
|---|---|---|
| P01 | `machineAdapter.impl.hal.PowerBoard`: `getSendPayload()[B`, `areDataCorrect([B)Z`, numeric/status/scale/error getters | 15/27-byte layouts, opcode mapping, checksums, endian/signed conversions, byte 24 unknown |
| P02 | `machineAdapter.impl.service.HardwareMachineService`: constructor, `onStartRequested(IIII)V`, `onStopRequested()V` | Device/baud, work-mode translation, direction mapping and STOP state |
| P03 | Same class: `onPerformPeriodicHardwareAction()V`, `onProcessSensorData(Lim;)V` (raw DEX descriptor); `defpackage.gm` loop/callback paths | Latest-state send, tare handling, sensor/error conversion and nominal 100 ms loop |
| P04 | `android_serialport_api.SerialUtils`: `send([B)V`, `getDeviceData()[B`; inner `SerialUtils.b.run()V` | Logged write errors, cached samples, fixed-block reader and 500 ms sleep |
| P05 | `cooking.CookingManager`: `startCooking`, `pauseCooking`, `resumeCooking`, `stopCooking`, validation `i`, minimum-speed `a`, cyclic `b.onTick`; `cooking.Limits`; `model.Presets`; `fragment.MainFragment` Turbo paths | Cooking states, software limits, presets, timing and UI gates |
| A01 | `AndroidManifest.xml`; `de.silpion.mc2.BuildConfig` | Package/component declarations, shared UID request, build flavor and version |
| A02 | `application.App.onCreate()`, `activity.MainActivity.onCreate(...)`, `helper.LayoutHelper` | Initialization, lifecycle and navigation |
| A03 | `MachineAdapterFactory.createMachineAdapter(...)`, `IPCMachineAdapter`, `IPCMachineBinder`, `ClientService` | Adapter choice, Binder command and callback boundaries |
| A04 | `db.model.DaoMaster`, `db.DbHelper.createSession(...)` and upgrade helper | `Recipes`, greenDAO schema 9, table set and reimport-style upgrade |
| A05 | `db.model.RecipeDao`, `StepDao`, `MachineValuesDao` | Relational recipe/step/value fields and recipe reverse persistence |
| A06 | `ImportRecipesAndImagesTask`, `RecipeAssetsHelper`, `RecipeImportService` | Localized import, image naming/storage and incremental synchronization |
| A07 | `mcapi.json.recipes.Recipe`, `GuidedCooking`, `Step`, `MachineValues`; `SharedPreferencesHelper` | JSON nesting/field types and preference-schema distinction |
| U01 | `de.silpion.mcupdater.UpdateServiceAdapter`, `IUpdateService` Stub/proxy, `IStateCallback` Stub/proxy | External service identity, transactions, callback dispatch and state names |
| U02 | `fragment.SettingsFragment.h()V`, `defpackage.n0.a(...)`, `defpackage.m0`, `FOTAReceiver`, `defpackage.o0` | Manual/inactivity update paths and separate FOTA references |
| U03 | `PowerBoard.getFirmwareVersion()I`, corresponding hardware/Binder getters and `SettingsFragment` | Unsigned firmware number from RX 20–21, separate from custom Android and APK versions |

Decompiler display aliases such as `defpackage.im` need not match the raw DEX descriptor (`Lim;` here). Preserve that distinction when reproducing a callsite; neither is a file byte offset.

### Recorded derived-file fingerprints

These SHA-256 values identify the original investigation's specific derived files, as recorded in its evidence catalog. Decompiled text is tool-dependent and is not the vendor's original source. The files themselves are excluded from this public release; hashes provide provenance without redistributing their content.

| Derived representation | Recorded SHA-256 |
|---|---|
| `PowerBoard` JADX Java | `d7f660e599c2464f41fa8e1cc73141c05e35302a1662ed4c5ad523295efbc02b` |
| `PowerBoard` Apktool Smali | `78a8c1d7f43d11c9f74d3ae9cb96d783abac027f133263ddbf6f229f1c35ac1e` |
| `HardwareMachineService` JADX Java | `ee3c30a77137b6bc047ccd1b67c161ec98b72d9089dedc177b521b262da39c16` |
| `SerialUtils` JADX Java | `ae45b4a1637f61a335f4c8fe841820a49123c6d80207244845ad0e55a2eed7b0` |
| `SerialUtils$b` Apktool Smali | `d5ee78bc622bf5660c95ec1dce44cfddeaf89ca5adfd536254e1630fb5d07752` |
| `DaoMaster` JADX Java | `e9812926bb081fc551a2e308c1aff32eb2ec020653f1c268d5c77fbed9fa3441` |
| `DbHelper` JADX Java | `6f03e88e183964843f11466d19352e31e5a659ec967c829fe93f32138c3ae791` |
| JSON `Recipe` model JADX Java | `7c5b01545c319ccfda4e1c844fd4dc687ae14aaa936693f791e363b2f65cf979` |
| `UpdateServiceAdapter` JADX Java | `f66daa0e45af4ee251c312b16c9d6452e8a2c48599de5e0b04ae19161179b35a` |
| `IUpdateService` JADX Java | `e738f2513e1f9493676fed76189599265cf5d2923914be63571642a333c7cd88` |
| `IStateCallback` JADX Java | `8faad1ab28948df27c80a4935d26a62716af3cb1569721f8317338fb96230447` |

### Recorded DEX callsites

| Target | Caller | `classes.dex` code-unit offset | Target method index |
|---|---|---:|---:|
| `PowerBoard.getSendPayload()[B` | `HardwareMachineService.onPerformPeriodicHardwareAction()V` | 15 | 34244 |
| `IUpdateService.startCheck()V` | `fragment.SettingsFragment.h()V` | 27 | 21451 |
| `IUpdateService.startCheck()V` | `n0.a(Landroid/widget/TextView;)V` | 147 | 21451 |

Offsets are **DEX code units relative to the calling method**, not absolute APK file offsets, byte offsets or Java line numbers. Recorded REA evidence IDs are `ev_494faee8abfe12f526a4b36987a04db1a3c6c1fbdc4eab50a60a14b1a0dfee53` for the payload xref and `ev_3c02e06fb5e40931813ded005def2af11609ad39fe4602213181c5f4fdae840f` for the corrected firmware getter inspection. Direct callsite coverage does not establish all dynamic/reflection paths.

## Tools, representation limits and earlier tests

The prior work used Apktool/Smali, JADX, AAPT, apksigner, REA 6.5.0 with JADX headless MCP 0.7.1, and static ELF/disassembly tools. The headless JAR's recorded SHA-256 was `6e5eacf500b64292bfb73c49797c1958f6ee44646e43e868039ae7feb573ff75`. The provider reported source revision `5844800a486d2248fa949b74c9896285f5b54de2`.

JADX produced 2,732 Java files and reported 12 errors. Apktool produced a complete Smali inventory for the decode. REA's Android output uses JADX; agreement between the two Java presentations is not an independent decompilation proof. A real example was the serial reader's misleading Java catch/return representation, resolved against Smali. Provider status “complete” means text was delivered, not that the text is compilable or semantically correct.

The earlier private investigation reports 2,560 serializer vectors and 29,739 assertions for an isolated decompiled `PowerBoard` representation, 23 intermittent-model tests and 3 independent regressions. Those counts describe **earlier research**, not tests copied into or newly passed by this repository. The public suite is an independent implementation with its own recorded results. See the release audit and [README](../../../../README.md) for actual public-run commands/results.

An earlier unsigned resource/Smali rebuild demonstrated an offline packaging roundtrip only. It did not demonstrate installability, native alignment correctness, runtime privileges or device safety. No APK or code from that rebuild is shipped here.

## Reproducing public results

The repository's tests, examples, parser and simulator require only the public files and Python 3.11+. Run from the repository root:

```sh
python -m unittest discover -s tests -v
```

The [API](api.md) and [README](../../../../README.md) document executable examples. All frames in them are synthetic. Researchers comparing another lawful artifact should record its exact hash, distinguish source representations, preserve unknown fields, and qualify every difference by build. Do not silently apply this build's mapping to another device variant.

For external research attribution and observed licensing status see [third-party references](../third-party-references.md). The [historical comparison](historical-comparison.md) separates prior findings from this build's extensions.
