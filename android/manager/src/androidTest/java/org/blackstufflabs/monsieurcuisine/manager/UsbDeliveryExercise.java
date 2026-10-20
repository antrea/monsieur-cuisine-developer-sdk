package org.blackstufflabs.monsieurcuisine.manager;

import android.app.Activity;
import android.app.Instrumentation;
import android.app.UiAutomation;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.view.accessibility.AccessibilityNodeInfo;
import java.io.File;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Actual API23 exercise of the Manager's install/update flow through Android's document picker and
 * PackageInstaller: new installation, data creation in the installed app, cancelled update, damaged
 * file, foreign signing key, incompatible Android version, file vanished before reading, real update
 * with data preserved, downgrade refusal, and Manager closed before Android's answer.
 * Arguments: package (the fixture app's package name), v1/v2/v3 (file names served by the test provider),
 * optional damaged/otherkey/minsdk/unreadable (file names; scenarios are skipped when absent).
 * The provider is a software stand-in for a mounted drive; this never proves a physical USB mount.
 */
public final class UsbDeliveryExercise {
    private final Instrumentation host;
    private static final String MANAGER = "org.blackstufflabs.monsieurcuisine.manager";
    private static final String DOCS = "com.android.documentsui";
    private static final String INSTALLER = "com.android.packageinstaller";
    private static final Pattern MEMORY = Pattern.compile("launch (\\d+)\\D+notes (\\d+)\\D+app (\\S+) \\((\\d+)\\)");  // ASCII-only: the label separators are non-ASCII
    private final Bundle arguments;
    private UiAutomation automation;
    private final List<String> stages = new ArrayList<>();
    private String fixturePackage;
    private int originalUnknownSources = -1;
    /** The Manager activity currently resumed (this instrumentation runs inside the Manager's process). */
    private volatile Activity current;

    UsbDeliveryExercise(Instrumentation host, Bundle arguments) { this.host = host; this.arguments = arguments; }

    private void stage(String value) {
        stages.add(value); Bundle status = new Bundle(); status.putString("stage", value); host.sendStatus(1, status);
    }

    // -- UI helpers (same approach as ConsentInstrumentation) ----------------------------------
    private AccessibilityNodeInfo find(AccessibilityNodeInfo node, String owner, String text, String description, String contains) {
        if (node == null) return null;
        boolean correctOwner = owner == null || owner.equals(String.valueOf(node.getPackageName()));
        String nodeText = String.valueOf(node.getText());
        if (correctOwner && node.isVisibleToUser()
                && ((text != null && text.equalsIgnoreCase(nodeText))
                    || (description != null && description.equalsIgnoreCase(String.valueOf(node.getContentDescription())))
                    || (contains != null && nodeText.toLowerCase(Locale.ROOT).contains(contains.toLowerCase(Locale.ROOT))))) return node;
        for (int index = 0; index < node.getChildCount(); index++) {
            AccessibilityNodeInfo match = find(node.getChild(index), owner, text, description, contains);
            if (match != null) return match;
        }
        return null;
    }
    /** Search every interactive window (the Manager stays behind Android's installer dialog), then the active one. */
    private AccessibilityNodeInfo findAnywhere(String owner, String text, String description, String contains) {
        try {
            for (android.view.accessibility.AccessibilityWindowInfo window : automation.getWindows()) {
                AccessibilityNodeInfo found = find(window.getRoot(), owner, text, description, contains);
                if (found != null) return found;
            }
        } catch (Exception ignored) { /* windows unavailable: fall back */ }
        return find(automation.getRootInActiveWindow(), owner, text, description, contains);
    }
    private AccessibilityNodeInfo wait(String owner, String text, String description, String contains, long seconds) throws Exception {
        long deadline = System.nanoTime() + seconds * 1_000_000_000L;
        while (System.nanoTime() < deadline) {
            AccessibilityNodeInfo found = findAnywhere(owner, text, description, contains);
            if (found != null) return found;
            Thread.sleep(150);
        }
        throw new IOException("UI element unavailable: " + owner + " / " + text + " / " + description + " / " + contains);
    }
    private boolean clickNode(AccessibilityNodeInfo found) {
        for (int depth = 0; found != null && depth < 5; depth++, found = found.getParent()) {
            if (found.isEnabled() && found.isClickable()) return found.performAction(AccessibilityNodeInfo.ACTION_CLICK);
        }
        return false;
    }
    private void click(String owner, String text, String description) throws Exception {
        long deadline = System.nanoTime() + 15_000_000_000L;
        while (System.nanoTime() < deadline) {
            AccessibilityNodeInfo found = find(automation.getRootInActiveWindow(), owner, text, description, null);
            if (found != null && clickNode(found)) { Thread.sleep(250); return; }
            Thread.sleep(100);
        }
        throw new IOException("UI control unavailable: " + owner + " / " + text + " / " + description);
    }
    private String textOf(String owner, String description, long seconds) throws Exception {
        return String.valueOf(wait(owner, null, description, null, seconds).getText());
    }
    // -- Manager texts read from its own views -------------------------------------------------
    // Android's consent screen covers the Manager within ~100 ms once the installer process is warm, so
    // the accessibility tree may never show the Manager's status and details while they matter. The
    // exercise runs in the Manager's process: its resumed activity is tracked and its TextViews read
    // on the main thread, whatever is in front. Clicks and the fixture app still go through accessibility.
    private static android.view.View viewWithDescription(android.view.View view, String description) {
        if (view == null) return null;
        if (description.contentEquals(String.valueOf(view.getContentDescription()))) return view;
        if (view instanceof android.view.ViewGroup) {
            android.view.ViewGroup group = (android.view.ViewGroup) view;
            for (int index = 0; index < group.getChildCount(); index++) {
                android.view.View match = viewWithDescription(group.getChildAt(index), description);
                if (match != null) return match;
            }
        }
        return null;
    }
    private String managerViewText(String description) {
        Activity activity = current;
        if (activity == null) return null;
        String[] out = new String[1];
        host.runOnMainSync(() -> {
            android.view.View view = viewWithDescription(activity.getWindow().getDecorView(), description);
            out[0] = view instanceof android.widget.TextView ? ((android.widget.TextView) view).getText().toString() : null;
        });
        return out[0];
    }
    private String managerText(String description, long seconds) throws Exception {
        long deadline = System.nanoTime() + seconds * 1_000_000_000L;
        while (System.nanoTime() < deadline) {
            String text = managerViewText(description);
            if (text == null) {
                AccessibilityNodeInfo node = findAnywhere(MANAGER, null, description, null);
                text = node == null ? null : String.valueOf(node.getText());
            }
            if (text != null) return text;
            Thread.sleep(150);
        }
        throw new IOException("Manager text unavailable: " + description);
    }
    private String waitForStatus(String contains, long seconds) throws Exception {
        long deadline = System.nanoTime() + seconds * 1_000_000_000L;
        String last = "";
        while (System.nanoTime() < deadline) {
            String text = managerViewText("install-status");
            if (text == null) {
                AccessibilityNodeInfo node = findAnywhere(MANAGER, null, "install-status", null);
                text = node == null ? "" : String.valueOf(node.getText());
            }
            last = text;
            if (last.toLowerCase(Locale.ROOT).contains(contains.toLowerCase(Locale.ROOT))) return last;
            Thread.sleep(200);
        }
        throw new IOException("Manager status did not report '" + contains + "'; last: " + last);
    }
    private AccessibilityNodeInfo scrollable(AccessibilityNodeInfo node) {
        if (node == null) return null;
        if (node.isScrollable()) return node;
        for (int index = 0; index < node.getChildCount(); index++) {
            AccessibilityNodeInfo match = scrollable(node.getChild(index)); if (match != null) return match;
        }
        return null;
    }
    private void scrollManagerToTop() {
        AccessibilityNodeInfo container = scrollable(automation.getRootInActiveWindow());
        for (int attempt = 0; container != null && attempt < 10; attempt++) {
            if (!container.performAction(AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD)) break;
        }
    }

    // -- package helpers --------------------------------------------------------------------
    private PackageInfo installed(String name) {
        try { return host.getTargetContext().getPackageManager().getPackageInfo(name, 0); }
        catch (PackageManager.NameNotFoundException absent) { return null; }
    }
    private int unknownSources() {
        return Settings.Secure.getInt(host.getTargetContext().getContentResolver(), "install_non_market_apps", 0);
    }
    private void setUnknownSourcesInSystemUi(int desired) throws Exception {
        if (unknownSources() == desired) return;
        // A fresh Settings task every time, so the screen starts at the top and the same scroll finds the row.
        host.getTargetContext().startActivity(new Intent(Settings.ACTION_SECURITY_SETTINGS)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TASK));
        Thread.sleep(900);
        boolean clicked = false;
        for (int attempt = 0; attempt < 12 && !clicked; attempt++) {
            AccessibilityNodeInfo found = find(automation.getRootInActiveWindow(), "com.android.settings", "Unknown sources", null, null);
            clicked = found != null && clickNode(found);
            if (!clicked) {
                AccessibilityNodeInfo container = scrollable(automation.getRootInActiveWindow());
                if (container != null) container.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD);
                Thread.sleep(200);
            }
        }
        if (!clicked) throw new IOException("system Unknown sources control unavailable");
        if (desired == 1) click("com.android.settings", "OK", null);
        long deadline = System.nanoTime() + 5_000_000_000L;
        while (unknownSources() != desired && System.nanoTime() < deadline) Thread.sleep(100);
        if (unknownSources() != desired) throw new IOException("system source preference did not change");
    }

    // -- flow pieces ---------------------------------------------------------------------------
    private Activity openManager() {
        Activity activity = host.startActivitySync(new Intent(host.getTargetContext(), ManagerActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        scrollManagerToTop();
        return activity;
    }
    /** Pick a fixture through the real document picker; returns the Manager's details text once inspected. */
    private void pick(String fileName) throws Exception {
        scrollManagerToTop();
        click(MANAGER, "Install a user-selected APK", null);
        // The picker may open on the test root, on another root, or with its drawer already open (it
        // remembers the last state): take whatever step the current screen allows until the file is clicked.
        long deadline = System.nanoTime() + 25_000_000_000L;
        while (System.nanoTime() < deadline) {
            AccessibilityNodeInfo root = automation.getRootInActiveWindow();
            AccessibilityNodeInfo file = find(root, DOCS, fileName, null, null);
            if (file != null && clickNode(file)) { Thread.sleep(250); return; }
            AccessibilityNodeInfo entry = find(root, DOCS, "MC SDK test APKs", null, null);
            if (entry != null && clickNode(entry)) { Thread.sleep(500); continue; }
            AccessibilityNodeInfo drawer = find(root, DOCS, null, "Show roots", null);
            if (drawer != null && clickNode(drawer)) { Thread.sleep(500); continue; }
            Thread.sleep(200);
        }
        throw new IOException("document picker did not offer " + fileName);
    }
    private String memoryOfInstalledApp() throws Exception {
        String text = textOf(fixturePackage, "local-memory", 20);
        if (!MEMORY.matcher(text).find()) throw new IOException("installed app did not show its local memory: " + text);
        return text;
    }
    private int[] memoryValues(String text) {
        Matcher match = MEMORY.matcher(text);
        if (!match.find()) throw new IllegalStateException(text);
        return new int[]{Integer.parseInt(match.group(1)), Integer.parseInt(match.group(2)), Integer.parseInt(match.group(4))};
    }
    private void backToManager() throws Exception {
        for (int attempt = 0; attempt < 4; attempt++) {
            if (find(automation.getRootInActiveWindow(), MANAGER, null, "install-status", null) != null) return;
            automation.performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK);
            Thread.sleep(600);
        }
        openManager();
    }
    private int versionCode(String name) { PackageInfo info = installed(name); return info == null ? -1 : info.versionCode; }

    /** Runs every scenario and finishes the host instrumentation with the result bundle. */
    void run() {
        Bundle result = new Bundle();
        Activity manager = null;
        try {
            if (Build.VERSION.SDK_INT != 23 || !("goldfish".equals(Build.HARDWARE) || "ranchu".equals(Build.HARDWARE))) {
                throw new SecurityException("this exercise requires the selected software API23 emulator");
            }
            fixturePackage = arguments.getString("package", "");
            String v1 = arguments.getString("v1", ""), v2 = arguments.getString("v2", ""), v3 = arguments.getString("v3", "");
            String damaged = arguments.getString("damaged", ""), otherKey = arguments.getString("otherkey", "");
            String minSdk = arguments.getString("minsdk", ""), unreadable = arguments.getString("unreadable", "");
            if (fixturePackage.isEmpty() || v1.isEmpty() || v2.isEmpty()) throw new IOException("package, v1 and v2 arguments are required");
            if (installed(fixturePackage) != null) throw new IOException("fixture package already installed; use a fresh environment");
            automation = host.getUiAutomation();
            android.accessibilityservice.AccessibilityServiceInfo info = automation.getServiceInfo();
            if (info != null) {
                info.flags |= android.accessibilityservice.AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS;
                automation.setServiceInfo(info);
            }
            originalUnknownSources = unknownSources();
            android.app.Application application = (android.app.Application) host.getTargetContext().getApplicationContext();
            application.registerActivityLifecycleCallbacks(new android.app.Application.ActivityLifecycleCallbacks() {
                @Override public void onActivityCreated(Activity activity, Bundle state) { }
                @Override public void onActivityStarted(Activity activity) { }
                @Override public void onActivityResumed(Activity activity) { if (activity instanceof ManagerActivity) current = activity; }
                @Override public void onActivityPaused(Activity activity) { }
                @Override public void onActivityStopped(Activity activity) { }
                @Override public void onActivitySaveInstanceState(Activity activity, Bundle state) { }
                @Override public void onActivityDestroyed(Activity activity) { if (activity == current) current = null; }
            });
            setUnknownSourcesInSystemUi(1);
            manager = openManager();

            // S1: new installation with consent, then the app creates data.
            pick(v1);
            waitForStatus("Waiting for Android", 30);
            String details = managerText("install-details", 10);
            if (!details.contains("NEW installation")) throw new IOException("details did not announce a new installation: " + details);
            if (installed(fixturePackage) != null) throw new IOException("installed before consent");
            click(INSTALLER, "Install", null);
            waitForStatus("Installed", 60);
            if (versionCode(fixturePackage) != 1) throw new IOException("v1 not installed");
            stage("S1_NEW_INSTALL_WITH_CONSENT");
            click(MANAGER, null, "open-installed-app");
            String memory = memoryOfInstalledApp();
            click(fixturePackage, null, "save-note"); click(fixturePackage, null, "save-note");
            memory = memoryOfInstalledApp();
            int[] before = memoryValues(memory);
            if (before[0] != 1 || before[1] != 2 || before[2] != 1) throw new IOException("unexpected v1 memory: " + memory);
            stage("S1_APP_OPENED_AND_DATA_CREATED");
            backToManager();

            // S2: update cancelled by the user.
            pick(v2);
            waitForStatus("Waiting for Android", 30);
            details = managerText("install-details", 10);
            if (!details.contains("UPDATE of installed version")) throw new IOException("details did not announce an update: " + details);
            click(INSTALLER, "Cancel", null);
            waitForStatus("Cancelled", 30);
            if (versionCode(fixturePackage) != 1) throw new IOException("cancel changed the installed version");
            stage("S2_UPDATE_CANCELLED_V1_KEPT");

            // S3: damaged file.
            if (!damaged.isEmpty()) {
                pick(damaged);
                waitForStatus("not a valid Android app package", 30);
                if (versionCode(fixturePackage) != 1) throw new IOException("damaged file changed the installation");
                stage("S3_DAMAGED_FILE_REFUSED_BEFORE_CONSENT");
            }

            // S4: same package, different signing key: Android refuses.
            if (!otherKey.isEmpty()) {
                pick(otherKey);
                waitForStatus("Waiting for Android", 30);
                details = managerText("install-details", 10);
                if (!details.contains("DIFFERENT key")) throw new IOException("signature warning missing: " + details);
                click(INSTALLER, "Install", null);
                waitForStatus("different key", 60);
                if (versionCode(fixturePackage) != 1) throw new IOException("foreign-key update changed the installation");
                stage("S4_OTHER_KEY_REFUSED_BY_ANDROID");
            }

            // S5: requires a newer Android than this device. API 23 cannot even parse such a package,
            // so the Manager reports it before Android's dialog; the file stays a well-formed APK.
            if (!minSdk.isEmpty()) {
                pick(minSdk);
                waitForStatus("newer Android", 30);
                if (versionCode(fixturePackage) != 1) throw new IOException("incompatible update changed the installation");
                stage("S5_INCOMPATIBLE_ANDROID_VERSION_REFUSED");
            }

            // S6: the file vanished between browsing and reading (drive removed).
            if (!unreadable.isEmpty()) {
                pick(unreadable);
                waitForStatus("no longer accessible", 30);
                if (versionCode(fixturePackage) != 1) throw new IOException("vanished file changed the installation");
                stage("S6_FILE_NO_LONGER_ACCESSIBLE");
            }

            // S7: real update, data preserved.
            pick(v2);
            waitForStatus("Waiting for Android", 30);
            click(INSTALLER, "Install", null);
            waitForStatus("Updated", 60);
            if (versionCode(fixturePackage) != 2) throw new IOException("v2 not installed");
            click(MANAGER, null, "open-installed-app");
            memory = memoryOfInstalledApp();
            int[] after = memoryValues(memory);
            if (after[0] != before[0] + 1 || after[1] != before[1] || after[2] != 2) throw new IOException("data not preserved across update: " + memory);
            stage("S7_UPDATE_KEPT_DATA");
            backToManager();

            // S8: older version over a newer one: Android refuses the downgrade.
            pick(v1);
            waitForStatus("Waiting for Android", 30);
            details = managerText("install-details", 10);
            if (!details.contains("OLDER version")) throw new IOException("downgrade warning missing: " + details);
            click(INSTALLER, "Install", null);
            waitForStatus("older version", 60);
            if (versionCode(fixturePackage) != 2) throw new IOException("downgrade changed the installation");
            stage("S8_DOWNGRADE_REFUSED_BY_ANDROID");

            // S9: the Manager is closed while Android waits for consent; the result still reaches it.
            if (!v3.isEmpty()) {
                pick(v3);
                waitForStatus("Waiting for Android", 30);
                wait(INSTALLER, "Install", null, null, 15);
                Activity owned = manager; host.runOnMainSync(owned::finish); manager = null;
                Thread.sleep(800);
                click(INSTALLER, "Install", null);
                waitForStatus("Updated", 60);
                if (versionCode(fixturePackage) != 3) throw new IOException("v3 not installed after reopening");
                click(MANAGER, null, "open-installed-app");
                int[] third = memoryValues(memoryOfInstalledApp());
                if (third[0] != after[0] + 1 || third[1] != after[1] || third[2] != 3) throw new IOException("data lost after the second update");
                stage("S9_MANAGER_CLOSED_DURING_CONSENT_RESULT_RECOVERED");
                backToManager();
            }
            result.putBoolean("passed", true);
            result.putString("package", fixturePackage);
            result.putInt("final_version_code", versionCode(fixturePackage));
            result.putBoolean("hardware_verified", false);
        } catch (Throwable failure) {
            result.putBoolean("passed", false); result.putString("detail", failure.toString());
        } finally {
            Activity owned = manager; if (owned != null) host.runOnMainSync(owned::finish);
            // Restore the source preference through Settings UI, trying once more after a BACK. The host
            // script re-checks the stored value and reports a restore it had to do itself; a failed restore
            // here never hides a scenario verdict.
            try {
                if (originalUnknownSources >= 0 && automation != null) {
                    try { setUnknownSourcesInSystemUi(originalUnknownSources); }
                    catch (IOException retry) {
                        automation.performGlobalAction(android.accessibilityservice.AccessibilityService.GLOBAL_ACTION_BACK);
                        Thread.sleep(800);
                        setUnknownSourcesInSystemUi(originalUnknownSources);
                    }
                    result.putBoolean("unknown_sources_restored_in_ui", true);
                }
            } catch (Exception failure) {
                result.putBoolean("unknown_sources_restored_in_ui", false);
                result.putString("cleanup_error", failure.toString());
            }
        }
        result.putString("stages", stages.toString());
        host.finish(result.getBoolean("passed", false) ? Activity.RESULT_OK : Activity.RESULT_CANCELED, result);
    }
}
