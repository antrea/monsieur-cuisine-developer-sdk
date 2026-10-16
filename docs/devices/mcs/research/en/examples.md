> **Historical MCS profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../../index.md) and [current evidence and validation](../../../../evidence.md) for SDK 0.1.0.

# Executable examples and resources

From the checkout root after installing the package:

```sh
python examples/sdk_roundtrip.py
python examples/record_replay.py
python examples/stream_recovery.py
python examples/ota_offline.py
python -m mcs_tools scenario examples/reversal.json
python -m mcs_tools scenario examples/thermal.json
python -m mcs_tools scenario examples/lid-fault.json
python -m mcs_tools scenario examples/intermittent.json
python -m mcs_tools scenario examples/link-faults.json
```

All Python examples assert their central result. The reversal scenario starts a motor/heater, injects mass, tares, reverses and stops. Thermal observes heating then cooling after timer expiry. Lid-fault demonstrates the configured artificial interlock. Intermittent applies explicit on/off commands; it does not claim the original Android kneading schedule. Link-faults drops and delays replies while commands still apply.

`fixtures/telemetry.jsonl` is a wholly synthetic bidirectional capture. `fixtures/conformance-900.json` freezes 300 manual, 300 operation and 300 OTA encoder cases. `fixtures/envelope-reference-900.json` regenerates the exact seeded random payloads previously compared with the recovered envelope method: 150 each of lengths 2,18,26,30,39,260. These arbitrary payloads are envelope tests, not semantically valid operation commands. No captured private hardware traffic is shipped. `examples/synthetic-recipe.json` is a tutorial format, not an OEM recipe importer.

Use `check_vectors(rows, manual=your_encoder, ...)` from `mcs_tools.conformance` to check another implementation against the typed argument fixtures. Golden frames constrain bytes; self-generated roundtrips alone do not establish independent correctness. The historical source comparison only establishes the envelope/checksum implementation, not every controller behavior.
