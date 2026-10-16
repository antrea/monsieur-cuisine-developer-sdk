package org.blackstufflabs.monsieurcuisine.profiles.mcc

import java.io.IOException

class MccProtocolException(message: String) : IOException(message)

/** Android-facing direction values; TX wire byte 11 is the inverse. */
enum class Direction(val androidValue: Int) { COUNTER_CLOCKWISE(0), CLOCKWISE(1) }
enum class Operation(val wire: Int) {
    STOP(0), STANDARD(1), STEAM(3), TOAST(4), KNEAD(5), SLEEP(15), TURBO(198)
}

/** All values are decoded observations. No sequence, timestamp or ACK is on wire. */
data class MccState(
    val rawHex: String, val status: Int, val motorHeaterState: Int,
    val motorOn: Boolean, val heaterOn: Boolean, val scaleStable: Boolean,
    val direction: Direction, val errorDetected: Boolean, val errorCode: Int,
    val androidErrorCode: Int, val aboveTargetTemperature: Boolean,
    val bowlNtcDetected: Boolean, val lidOpen: Boolean, val extendedState: Int,
    val targetSpeedLevel: Int, val targetRpm: Int, val actualRpm: Int,
    val targetTemperatureLevel: Int, val targetTemperature: Int, val actualTemperature: Int,
    val weight: Int, val firmwareVersion: Int, val scaleStateRaw: Int,
    val scaleState: String, val calibrationStep: Int, val unknownByte24: Int,
    val warnings: List<String>
) {
    val targetSpeedLevelSigned get() = if (targetSpeedLevel < 128) targetSpeedLevel else targetSpeedLevel - 256
    val targetTemperatureLevelSigned get() = if (targetTemperatureLevel < 128) targetTemperatureLevel else targetTemperatureLevel - 256
    val unknownByte24Signed get() = if (unknownByte24 < 128) unknownByte24 else unknownByte24 - 256
    val androidScaleState get() = if (scaleState == "not_available") "overload" else scaleState
    val actualSpeedLevel get() = MccCodec.actualSpeedLevel(actualRpm)
}

