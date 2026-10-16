> **Historical MCC profile research.** Retained from the separate legacy toolkit. Protocol/build facts retain their stated evidence scope; API names, commands, dependency versions, screenshots and prior test counts below describe that earlier product. Use the [current unified documentation](../../../index.md) and [current evidence and validation](../../../evidence.md) for SDK 0.1.0.

# Board and Android error codes

The response exposes **two separate fields**: an error-detected flag at offset 3 bit 4 (`10`) and a raw board error code at offset 5. `PowerBoard.getError()` and `HardwareMachineService.onProcessSensorData()` translate that information into Android's internal error representation. Sources are ledger P01/P03 in [research methodology](research-methodology.md#evidence-ledger).

| Raw board code | Meaning in the examined application | Android IPC code |
|---:|---|---:|
| 1 | Serial-port communication | 1 |
| 3 | Power input overvoltage | 2 |
| 4 | Power input undervoltage | 3 |
| 5 | Motor error | 4 |
| 6 | No water | 5 |
| 7 | Motor overheat | 12 |
| 8 | Maximum runtime exceeded | 13 |
| Any other, with error flag set | Undefined / unmapped board error | 6 |
| Any code, with error flag clear | No active board error according to this flag | 0 |

The numbering intentionally skips board code 2. It is not mapped to overvoltage and should not be invented as a missing error. Code 0 is likewise not an independently confirmed board error when the flag is set: it follows the undefined mapping. Retain the raw byte even when the flag is clear.

## Related state conditions

| Condition | Android observation | What it does not establish |
|---|---|---|
| Scale overload | Contributes Android code 7 through scale-state handling | Not a raw board error code 7; board code 7 means motor overheat |
| Lid open | Dedicated RX bit and callback to UI | Not a unique board error code |
| Bowl NTC detected | Dedicated RX bit and getter | Not a demonstrated complete bowl-presence guard |
| `NO_BOWL_DETECTED` constant | Android IPC constant 8 exists | No assignment from the examined sensor mapping was identified |

Do not merge all flags into the raw error byte. A client needs the separate scale/lid state as well as the board error to represent the observed interface faithfully.

## Communication failure is not one mechanism

Board error 1 is **reported by the board**. It is not evidence that Android has an independent timeout based on receive age. No such host freshness timeout was identified in the original serial path. Conversely, `SerialUtils.send()` catches a write `IOException` and logs it without passing an error through the normal UI command result. A missing frame, a checksum failure, a Binder exception and board error 1 are different events.

The public parser reports malformed input as a parsing error; it does not synthesize a genuine board error. The simulator's injected error flags and board codes are explicitly synthetic. Neither demonstrates a physical fault cause, recovery behavior, watchdog or safe restart policy. See [timing and state](timing-and-state.md) and [safety and limitations](safety-and-limitations.md).
