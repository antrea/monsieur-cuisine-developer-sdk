> **Historical MCC profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../index.md) and [current evidence and validation](../../../evidence.md) for SDK 0.1.0.

# MCUpdater, Android updates and powerboard firmware

> **SDK 2.0 update:** the owner's full backup now supplies the actual updater
> and platform images. See [platform startup and updater evidence](platform-startup.md)
> for the newly identified files and static analysis. Artifact-absence statements
> below describe the earlier investigation only.

**No MCUpdater APK and no confirmed MCU firmware image were acquired in the research summarized here.** The client side present in MCLauncher build 292 was analyzed; its server-side update implementation was not. These are partial but useful results, not a completed reverse engineering of the missing updater.

## Components are different artifacts

| Component | Examined material | Limit |
|---|---|---|
| MCLauncher `de.silpion.mc2`, build 292 | Hash-identified original APK; managed code, resources, native serial wrappers | Only this APK version was analyzed as an application artifact |
| MCUpdater `de.silpion.mcupdater` | Binder interfaces, adapter and callers inside the launcher | External APK absent; version, signature, native code and installer unknown |
| `com.adups.tgifota` | External Activity reference and FOTA broadcasts/receiver in launcher | External APK and target update image absent |
| Android system | Custom property access and OEM service clients | No device system image acquired |
| Powerboard | Ordinary operational protocol and reported version field | No MCU model, firmware dump or bootloader identified |

The 11 Smali units under `de.silpion.mcupdater` in MCLauncher are client/interface support. Their namespace does not establish an embedded complete updater. `MCUpdateService` is not a local service implementation in the examined launcher manifest.

## Binder contract seen by the launcher

`BuildConfig` and `UpdateServiceAdapter` name external component **`de.silpion.mcupdater/de.silpion.mcupdater.MCUpdateService`**. The adapter starts and binds that explicit service. The service descriptor is `de.silpion.mcupdater.IUpdateService`.

| Transaction | Method | Application payload | Reply |
|---:|---|---|---|
| 1 | `registerStateCallback(IStateCallback)` | Nullable callback Binder | No return value; exception status |
| 2 | `unregisterStateCallback(IStateCallback)` | Nullable callback Binder | No return value; exception status |
| 3 | `getUpdaterState()` | None | Integer and exception status |
| 4 | `startCheck()` | None | No return value; exception status |

These proxy calls are synchronous (Binder flag 0). They are Android IPC transaction numbers, not UART or firmware opcodes. The observed application callers use callback registration and `startCheck`; no application consumer beyond generated support was found for the other two interface methods.

Callback descriptor `de.silpion.mcupdater.IStateCallback` exposes transaction 1 `onStateChanged(int,int)` and transaction 2 `onDownloadProgress(int)`. These are one-way calls (flag 1). The adapter dispatches the **second integer** of the state-change callback:

| Value | Listener name |
|---:|---|
| 0 | `idle()` |
| 1 | `checking()` |
| 2 | `updateAvailable()` |
| 3 | `downloading()` |
| 4 | `updateReady()` |
| 5 | `installing()` |
| Other | `unknown()` |

The log represents first-to-second state; interpreting the first as the previous state is reasonable but not an original parameter name recovered from source. This list does not establish permitted transitions or signature checks. Download progress is forwarded/logged as a percentage without a local validation proving a particular accepted range.

`getUpdateService(Context)` can return null before asynchronous binding completes. `onServiceConnected` creates the proxy and registers a callback; disconnect clears the proxy/binding guard. `SettingsFragment.h()` requests a check if connected and otherwise displays an error. The check button is re-enabled by the idle listener, while the local failure branch does not directly re-enable it. These are static control-flow observations, not runtime failure tests.

The inactivity path `n0.a(TextView)` can request a check and register `m0`, whose idle callback proceeds toward sleep. Idle does not prove that a check succeeded. The UI state `installing` or text announcing a reboot does not reveal the installer operation, file target or rollback mechanism.

## Documented public update catalogs