object MccCodec {
    val temperatureLevels = listOf(0, 37, 45, 50, 55, 60, 65, 70, 75, 80,
        85, 90, 95, 100, 105, 110, 115, 120, 125, 130)
    private val errorMap = mapOf(1 to 1, 3 to 2, 4 to 3, 5 to 4, 6 to 5, 7 to 12, 8 to 13)
    fun checksum(bytes: ByteArray): Int = bytes.fold(0) { total, byte -> (total + (byte.toInt() and 255)) and 255 }
    fun hex(bytes: ByteArray): String = bytes.joinToString(" ") { "%02X".format(it.toInt() and 255) }
    fun parseHex(text: String): ByteArray {
        val compact = text.filterNot { it in " \t\r\n\u000B\u000C" }
        require(compact.isNotEmpty() && compact.length % 2 == 0 && compact.all { it in "0123456789abcdefABCDEF" })
        return ByteArray(compact.length / 2) { compact.substring(it*2, it*2+2).toInt(16).toByte() }
    }
    fun encodeTx(operation: Operation = Operation.STOP, speed: Int = 0, temperatureLevel: Int = 0,
                 direction: Direction = Direction.CLOCKWISE, tare: Boolean = false): ByteArray {
        require(speed in 0..10) { "speed must be 0..10" }
        require(temperatureLevel in 0..19) { "temperature level must be 0..19" }
        val raw = byteArrayOf(0x55, 15, 0xA1.toByte(), operation.wire.toByte(),
            (if (tare) 0xA9 else 0).toByte(), speed.toByte(), temperatureLevel.toByte(),
            0, 0, 0, 0, (1-direction.androidValue).toByte(), 0, 0, 0xAA.toByte())
        raw[13] = checksum(raw.copyOfRange(0, 13)).toByte()
        return raw
    }
    fun validate(raw: ByteArray, expectedSize: Int? = null) {
        val size = raw.size
        if (size !in listOf(15, 27) || (expectedSize != null && size != expectedSize))
            throw MccProtocolException("frame length")
        if ((raw[0].toInt() and 255) != 0x55 || (raw[1].toInt() and 255) != size)
            throw MccProtocolException("header/length byte")
        if ((raw[2].toInt() and 255) != if (size == 15) 0xA1 else 0xB1)
            throw MccProtocolException("frame type")
        if ((raw.last().toInt() and 255) != 0xAA) throw MccProtocolException("terminator")
        if ((raw[size-2].toInt() and 255) != checksum(raw.copyOfRange(0, size-2)))
            throw MccProtocolException("checksum")
    }
    fun actualSpeedLevel(rpm: Int): Int {
        if (rpm <= 0) return 0
        val upper = intArrayOf(558, 1008, 1437, 3359, 6349, 9309, 12312, 15315, 18232)
        return upper.indexOfFirst { rpm <= it }.let { if (it < 0) 10 else it+1 }
    }
    fun decodeRx(raw: ByteArray): MccState {
        validate(raw, 27)
        fun u(index: Int) = raw[index].toInt() and 255
        fun word(index: Int) = (u(index) shl 8) or u(index+1)
        val status = u(3); val mode = status and 3; val error = status and 16 != 0
        val warnings = mutableListOf<String>()
        if (u(6) > 10) warnings += "Target speed level exceeds 0..10"
        if (u(11) > 19) warnings += "Target temperature level exceeds 0..19"
        if (u(4) !in listOf(0, 3, 4, 5)) warnings += "Unknown extended state"
        if (error && u(5) !in errorMap) warnings += "Unmapped error; Android fallback 6"
        if (!error && u(5) != 0) warnings += "Error byte set without error flag"
        if (u(22) and 248 != 0) warnings += "Unknown scale bits"
        if (u(22) and 7 == 0) warnings += "No scale flags; Android fallback overload"
        if (u(23) !in listOf(0, 1, 2, 3, 4, 5, 7)) warnings += "Unknown calibration step"
        val scale = when { u(22) and 4 != 0 -> "overload"; u(22) and 1 != 0 -> "calibration"
            u(22) and 2 != 0 -> "normal"; else -> "not_available" }
        val weight = (u(16) shl 24) or (u(17) shl 16) or (u(18) shl 8) or u(19)
        return MccState(hex(raw), status, mode, mode in listOf(1,3), mode in listOf(1,2),
            status and 4 != 0, if (status and 8 != 0) Direction.CLOCKWISE else Direction.COUNTER_CLOCKWISE,
            error, u(5), if (error) errorMap[u(5)] ?: 6 else 0, status and 32 != 0,
            status and 64 != 0, status and 128 != 0, u(4), u(6), word(7), word(9),
            u(11), word(12), word(14), weight, word(20), u(22), scale, u(23), u(24), warnings.toList())
    }
}

/** Bounded incremental framing; keep at most 26 incomplete bytes between calls. */
class MccStreamParser(private val expectedSize: Int = 27) {
    init { require(expectedSize == 15 || expectedSize == 27) }
    private val buffer = ArrayList<Byte>(27)
    private val issueBuffer = ArrayDeque<String>()
    val bufferedBytes get() = buffer.size
    var discardedBytes = 0L; private set
    var protocolIssueCount = 0L; private set
    val issues: List<String> get() = issueBuffer.toList()
    fun reset() { buffer.clear(); issueBuffer.clear() }
    private fun reject(message: String) {
        protocolIssueCount++
        if (issueBuffer.size == 64) issueBuffer.removeFirst()
        issueBuffer.addLast(message)
        buffer.removeAt(0); discardedBytes++
    }
    fun feed(data: ByteArray): List<ByteArray> {
        val frames = mutableListOf<ByteArray>()
        for (value in data) {
            buffer.add(value)
            while (buffer.isNotEmpty()) {
                if ((buffer[0].toInt() and 255) != 0x55) { reject("garbage"); continue }
                if (buffer.size < 2) break
                val size = buffer[1].toInt() and 255
                if (size != expectedSize) { reject("unexpected length"); continue }
                if (buffer.size < 3) break
                val type = if (size == 15) 0xA1 else 0xB1
                if ((buffer[2].toInt() and 255) != type) { reject("unexpected type"); continue }
                if (buffer.size < size) break
                val candidate = buffer.take(size).toByteArray()
                try { MccCodec.validate(candidate, expectedSize) }
                catch (error: MccProtocolException) { reject(error.message ?: "invalid frame"); continue }
                frames.add(candidate); buffer.subList(0, size).clear()
            }
        }
        return frames
    }
}

