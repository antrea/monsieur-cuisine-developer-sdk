package org.blackstufflabs.monsieurcuisine.oemprobe;

import android.app.Activity;
import android.app.Instrumentation;
import android.os.Bundle;
import dalvik.system.DexClassLoader;
import org.json.JSONObject;
import java.io.*;
import java.lang.reflect.Method;
import java.security.MessageDigest;
import java.util.HashMap;
import java.util.Map;
import java.util.Random;

/** Executes only named pure host codec/conversion methods from a supplied DEX.
 * No original APK is bundled, installed or started; no service or UART class is
 * instantiated. This harness contains no SDK codec and has no INTERNET permission.
 * Use the explicit-emulator host verifier, not a connected physical appliance.
 */
public final class ReferenceInstrumentation extends Instrumentation {
    private Bundle arguments;
    private final Map<String, Method> methods = new HashMap<>();
    private ClassLoader loader;
    private Class<?> boardClass;
    private PrintWriter output;
    private int count;

    @Override public void onCreate(Bundle arguments) {
        super.onCreate(arguments);
        this.arguments = arguments == null ? new Bundle() : arguments;
        start();
    }

    private Object call(Object target, String name, Object... values) throws Exception {
        Class<?> type = target instanceof Class<?> ? (Class<?>) target : target.getClass();
        String key = type.getName() + "/" + name + "/" + values.length;
        Method method = methods.get(key);
        if (method == null) {
            for (Method candidate : type.getMethods()) {
                if (candidate.getName().equals(name) && candidate.getParameterTypes().length == values.length) {
                    method = candidate; methods.put(key, method); break;
                }
            }
        }
        if (method == null) throw new NoSuchMethodException(key);
        return method.invoke(target instanceof Class<?> ? null : target, values);
    }

    private Class<?> type(String name) throws Exception { return Class.forName(name, true, loader); }
    private Object board() throws Exception { return boardClass.getDeclaredConstructor().newInstance(); }
    private static String hex(byte[] bytes) {
        char[] chars = new char[bytes.length * 2];
        char[] digits = "0123456789abcdef".toCharArray();
        for (int i = 0; i < bytes.length; i++) { chars[2*i] = digits[(bytes[i] & 255) >>> 4]; chars[2*i+1] = digits[bytes[i] & 15]; }
        return new String(chars);
    }
    private void emit(Object... pairs) throws Exception {
        JSONObject row = new JSONObject();
        for (int i = 0; i < pairs.length; i += 2) {
            Object value = pairs[i+1];
            row.put((String) pairs[i], value instanceof Enum<?> ? value.toString() : value);
        }
        output.println(row); count++;
    }

    @Override public void onStart() {
        Bundle result = new Bundle();
        try {
            File dex = new File(arguments.getString("dex", ""));
            if (!dex.isFile() || dex.length() > 64L * 1024 * 1024) throw new IOException("invalid DEX input");
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            try (InputStream input = new FileInputStream(dex)) {
                byte[] chunk = new byte[65536]; int read;
                while ((read = input.read(chunk)) != -1) digest.update(chunk, 0, read);
            }
            String expected = arguments.getString("sha256", "");
            if (!hex(digest.digest()).equals(expected)) throw new IOException("DEX hash mismatch");
            loader = new DexClassLoader(dex.getAbsolutePath(), getTargetContext().getCodeCacheDir().getAbsolutePath(), null, getClass().getClassLoader());
            boardClass = type("machineAdapter.impl.hal.PowerBoard");
            File file = new File(getTargetContext().getFilesDir(), "oem-vectors.jsonl");
            try (PrintWriter writer = new PrintWriter(new OutputStreamWriter(new FileOutputStream(file), "UTF-8"))) {
                output = writer;
                generate();
                if (writer.checkError()) throw new IOException("vector output failed");
            }
            result.putBoolean("passed", true);
            result.putInt("vectors", count);
            result.putInt("android_api", android.os.Build.VERSION.SDK_INT);
            result.putString("dex_sha256", expected);
            result.putString("reference", "original DEX directly executed by ART; no SDK codec dependency");
            finish(Activity.RESULT_OK, result);
        } catch (Throwable failure) {
            result.putBoolean("passed", false);
            result.putString("detail", failure.toString());
            finish(Activity.RESULT_CANCELED, result);
        }
    }

