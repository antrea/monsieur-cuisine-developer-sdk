package org.blackstufflabs.monsieurcuisine.oemprobe;

import android.app.Activity;
import android.app.Instrumentation;
import android.os.Build;
import android.os.Bundle;
import android.system.ErrnoException;
import android.system.Os;
import android.system.OsConstants;
import dalvik.system.DexClassLoader;
import org.json.JSONObject;
import java.io.*;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.security.MessageDigest;
import java.util.Arrays;

/** Original JNI open on an emulator's SOFTWARE PTY only. No UART or TX/RX.
 * The original DEX/native bytes are supplied privately, hash pinned, never
 * bundled. A different component keeps the pure codec reference scope intact.
 */
public final class NativeSerialInstrumentation extends Instrumentation {
    private static final String DEX_SHA = "daacbce286ea9f4911556d37c66b8559a3f341046cf720fb900bc047b10c2b53";
    private static final String NATIVE_SHA = "bd3231f08be279700f6ba64b405429082e02159f136b56fe0f26a0c51877d0fa";
    private Bundle arguments;

    @Override public void onCreate(Bundle arguments) {
        super.onCreate(arguments);
        this.arguments = arguments == null ? new Bundle() : arguments;
        start();
    }

    private static String sha256(File file) throws Exception {
        MessageDigest hash = MessageDigest.getInstance("SHA-256");
        try (InputStream input = new FileInputStream(file)) {
            byte[] block = new byte[65536]; int count;
            while ((count = input.read(block)) != -1) hash.update(block, 0, count);
        }
        StringBuilder result = new StringBuilder();
        for (byte value : hash.digest()) result.append(String.format(java.util.Locale.ROOT, "%02x", value & 255));
        return result.toString();
    }

    private File verified(String key, String expected, long limit) throws Exception {
        File file = new File(arguments.getString(key, ""));
        if (!file.isFile() || file.length() <= 0 || file.length() > limit
                || !file.getCanonicalPath().equals(file.getAbsolutePath())
                || !file.getAbsolutePath().startsWith("/data/local/tmp/mc-sdk-")) {
            throw new IOException("invalid private reference input");
        }
        if (!sha256(file).equals(expected)) throw new IOException("reference component hash mismatch");
        return file;
    }

    private static void retireWrappers(Class<?> serial, Object instance) {
        for (String getter : new String[]{"getInputStream", "getOutputStream"}) {
            try { ((Closeable) serial.getMethod(getter).invoke(instance)).close(); }
            catch (Exception ignored) { /* both wrappers share the same descriptor */ }
        }
    }

