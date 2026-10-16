> **Historical MCS profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../../index.md) and [current evidence and validation](../../../../evidence.md) for SDK 0.1.0.

# FAQ

**Is this the latest MCS protocol?** It targets the acquired historical1.2.14.15 layout. Newer versions/hardware are unverified. detect_profile identifies compatible layout only.

**Can I control my appliance?** No real transport is shipped. This is an offline development environment. Matching wire bytes does not establish safe physical operation.

**Is the twin the original firmware?** No. It evolves original synthetic motor/thermal/scale models and encodes genuine documented response shapes. MCU firmware has not been acquired.

**Why no RPM?** No verified conversion from MCS raw level to RPM exists in this evidence set.

**Does a repeated sequence acknowledge or deduplicate?** Neither is established. The model accepts repeats and uses its own RX counter.

**Why are some valid opcodes rejected?** Raw decoding and behavior modeling have different scopes. Registered CookStatus/Scale/Version families and0805 are retained raw; unknown semantics are not invented.

**Can I run headless without Tk?** Yes: import SDK/API or run --headless. Tk is imported only for desktop/telemetry GUI. A missing display skips GUI tests explicitly.

**Does installation require Internet?** Pip may fetch setuptools; preprovision it for offline installation. Runtime simulation has no networking dependency.

**Can I publish my traces?** Review provenance and privacy first. Only synthetic traces are included here. The audit is a heuristic; it does not certify third-party redistribution rights.

**Where are recipes and the APK?** Deliberately outside the public release. The synthetic recipe is an original tutorial object, not an OEM catalog.
