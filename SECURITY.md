# Security scope

The SDK models software offline. Its optional development listener is disabled by default, accepts IPv4 loopback addresses only (127.0.0.0/8; the name `localhost` is mapped to 127.0.0.1) and grants one command owner. It does not provide authentication, an encrypted appliance transport or a physical hardware driver. The original additive checksums are error checks, not security mechanisms.

Security-relevant reports should include the selected profile, SDK version, minimal synthetic input, expected/actual behavior and affected bounds or lifecycle. Avoid posting credentials, real device identities, authenticated logs or proprietary artifacts. For a suspected private-data or exploitable defect, use an established private maintainer contact when one is available; no unverified contact address is invented here.

Relevant areas include malformed recordings, unchecked work/queue growth, stale session callbacks, profile confusion, unexpected network exposure and copied/mutable write buffers. Report platform/runtime and whether a reproduction uses the Python API, desktop, JVM client or Android runtime. Physical appliance or OEM firmware findings have a separate evidence/safety scope.

See [safety and limitations](docs/safety.md), [recording bounds](docs/recording.md) and [contribution rules](CONTRIBUTING.md). No claim of a completed independent security certification is made.
