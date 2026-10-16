> **Historical MCS profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../../index.md) and [current evidence and validation](../../../../evidence.md) for SDK 0.1.0.

# MCS and MCC comparison

Historical facts from the separate static dossiers; MCC is an architectural reference, never a runtime dependency.

| Aspect | MCC launcher292 | MCS 1.2.14.15 |
|---|---|---|
| package | de.silpion.mc2 | com.tecpal.device.mc30 |
| hardware service | separate :mc.machine_service / Binder | local serial service in default process |
| UART | ttyMT0 / 4800 | ttyMT1 / 9600 |
| operational TX/RX | 15 / 27 bytes | 39 / 48; legacy TX35 |
| envelope | MCC-specific PowerBoard format | AA / u16BE length / OB / subtype / sequence / sum |
| motor | separate MCC coding | UI0..10 → raw0..20; RPM UNKNOWN |
| recipes | localized JSON → DBRecipes | encrypted tgi-v6.db / richer entities |
| OTA | separate MCUpdater research | FE01..06 structures plus Android updater chain |

Common engineering concepts include controlled clocks, input recording, replay, test fixtures, evidence levels and GUI organization. This implementation uses original MCS code and standalone modules; no shared MCC transport or numeric tables are imported. An identical public Android signing certificate does not establish APK or hardware compatibility. Never convert MCS to MCC by swapping only the baud rate.
