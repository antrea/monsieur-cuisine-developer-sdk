# Migration from the separate toolkits

## SDK 2.0 local branch changes

The development build is `2.0.0.dev0`, not a remote release. Python and Kotlin
high-level starts now default to CW. Specify CCW explicitly to preserve an old
call's direction. MCC host policy now caps heated/reverse speeds and requires
minimum STANDARD speed one; `parameters={"host_policy":"strict"}` rejects
adaptation, while raw `feed()` preserves wire experimentation. Old recordings
whose checkpoints encode earlier policy/model defaults may fail exact replay;
keep the originating SDK version for those traces rather than silently claiming
equivalent results. New recordings retain explicit policy/physics parameters.
See [host policy](mcc-oem-policy.md) for recipe conversion, calibration hypotheses
and the separate optional host timing model. `mc-sdk --model` stays unchanged;
`mc-backup` and `mc-usb` are separate interfaces for their specific local tools.

Monsieur Cuisine Developer SDK **0.1.0** is a new product. Earlier MCC/MCS Developer Toolkit 0.2.0 version labels remain historical provenance, not the unified package version.

Use one installation, GUI and CLI:

```sh
python -m pip install -e .
python -m monsieur_cuisine_sdk
mc-sdk --model mcc capabilities
mc-sdk --model mcs capabilities
```

## Namespace mapping

| Earlier API | Canonical location / replacement |
|---|---|
| `mcc_protocol.codec`, `.stream`, `.program`, `.simulator` | `monsieur_cuisine_sdk.profiles.mcc.protocol.*` |
| `mcc_powerboard_simulator.model`, `.scenarios`, `.recording`, `.mock`, `.virtual_serial`, `.server` | `monsieur_cuisine_sdk.profiles.mcc.simulation.*` |
| `mcc_tools.analyzer`, `.inspector` | `monsieur_cuisine_sdk.profiles.mcc.tools.*` |
| `mcs_protocol` and its typed/stream/schema modules | `monsieur_cuisine_sdk.profiles.mcs.protocol` |
| `mcs_digital_twin` headless model/board/API/scenario helpers | `monsieur_cuisine_sdk.profiles.mcs.simulation` |
| `mcs_tools.logs`, `.conformance` | `monsieur_cuisine_sdk.profiles.mcs.tools.*` |
| Independent legacy desktops and integrated listeners | One `monsieur_cuisine_sdk` GUI and `android_connection` around the common owner |
| Separate Android SDK/demo projects | `android/sdk`, `android/demo`, package `org.blackstufflabs.monsieurcuisine` |

Retained aliases refer to the same canonical module objects, preserving enum/class identity for ordinary headless helpers. They do not run a second model. The source tree retains no second legacy GUI or desktop controller. Legacy CLI modules enter the unified parser with an explicit profile; **use the new documented command syntax**, not an assumption that every old flag or executable remains compatible. Old script entrypoint names are replaced by `mc-sdk` and `monsieur-cuisine-digital-twin`.

## Behavior differences to preserve deliberately

- Model is explicit at `DigitalTwin` construction and in CLI/Android/recordings. Raw unknown-profile data never selects an actuator model.
- Common time is seconds. MCC native virtual milliseconds and MCS native dynamics are adapted without fabricating common wire fields.
- Common speed requests are profile UI levels. MCC observation is RPM; MCS is raw motor level, with `actual_rpm=None`.
- Temperature is an exact supported Celsius target. MCC has no 40 °C level or duration field; MCS has both its own 40 °C mapping and a bounded manual timer.
- Shared disconnect/model-switch removes targets and old transport state. The explicit legacy MCC TCP helper retains its older target policy while now clearing queued RX between clients.
- Common recordings use `monsieur-cuisine-recording-v1`, distinct from legacy formats. Model selection, faults and queue checkpoints are explicit. Legacy MCC selected-field checkpoint limitations remain historical.
- Error code values, calibration behavior, direction mapping, OTA and timer semantics remain profile-specific.

## Legacy examples and research

Current runnable examples are [`headless.py`](../examples/headless.py), [`record_replay.py`](../examples/record_replay.py) and [`inspect_frames.py`](../examples/inspect_frames.py), each accepting `--model`. Original synthetic recipe/scenario/log data remains under `examples/research/mcc` and `examples/research/mcs`, with its original format; it is not silently promoted to the unified recording/scenario schema.

Historical protocol/application documentation is retained under `docs/devices`. Banners identify earlier APIs, command lines, screenshots and counts. Relative links were rewritten through source-to-destination mappings. Missing earlier audit links point to the evidence-backed [current audit page](evidence.md). Old publication guides and unverified release-success claims were not imported as current instructions. Research facts still retain original class/method/build anchors and attribution.