    @Override public void onStart() {
        Bundle result = new Bundle();
        try {
            if (Build.VERSION.SDK_INT != 23 || !Arrays.asList(Build.SUPPORTED_ABIS).contains("x86")
                    || !("goldfish".equals(Build.HARDWARE) || "ranchu".equals(Build.HARDWARE))) {
                throw new SecurityException("native probe requires the explicit API23 x86 software emulator");
            }
            File dex = verified("dex", DEX_SHA, 64L * 1024 * 1024);
            File supplied = verified("native", NATIVE_SHA, 16L * 1024 * 1024);
            File libraries = getTargetContext().getDir("oem-native", 0);
            File library = new File(libraries, "libserial_port.so");
            try (InputStream input = new FileInputStream(supplied); OutputStream output = new FileOutputStream(library)) {
                byte[] block = new byte[65536]; int count;
                while ((count = input.read(block)) != -1) output.write(block, 0, count);
            }
            if (!sha256(library).equals(NATIVE_SHA)) throw new IOException("native private copy differs");
            DexClassLoader loader = new DexClassLoader(dex.getAbsolutePath(),
                    getTargetContext().getCodeCacheDir().getAbsolutePath(), libraries.getAbsolutePath(), getClass().getClassLoader());
            Class<?> serial = Class.forName("android_serialport_api.SerialPort", true, loader);
            File endpoint = new File("/dev/ptmx");
            if (!endpoint.canRead() || !endpoint.canWrite()) throw new IOException("software PTY unavailable");
            Object instance = null; FileDescriptor descriptor = null;
            boolean character = false, closed = false, invalidRejected = false;
            String descriptorField = null;
            boolean nativeCloseFieldPresent = false;
            try { nativeCloseFieldPresent = serial.getDeclaredField("mFd").getType() == FileDescriptor.class; }
            catch (NoSuchFieldException expected) { /* supplied DEX has obfuscated field 'a' */ }
            try {
                instance = serial.getConstructor(File.class, int.class, int.class).newInstance(endpoint, 4800, 0);
                for (Field field : serial.getFields()) {
                    if (field.getType() == FileDescriptor.class) {
                        descriptor = (FileDescriptor) field.get(instance);
                        descriptorField = field.getName();
                    }
                }
                if (descriptor == null || !descriptor.valid()) throw new IOException("original JNI did not open a valid FD");
                character = (Os.fstat(descriptor).st_mode & OsConstants.S_IFMT) == OsConstants.S_IFCHR;
                if (!character) throw new IOException("expected software character device");
                if (Boolean.parseBoolean(String.valueOf(arguments.get("exerciseOriginalClose")))) {
                    // Explicit diagnostic reproduction only. The pinned x86 JNI
                    // looks up mFd, missing from the original DEX, and ART aborts.
                    Bundle phase = new Bundle();
                    phase.putString("phase", "original-native-close");
                    phase.putInt("pid", android.os.Process.myPid());
                    sendStatus(0, phase);
                    serial.getMethod("close").invoke(instance);
                    throw new IOException("original native close unexpectedly returned; inspect this new evidence");
                }
                // Normal probe cleans up through Java, not the broken original
                // native close. Never label this as a successful JNI close test.
                retireWrappers(serial, instance);
                // API23 stream wrappers made from an existing FD do not own
                // the native descriptor; release it explicitly through libcore.
                Os.close(descriptor);
                try { Os.fstat(descriptor); }
                catch (ErrnoException expected) {
                    if (expected.errno == OsConstants.EBADF) closed = true;
                    else throw expected;
                }
                if (!closed) throw new IOException("software probe cleanup did not close its descriptor");
                instance = null; descriptor = null;
                Method open = serial.getMethod("open", String.class, int.class, int.class);
                FileDescriptor invalid = (FileDescriptor) open.invoke(null, "/dev/ptmx", 12345, 0);
                invalidRejected = invalid == null;
                if (invalid != null) Os.close(invalid);
                if (!invalidRejected) throw new IOException("original JNI accepted the unsupported test baud argument");
            } finally {
                // Retire Java wrappers immediately after observing cleanup,
                // before another file can reuse the kernel descriptor number.
                if (instance != null) {
                    retireWrappers(serial, instance);
                }
                if (!closed && descriptor != null) {
                    try { Os.close(descriptor); } catch (ErrnoException ignored) { }
                }
            }
            JSONObject record = new JSONObject();
            record.put("passed", character && closed && invalidRejected);
            record.put("abi", "x86"); record.put("android_api", Build.VERSION.SDK_INT);
            record.put("endpoint", "/dev/ptmx"); record.put("software_pty_only", true);
            record.put("character_device", character); record.put("probe_cleanup_verified_ebadf", closed);
            record.put("native_open_verified", character);
            record.put("original_native_close_invoked", false);
            record.put("original_descriptor_field", descriptorField);
            record.put("original_native_close_required_field", "mFd");
            record.put("original_native_close_field_present", nativeCloseFieldPresent);
            record.put("original_native_close_verified", false);
            record.put("invalid_baud_rejected", invalidRejected); record.put("open_baud_argument", 4800);
            record.put("physical_baud_measured", false); record.put("payload_bytes_sent", 0);
            record.put("hardware_verified", false); record.put("original_dex_sha256", DEX_SHA);
            record.put("original_native_sha256", NATIVE_SHA);
            File report = new File(getTargetContext().getFilesDir(), "native-serial.json");
            try (Writer writer = new OutputStreamWriter(new FileOutputStream(report), "UTF-8")) { writer.write(record.toString()); }
            result.putBoolean("passed", true);
            result.putString("scope", "original JNI software PTY open only; native close NOT verified; no robot hardware");
            finish(Activity.RESULT_OK, result);
        } catch (Throwable failure) {
            result.putBoolean("passed", false); result.putString("detail", failure.toString());
            finish(Activity.RESULT_CANCELED, result);
        }
    }
}
