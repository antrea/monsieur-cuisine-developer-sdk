> **Historical MCS profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../../index.md) and [current evidence and validation](../../../../evidence.md) for SDK 0.1.0.

# Tutorial: test a client without a robot

1. Run `python examples/sdk_roundtrip.py`. Observe that the first response has zero actual motor level even though target speed is3: acceleration takes virtual time.
2. Change `twin.advance(3)` to0.2 in your own copy. The motor reaches only a fraction of target. Decode RX rather than assuming TX implies immediate motion.
3. Inject `twin.sensors(lid_open=True)`, advance one second and query. The default artificial interlock decelerates toward zero while preserving the requested target. Clear the sensor and advance to observe resumption.
4. Set `twin.faults(drop_next=1)` before a manual frame. `transact` returns None while the command is applied. A client should distinguish missing feedback from proof of no action. This is a model test case, not a claim of real retry/deduplication behavior.
5. Enable `record=True`, use only facade methods, then call `replay(twin.recording)`. Response bytes and snapshots must match. An edited expected result causes an explicit mismatch.
6. Encode the same exercise as JSON events using examples/lid-fault.json as a template. Add final-state expectations and run in CI without a display.

For a new client, inject InMemoryTransport instead of opening an OS device. Build frames with SDK and decode returned bytes. You can replace encode_manual in check_vectors with your implementation. Keep model assumptions separate from wire conformance in tests: the former checks your algorithm under chosen conditions, the latter checks bytes against historical software evidence.
