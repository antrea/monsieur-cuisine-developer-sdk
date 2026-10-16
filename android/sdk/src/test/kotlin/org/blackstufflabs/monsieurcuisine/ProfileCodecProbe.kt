package org.blackstufflabs.monsieurcuisine

import org.json.JSONObject
import org.blackstufflabs.monsieurcuisine.profiles.mcc.MccCodec
import org.blackstufflabs.monsieurcuisine.profiles.mcs.McsCodec

/** JSON-lines differential probe. Test-only dependency; absent from the SDK/runtime APK. */
object ProfileCodecProbe {
    @JvmStatic fun main(args:Array<String>) {
        generateSequence(::readLine).forEach { text ->
            val input=JSONObject(text)
            val model=DeviceModel.valueOf(input.getString("model"))
            val output=when(input.getString("action")) {
                "encode" -> JSONObject().put("hex",WireProfiles.hex(WireProfiles.encode(model,
                    RequestedOperation(input.optBoolean("running",true),input.optInt("speed"),
                        MotorDirection.valueOf(input.optString("direction","COUNTER_CLOCKWISE")),
                        input.optInt("temperature"),input.optInt("duration")),input.optInt("sequence",1))))
                "decode" -> {
                    val raw=MccCodec.parseHex(input.getString("hex"))
                    if(model==DeviceModel.MCC) MccCodec.decodeRx(raw).let { s -> JSONObject()
                        .put("status",s.status).put("motor_heater_state",s.motorHeaterState)
                        .put("direction",s.direction.androidValue).put("error_code",s.errorCode)
                        .put("android_error_code",s.androidErrorCode).put("actual_rpm",s.actualRpm)
                        .put("target_rpm",s.targetRpm).put("actual_temperature",s.actualTemperature)
                        .put("target_temperature",s.targetTemperature).put("weight",s.weight)
                        .put("firmware_version",s.firmwareVersion).put("scale_state_raw",s.scaleStateRaw)
                        .put("unknown_byte24",s.unknownByte24) }
                    else McsCodec.telemetry(raw).let { s -> JSONObject()
                        .put("firmware_version",s.firmware).put("state",s.state).put("error",s.error)
                        .put("actual_temperature",s.temperature).put("returned_temperature",s.returnedTemperature)
                        .put("speed_level",s.speedLevel).put("direction",s.directionRaw)
                        .put("weight_raw",s.weightRaw).put("weight_unit",s.weightUnit)
                        .put("weight_decimal_point",s.decimalPlaces).put("temperature_unit",s.temperatureUnit)
                        .put("turbo_key",s.turboKey).put("function",s.function)
                        .put("countdown_seconds",s.countdownSeconds) }
                }
                else -> error("unknown probe action")
            }
            println(output.toString())
        }
    }
}
