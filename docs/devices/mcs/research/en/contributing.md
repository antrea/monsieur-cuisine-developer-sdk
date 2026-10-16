> **Historical MCS profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../../index.md) and [current evidence and validation](../../../../evidence.md) for SDK 0.1.0.

# Contributing

Install editable, run unittest discovery, conformance and scripts/audit_public.py before proposing changes. Add a targeted regression test for a real codec/model defect. Keep the runtime standard-library-only and keep Tk out of SDK/headless imports. Avoid global tools/configuration changes in contributor scripts. CI targets three OS families; report actual execution separately from configuration.

Attach evidence level and build provenance to factual protocol changes. Preserve raw unknown fields. Do not add guessed RPM, MCC tables, ACK guarantees or undocumented firmware CRC as facts. Model improvements should state equations, units, defaults and reproducibility implications; bump recording format when semantics become incompatible.

Contribute only code/data you may redistribute. Do not attach APK/DEX/Smali/decompiled methods, firmware, databases, recipe catalogs, serial identifiers, credentials or private paths. Public references can describe research without copying source. This repository's MIT grant covers original contributions, not third-party artifacts. Use synthetic minimal traces for regression cases.

GUI changes must preserve main-thread widget access, responsive after scheduling and graceful close. Run the actual Tk tests where a display exists; a skipped test is not evidence of GUI success. Keep the English guides and machine specifications synchronized. The protocol table test detects drift between SDK FieldSpec and JSON.