    private void generate() throws Exception {
        Object[] commands = type("machineAdapter.impl.hal.PowerBoard$I_WorkCommand").getEnumConstants();
        Object[] directions = type("machineAdapter.impl.hal.PowerBoard$I_MotorDirection").getEnumConstants();
        Object[] calibrations = type("machineAdapter.impl.hal.PowerBoard$I_ScaleCalibration").getEnumConstants();
        for (Object command : commands) for (int speed = -2; speed <= 12; speed++)
            for (int level = -2; level <= 21; level++) for (Object direction : directions)
                for (int tare = 0; tare < 2; tare++) for (Object calibration : calibrations) {
                    Object b = board();
                    call(b, "setSendWorkCommand", command); call(b, "setSendSpeedLevel", speed);
                    call(b, "setSendTemperatureLevel", level); call(b, "setSendMotorDirection", direction);
                    call(b, "setSendTareScale", tare == 1); call(b, "setSendScaleCalibration", calibration);
                    emit("kind", "tx", "command", command, "speed", speed, "level", level, "direction", direction,
                        "tare", tare == 1, "calibration", calibration, "frame", hex((byte[]) call(b, "getSendPayload")));
                }
        Random random = new Random(292);
        for (int n = 0; n < 20000; n++) {
            byte[] frame = new byte[27]; random.nextBytes(frame); int variant = n % 10;
            if (variant < 9) { frame[0] = 0x55; frame[1] = 27; frame[2] = (byte) 0xb1; frame[26] = (byte) 0xaa; }
            if (variant < 8) {
                if (variant < 4) { frame[5] = (byte) random.nextInt(10); frame[22] = (byte) random.nextInt(8); frame[23] = (byte) random.nextInt(9); }
                int sum = 0; for (int i = 0; i < 25; i++) sum += frame[i]; frame[25] = (byte) sum;
            }
            Object b = board(); call(b, "setReceivedData", frame);
            emit("kind", "rx", "frame", hex(frame), "valid", call(boardClass, "areDataCorrect", frame),
                "stable", call(b, "areScaleDataStable"), "actual_rpm", call(b, "getActualRpm"), "actual_level", call(b, "getActualSpeedLevel"),
                "actual_temperature", call(b, "getActualTemperature"), "error", call(b, "getError"), "firmware", call(b, "getFirmwareVersion"),
                "extended", call(b, "getMotorHeaterExtendedState"), "motor_heater", call(b, "getMotorHeaterState"), "not_available", call(b, "getNotAvailable"),
                "calibration_step", call(b, "getScaleCalibrationStep"), "scale_state", call(b, "getScaleState"), "weight", call(b, "getScaleWeight"),
                "target_rpm", call(b, "getTargetRpm"), "target_level", call(b, "getTargetSpeedLevel"), "target_temperature", call(b, "getTargetTemperature"),
                "target_temperature_level", call(b, "getTargetTemperatureLevel"), "lid_open", call(b, "isCupCoverOpened"),
                "above_target", call(b, "isCupTemperatureHigherThanTargetTemperature"), "ntc", call(b, "isCupsNTCDetected"),
                "error_detected", call(b, "isErrorDetected"), "clockwise", call(b, "isMotorDirectionClockwise"));
        }
        Class<?> cooking = type("cooking.CookingUtils"), limits = type("cooking.Limits");
        for (int c = -50; c <= 300; c++) emit("kind", "celsius", "celsius", c, "level", call(cooking, "getTemperatureLevel", c), "knob_step", call(limits, "getStepFromTemperature", c));
        for (int l = -3; l <= 25; l++) emit("kind", "level", "level", l, "celsius", call(cooking, "getTemperature", l), "knob_celsius", call(limits, "getTemperatureFromStep", l));
        for (int s = -2; s <= 12; s++) emit("kind", "time_limit", "speed", s, "ms", call(limits, "getMaxTimeForSpeedLevel", s));
        for (int rpm = -10; rpm <= 20000; rpm++) {
            if (rpm > 100 && rpm % 7 != 0 && !(rpm % 1000 < 3 || rpm % 1000 > 997) && rpm != 558 && rpm != 559 && rpm != 1008 && rpm != 1009 && rpm != 1437 && rpm != 1438) continue;
            byte[] frame = new byte[27]; frame[0] = 0x55; frame[1] = 27; frame[2] = (byte) 0xb1; frame[26] = (byte) 0xaa;
            frame[9] = (byte) (rpm >> 8); frame[10] = (byte) rpm;
            int sum = 0; for (int i = 0; i < 25; i++) sum += frame[i]; frame[25] = (byte) sum;
            Object b = board(); call(b, "setReceivedData", frame);
            emit("kind", "rpm_level", "rpm", rpm, "level", call(b, "getActualSpeedLevel"));
        }
    }
}
