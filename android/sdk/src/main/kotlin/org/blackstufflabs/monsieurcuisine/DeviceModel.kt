package org.blackstufflabs.monsieurcuisine

enum class DeviceModel(val defaultPort: Int) { MCC(8765), MCS(8766) }
enum class MotorDirection { CLOCKWISE, COUNTER_CLOCKWISE }
enum class SpeedUnit { RPM, RAW_MOTOR_LEVEL }
enum class ConnectionState { DISCONNECTED, CONNECTING, CONNECTED, FAILED }

data class Capabilities(
    val model: DeviceModel,
    val temperaturesC: List<Int>,
    val supportsDuration: Boolean,
    val observedSpeedUnit: SpeedUnit,
    val telemetryRequiresQuery: Boolean,
    val maximumDurationSeconds: Int,
    val physicalTransportImplemented: Boolean = false
)

/** An observed frame. Socket success is never a physical action acknowledgment. */
data class DeviceState(
    val model: DeviceModel,
    val rawHex: String,
    val sessionGeneration: Long,
    val receivedAtNanos: Long,
    val observedSpeedValue: Double,
    val observedSpeedUnit: SpeedUnit,
    val direction: MotorDirection,
    val actualTemperatureC: Int,
    val targetTemperatureC: Int,
    val weightGrams: Double?,
    val lidOpen: Boolean,
    val ntcPresent: Boolean,
    val errorCode: Int,
    val errorName: String,
    val firmware: Int,
    val rawFields: Map<String, String>
)

data class FrameEvent(val model: DeviceModel, val sessionGeneration: Long, val direction: String, val hex: String)
