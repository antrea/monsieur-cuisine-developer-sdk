# Scientific and practical limits

This SDK is an offline software development environment. It does not open a real UART, control an appliance, install an OEM application, flash firmware or certify cooking/motor safety. The optional localhost bridge connects an application you develop to the in-process software model.

The codecs implement observed host formats for specific historical builds. Physical MCU firmware, braking/watchdog behavior, interlocks, electrical levels and safe repeated-start duty cycles were not verified. Application labels and static getters are evidence of host interpretation, not measurement of the mechanism.

Motor acceleration, coasting, reversal, thermal response, interlocks, default firmware values, noise and saturation are explicit synthetic hypotheses. MCC and MCS keep different native policies. A STOP removes a target; the model can continue coasting/cooling. Socket closure or a successful write is not physical acknowledgement. A stale RX can be structurally valid, and additive checksum agreement is not authentication.

MCC reports modeled RPM using illustrative targets. MCS has no established RPM conversion; retain raw level units. Recipe examples are newly written structures/tutorial data, not OEM content or a supported manufacturer importer. MCS OTA serialization/emulation exercises documented frame shapes only; firmware interpretation, validation, retry/success meaning and flashing remain unknown or unimplemented.

The default desktop opens no listener. Enabling Android Connection binds loopback and admits one owner. Queues, work budgets and generation checks protect local development responsiveness; they do not make the wire protocol secure for an exposed network. Hardware transport remains an explicitly separate integration task.

Public tests demonstrate deterministic implementation behavior under their tested inputs/platforms. They do not prove model fidelity, portability on unexecuted systems or compatibility with newer app builds. See [evidence](evidence.md), [validation](tests.md) and each [device profile](protocols.md) for precise scope.
