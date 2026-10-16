# Frequently Asked Questions

## 1. What is Monsieur Cuisine Developer SDK?

An independent Python and Kotlin toolkit for developing software around MCC and MCS protocols. Its native Digital Twin provides stateful virtual PowerBoards so you can test without the appliances. Start with [first steps](first-steps.md).

## 2. Is this an official Lidl or Silvercrest project?

No. BlackStuff Labs is an independent project with no claimed vendor affiliation or endorsement. See [license and attribution](../THIRD_PARTY_NOTICES.md).

## 3. What is the difference between MCC and MCS?

They are separate device models with different host apps, serial frames, fields, temperature tables and speed units. Select the matching [device profile](protocols.md); a common UI does not make the protocols interchangeable.

## 4. Do I need a real Monsieur Cuisine device?

No. The SDK, desktop and demo use synthetic state and need no appliance, original APK or firmware. Real hardware is outside the supplied transport implementation.

## 5. Can I use the SDK completely offline?

Yes, after obtaining Python/Tk and any build dependencies you need. The installed library, desktop and built demo run locally without an account or Internet connection. An offline wheel installation is covered in [setup](setup.md).

## 6. Does the Digital Twin run on Windows?

Yes. Native Tk, Python API, CLI, loopback and installed-wheel checks have run on Windows 11. Use a Python distribution with Tcl/Tk; see [setup](setup.md).

## 7. Does it work on Linux and macOS?

The codebase is portable Python/Tk and CI covers both platforms. Read [compatibility](compatibility.md) for actual executed results rather than treating a prepared workflow as verification. Linux may need a separate Tk package and display/Xvfb.

## 8. How do I switch between MCC and MCS?

Use **Device Model** at the top of the desktop. The old model is disarmed, clients and pending work are closed, and a fresh selected model is created. Save a recording before switching if you want to keep the session.

## 9. Can I develop an Android app?

Yes. The complete [`android/sdk`](../android/README.md) module exposes a common client, transport, mocks and two codecs. The debug demo shows integration with each virtual profile.

## 10. How do I connect Android Studio Emulator?

Enable Android Connection in the desktop, choose the same model in the demo and use host `10.0.2.2`. Defaults are MCC `8765` and MCS `8766`; custom ports must match. Follow the [Android guide](android.md).

## 11. Do I need a separate bridge application?

No. The optional localhost listener runs in the existing desktop process and shares its twin. It is disabled until explicitly enabled.

## 12. Does Android Connection require Internet?

No. The standard emulator host alias reaches the local computer. The desktop binds loopback; the connection is not a cloud service or LAN appliance endpoint.

## 13. Can I use Python without the GUI?

Yes. Import `DigitalTwin` or run `python -m monsieur_cuisine_sdk --headless`. Core use starts no Tk window or socket. See the [Python API](api.md).

## 14. How do I send a motor command?

Call `twin.start_motor(speed=2, direction="ccw", temperature=60)`, then `twin.advance(0.5)` to advance virtual time. The [first tutorial](first-steps.md) shows both profiles, telemetry and STOP.

## 15. How do I simulate a sensor error?

Use the desktop **Errors** or **Scale & Sensors** controls, or `twin.set_sensors(error_code=3)`. Error numbers retain their profile meaning; injection does not establish a physical interlock. See [faults and sensors](api.md#ownership-faults-and-lifecycle).

## 16. How can I view raw protocol packets?

Open **Protocol Monitor** for live TX/RX HEX. The [CLI](cli.md) can build, decode, inspect or analyze saved bytes without connecting to anything.

## 17. How do I run automated tests?

After installation, run `python -m unittest discover -s tests -v` from the source checkout. The full suite needs Tk/display; Linux CI uses Xvfb. [Testing](tests.md) also covers conformance, stress and Android checks.

## 18. How do I record and replay sessions?

Use **Settings → Save recording**, or `twin.save("session.json")` and `replay("session.json")`. Replay reconstructs deterministic inputs and checks bytes/state; it is not hardware verification. See [recording](recording.md).

## 19. Are simulated RPM and temperatures physically accurate?

They are configurable synthetic dynamics. MCC modeled RPM is not a measured motor curve, and MCS physical RPM conversion is unknown. Temperatures and braking behavior must not be used as calibrated appliance measurements.

## 20. Can I install my Android app directly on the real appliance?

This SDK does not provide or validate that procedure. Appliance privileges, signing, serial access, firmware compatibility and physical safety are separate unknowns. The demo is **Emulator/Test Use**; see [limitations](safety.md).

## 21. Can this SDK update appliance firmware?

No. Qualified OTA helpers inspect or generate offline frame shapes; there is no firmware validation, bootloader implementation or flasher.

## 22. Does the project include original firmware or proprietary recipes?

No. Supplied code and examples are independent; recipe-shaped examples are synthetic. Research references and artifact hashes do not distribute manufacturer contents.

## 23. How can I contribute?

Read [CONTRIBUTING.md](../CONTRIBUTING.md), reproduce an issue with a small synthetic example and state the selected profile and runtime. Do not upload OEM binaries, credentials or private device logs.

## 24. How can I support the project?

Use [BlackStuff Labs on Ko-fi](https://ko-fi.com/blackstufflabs). Support is optional; the SDK remains free and open source.

## 25. Why does motion continue after STOP?

STOP removes the requested output; the model retains finite synthetic braking. Observe actual speed until it reaches zero. An injected disconnected-link fault can also prevent an ordinary wire STOP; lifecycle disarm is a separate host policy.

## 26. Why are desktop START controls disabled while Android is connected?

The remote client owns the command lease. Disconnect it, or use desktop STOP to disconnect/disarm it. Host sensor and fault controls remain available.

## 27. Can an original manufacturer APK connect unchanged?

Compatible bytes do not replace its compiled serial or Binder transport. Integrate an app you control through an authorized source seam, such as this SDK; no OEM APK patch is supplied.

## 28. Why does MCC reject 40 °C or a duration?

The studied MCC temperature table lacks 40 °C and no wire duration field was identified. MCS has its own 40 °C entry and manual timer. Unsupported requests fail explicitly instead of fabricating protocol support.

## 29. What does a replay PASS prove?

The software inputs reproduce the stored bytes and checkpoints under that model. Recordings are not authenticated; editing both input and expectations can create another valid trace. It does not prove physical safety or firmware equivalence.

## 30. Where should I look when a command fails?

Start with [troubleshooting](troubleshooting.md), then check capabilities, selected model, units and the raw HEX monitor. [Evidence](evidence.md) distinguishes confirmed host behavior, inferred policy and unknown hardware details.
