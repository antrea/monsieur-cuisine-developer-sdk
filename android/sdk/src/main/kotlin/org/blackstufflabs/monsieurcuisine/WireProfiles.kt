package org.blackstufflabs.monsieurcuisine

import org.blackstufflabs.monsieurcuisine.profiles.mcc.MccCodec
import org.blackstufflabs.monsieurcuisine.profiles.mcc.MccStreamParser
import org.blackstufflabs.monsieurcuisine.profiles.mcc.Direction as MccDirection
import org.blackstufflabs.monsieurcuisine.profiles.mcc.Operation as MccOperation
import org.blackstufflabs.monsieurcuisine.profiles.mcs.McsCodec
import org.blackstufflabs.monsieurcuisine.profiles.mcs.McsStreamParser
import org.blackstufflabs.monsieurcuisine.profiles.mcs.Operation as McsOperation

internal interface FrameParser {
    fun feed(data: ByteArray): List<ByteArray>
    fun expire(): List<ByteArray> = emptyList()
}
internal data class RequestedOperation(
    val running: Boolean = false, val speed: Int = 0,
    val direction: MotorDirection = MotorDirection.CLOCKWISE,
    val temperatureC: Int = 0, val durationSeconds: Int = 0
)
internal object WireProfiles {
    fun capabilities(model: DeviceModel) = when(model) {
        DeviceModel.MCC -> Capabilities(model, MccCodec.temperatureLevels.toList(), false, SpeedUnit.RPM, false, 0)
        DeviceModel.MCS -> Capabilities(model, McsCodec.temperatures.toList(), true, SpeedUnit.RAW_MOTOR_LEVEL, true, 5940)
    }
    fun parser(model: DeviceModel): FrameParser = when(model) {
        DeviceModel.MCC -> object: FrameParser {
            private val parser = MccStreamParser()
            override fun feed(data: ByteArray) = parser.feed(data)
        }
        DeviceModel.MCS -> object: FrameParser {
            private val parser = McsStreamParser()
            override fun feed(data: ByteArray) = parser.feed(data)
            override fun expire() = parser.expire()
        }
    }
    fun validateTx(model: DeviceModel, raw: ByteArray) { when(model) {
        DeviceModel.MCC -> MccCodec.validate(raw, 15)
        DeviceModel.MCS -> McsCodec.parse(raw)
    } }
    fun encode(model: DeviceModel, command: RequestedOperation, sequence: Int): ByteArray {
        val caps=capabilities(model)
        require(command.speed in 0..10) { "speed must be 0..10" }
        require(command.temperatureC in caps.temperaturesC) { "unsupported temperature for $model" }
        require(command.durationSeconds in 0..caps.maximumDurationSeconds) { "unsupported duration for $model" }
        return when(model) {
            DeviceModel.MCC -> MccCodec.encodeTx(
                if(command.running) MccOperation.STANDARD else MccOperation.STOP,
                command.speed, caps.temperaturesC.indexOf(command.temperatureC),
                if(command.direction==MotorDirection.CLOCKWISE) MccDirection.CLOCKWISE else MccDirection.COUNTER_CLOCKWISE)
            DeviceModel.MCS -> McsCodec.operation(McsOperation(
                speedLevel=command.speed*2, reverse=command.direction==MotorDirection.COUNTER_CLOCKWISE,
                temperatureLevel=caps.temperaturesC.indexOf(command.temperatureC),
                function=if(command.running) 1 else 0, seconds=command.durationSeconds), sequence)
        }
    }
    fun poll(model: DeviceModel, sequence: Int): ByteArray? = when(model) {
        DeviceModel.MCC -> null
        DeviceModel.MCS -> McsCodec.operation(McsOperation(opcode=0x0801), sequence)
    }
    fun hex(bytes: ByteArray)=bytes.joinToString(" ") { "%02X".format(it.toInt() and 255) }
    fun decode(model: DeviceModel, bytes: ByteArray, generation: Long): DeviceState = when(model) {
        DeviceModel.MCC -> MccCodec.decodeRx(bytes).let { s -> DeviceState(
            model,hex(bytes),generation,System.nanoTime(),s.actualRpm.toDouble(),SpeedUnit.RPM,
            if(s.direction==MccDirection.CLOCKWISE) MotorDirection.CLOCKWISE else MotorDirection.COUNTER_CLOCKWISE,
            s.actualTemperature,s.targetTemperature,s.weight.toDouble(),s.lidOpen,s.bowlNtcDetected,
            if(s.errorDetected) s.errorCode else 0,if(s.errorDetected) "BOARD_ERROR_${s.errorCode}" else "NORMAL",s.firmwareVersion,
            mapOf("status" to s.status.toString(),"androidErrorCode" to s.androidErrorCode.toString(),
                "targetSpeedLevel" to s.targetSpeedLevel.toString(),"targetRpm" to s.targetRpm.toString(),
                "scaleState" to s.scaleState,"warnings" to s.warnings.joinToString("; ")))
        }
        DeviceModel.MCS -> McsCodec.telemetry(bytes).let { s -> DeviceState(
            model,hex(bytes),generation,System.nanoTime(),s.speedLevel.toDouble(),SpeedUnit.RAW_MOTOR_LEVEL,
            if(s.directionRaw==1) MotorDirection.COUNTER_CLOCKWISE else MotorDirection.CLOCKWISE,
            s.temperature,s.returnedTemperature,if(s.weightUnit==0)s.weight else null,s.lidOpen,!s.ntcAbsent,s.error,s.errorName,s.firmware,
            mapOf("state" to s.state.toString(),"opcode" to s.frame.opcode.toString(),"sequence" to s.frame.sequence.toString(),
                "function" to s.function.toString(),"countdownSeconds" to s.countdownSeconds.toString(),
                "weightUnit" to s.weightUnit.toString(),"weightRaw" to s.weightRaw.toString(),
                "decimalPlaces" to s.decimalPlaces.toString(),"scaledWeight" to s.weight.toString(),
                "temperatureUnit" to s.temperatureUnit.toString(),"directionRaw" to s.directionRaw.toString(),
                "scaleState" to s.scaleState.toString()))
        }
    }
}