Two text catalogs were acquired on **16 October 2026**. Each contains APK filenames, one per line; neither contains firmware blocks, hashes, board model constraints or installation instructions.

| Public catalog | Listed launcher builds | Archived body SHA-256 |
|---|---|---|
| [mc20 historical catalog](https://mc20.monsieur-cuisine.com/666a60bc-0ce2-4878-9e3b-23ba3ceaba5a/versions.txt) | 208, 226, 231 | `bfbde6b289382afd9171c9da56c4e81bbb738ba428abbc9e6aa6cdaaf041f5ed` |
| [Simplexion catalog](https://update32.simplexion.pm/4b606313-3631-4d5f-a856-ca0edecf0c13/versions.txt) | 248, 266, 281, 285, 292 | `0fc1868cc172cd6b0c70694e6ff71b6b526301bc197cd166dd6e7c01469c7e3d` |

These hashes identify text bodies, **not the listed APKs**. Only launcher build 292 was analyzed as an acquired application artifact. A filename is not independent manifest verification of another listed version. The fact that 292 is the highest number in those catalogs does not establish the latest release across all channels.

The public [monsieurcc-rs](https://github.com/tuxuser/monsieurcc-rs) client documents a machine-configuration `updatelocation`, then `versions.txt`, then base/name URL construction. That is behavior of the Rust client; it is not proof of the missing MCUpdater's selection/download/install algorithm. MCLauncher declares `MachineConfigResponse.KEY_UPDATE_URL = updatelocation`, but the examined launcher consumer uses recipe configuration; use of that key by MCUpdater remains unproven. No machine-configuration request using a device serial was made.

`MCUpdate0.123.apk`, `MCUpdate0.124.apk` and `MCUpdate0.125.apk` appear in a Rust **test fixture**. They are not evidence of three publicly distributed MCUpdater versions. Targeted checks did not acquire those packages; inconclusive HTTP responses must not be treated as proof of absence.

## Powerboard-reported firmware version

The UI gets the number through `ICommandInterface.getFirmwareVersion()`, the IPC adapter, Binder, `IPCMachineBinder`, the hardware service and finally `PowerBoard.getFirmwareVersion()`. The last getter reads unsigned big-endian RX offsets **20–21** from the last valid status buffer. It sends no special firmware query or download.

The number 4924 converts arithmetically to bytes `13 3C`; 5016 converts to `13 98`. The first was a reported device value in the earlier investigation; the latter appears in a [public issue](https://github.com/EliasKotlyar/Monsieur-Cuisine-Connect-Hack/issues/36). Neither is a captured frame or acquired firmware image in this release. Numeric ordering does not establish replaceability, board revision or safe upgrades. The vendor's internal interpretation of the number is unknown.

`SettingsFragment` separately reads `ro.custom.build.version` for the Android build label and `PackageInfo` for the launcher version. Do not conflate those with the serial firmware number.

## MCU search and FOTA boundary

The prior search inventoried all 2,344 APK entries, inspected native sections, classified compressed data and large DEX arrays, and examined public research. It found no identified MCU payload or programming call chain. The three native libraries are JNI serial wrappers; the identified gzip is an OkHttp public-suffix list. This is **none identified in the examined corpus**, not proof against hidden, encrypted, runtime-generated or externally stored firmware.

The launcher refers to an ADUPS/tgifota Activity, permission-limited FOTA broadcasts and a receiver that changes LEDs. The name `install_other_image` does not identify the target partition or prove powerboard programming. The external implementation was not acquired.

No bootloader-entry, flash-erase, page-write, verification or MCU-reset procedure was identified. Operational STOP, SLEEP, tare and scale calibration must not be renamed as those operations. A frame's additive checksum is not a firmware CRC/signature check.

Open work includes updater artifact acquisition/provenance, installer/download/staging behavior, signature/rollback policy, firmware payload identification and board-model compatibility. This release implements none of those functions. Sources and code-unit references are U01–U03 in the [evidence ledger](research-methodology.md#evidence-ledger); see also [historical comparison](historical-comparison.md) and [limitations](safety-and-limitations.md).
