package org.blackstufflabs.monsieurcuisine.manager;

import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.PackageInstaller;

/** Durable record of the current/last installation, so the Manager can explain what happened
 * after it was closed, killed or replaced in the middle of a flow. Holds package metadata only.
 */
final class InstallJournal {
    static final String PHASE_NONE = "none", PHASE_COPYING = "copying", PHASE_COMMITTED = "committed",
        PHASE_AWAITING_CONSENT = "awaiting_consent", PHASE_RESULT = "result";
    private final SharedPreferences store;

    InstallJournal(Context context) { store = context.getSharedPreferences("install-journal", Context.MODE_PRIVATE); }

    String phase() { return store.getString("phase", PHASE_NONE); }
    String packageName() { return store.getString("package", ""); }
    String label() { return store.getString("label", ""); }
    int versionCode() { return store.getInt("version_code", 0); }
    String versionName() { return store.getString("version_name", ""); }
    boolean update() { return store.getBoolean("update", false); }
    int sessionId() { return store.getInt("session", -1); }
    int status() { return store.getInt("status", Integer.MIN_VALUE); }
    String message() { return store.getString("message", ""); }
    String fileName() { return store.getString("file", ""); }

    void begin(String fileName) {
        store.edit().clear().putString("phase", PHASE_COPYING).putString("file", fileName)
            .putLong("started", System.currentTimeMillis()).commit();
    }
    void inspected(String packageName, String label, int versionCode, String versionName, boolean update) {
        store.edit().putString("package", packageName).putString("label", label).putInt("version_code", versionCode)
            .putString("version_name", versionName).putBoolean("update", update).commit();
    }
    void committed(int sessionId) {
        store.edit().putString("phase", PHASE_COMMITTED).putInt("session", sessionId).commit();
    }
    void awaitingConsent() { store.edit().putString("phase", PHASE_AWAITING_CONSENT).commit(); }
    void result(int status, String message) {
        store.edit().putString("phase", PHASE_RESULT).putInt("status", status)
            .putString("message", message == null ? "" : message).commit();
    }
    void clear() { store.edit().clear().commit(); }

    static String describe(int status, String message) {
        String base;
        switch (status) {
            case PackageInstaller.STATUS_SUCCESS: base = "Installed successfully."; break;
            case PackageInstaller.STATUS_FAILURE_ABORTED:
                base = "Cancelled: Android did not install anything. The previously installed version, if any, is unchanged."; break;
            case PackageInstaller.STATUS_FAILURE_BLOCKED:
                base = "Blocked by Android: installation from this source is not allowed (check the unknown-sources setting or a device policy)."; break;
            case PackageInstaller.STATUS_FAILURE_CONFLICT:
                base = "Refused by Android: the installed copy was signed with a different key, or another package conflicts. "
                     + "An update must come from the same developer key; otherwise the installed app must be uninstalled first, which deletes its data."; break;
            case PackageInstaller.STATUS_FAILURE_INCOMPATIBLE:
                base = "Refused by Android: this package is not compatible with this device or Android version (for example it requires a newer Android)."; break;
            case PackageInstaller.STATUS_FAILURE_INVALID:
                base = "Refused by Android: the package is damaged, incomplete, or an older version than the one installed."; break;
            case PackageInstaller.STATUS_FAILURE_STORAGE:
                base = "Refused by Android: not enough storage space."; break;
            default: base = "Installation failed."; break;
        }
        return (message == null || message.isEmpty()) ? base : base + " Android reported: " + message;
    }
}
