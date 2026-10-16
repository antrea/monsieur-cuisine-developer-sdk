> **Historical MCS profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../../index.md) and [current evidence and validation](../../../../evidence.md) for SDK 0.1.0.

# Scope and limitations

- **CONFIRMED_IN_APK:** historical wire structures, constants, serializer behavior and getter signedness. An acquired APK is not a certification of every hardware revision.
- **INFERRED:** all virtual dynamics, interlocks, overload threshold, heater law, watchdog option, reply timing/counter, turbo fallback, LED echo and OTA return=0 policy.
- **UNKNOWN:** physical RPM, electrical UART details, actual MCU/ISA/image, bootloader, packetKey and firmware CRC semantics, retry, final verification, complete return codes and special-program schedules.
- **HARDWARE_VERIFIED:** none.

The board recognizes operational 0801/02/03 and shape-only OTA 01/02/03/04/06. 0805 and additional registered families are raw-decodable but behavior is not modeled. Scale calibration other than tare is rejected. Query is a model snapshot; repeated sequence values are not deduplicated. RX sequence is independent. Signed raw fields can represent values the model never generates. Profile detection reports layout compatibility, not an app version.

Thermal coefficients are not calibrated to water, vessel, mass or ambient airflow. Motor levels are not torque or RPM. Interlocks can retain targets and later resume; timer pauses under modeled blockage. These choices are documented for testing applications and do not predict safe real operation. No physical-device transport, serial device adapter, flasher, certified OEM replacement app, proprietary firmware or paid recipe integration exists in the distribution.

The toolkit runs offline after installation. Build tools may require initial download unless available locally. Tk availability/display differs by platform. Local execution covers Windows/Python3.12.14; other matrix combinations await CI. Timeline and diagnostics are bounded; full recordings and imported scenario/log files can grow, so process trusted reasonable-sized files. Cross-platform floating-point exactness is not certified.

The public evidence register retains hashes, methods and synthetic inputs rather than proprietary sources. Repeating the private serializer comparison requires lawful access to the original research corpus; normal tests never require it. The automated audit detects common issues but does not replace attribution/licensing review. Historical community links may change independently of the release.
