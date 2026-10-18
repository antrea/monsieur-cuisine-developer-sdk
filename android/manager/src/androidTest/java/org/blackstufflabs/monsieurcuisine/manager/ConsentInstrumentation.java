package org.blackstufflabs.monsieurcuisine.manager;

import android.app.Activity;
import android.app.Instrumentation;
import android.app.UiAutomation;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.PackageInstaller;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.view.accessibility.AccessibilityNodeInfo;
import java.io.*;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.List;

/** Actual API23 SAF + PackageInstaller UI exercise. No install shell command.
 * The fixture must be an independent SDK demo APK with a dedicated test ID.
 */
public final class ConsentInstrumentation extends Instrumentation {
    private static final String TEST_PACKAGE = "org.blackstufflabs.monsieurcuisine.demo.consenttest.debug";
    private static final String MANAGER = "org.blackstufflabs.monsieurcuisine.manager";
    private Bundle arguments;
    private final List<String> stages = new ArrayList<>();
    private UiAutomation automation;
    private int originalUnknownSources = -1;

    @Override public void onCreate(Bundle arguments) { super.onCreate(arguments); this.arguments = arguments; start(); }
    private void stage(String value) {
        stages.add(value); Bundle status = new Bundle(); status.putString("stage", value); sendStatus(1, status);
    }
    private boolean installed() {
        try { getTargetContext().getPackageManager().getPackageInfo(TEST_PACKAGE, 0); return true; }
        catch (PackageManager.NameNotFoundException expected) { return false; }
    }
    private AccessibilityNodeInfo find(AccessibilityNodeInfo node, String owner, String text, String description) {
        if (node == null) return null;
        boolean correctOwner = owner.equals(String.valueOf(node.getPackageName()));
        if (correctOwner && node.isVisibleToUser()
                && ((text != null && text.equalsIgnoreCase(String.valueOf(node.getText())))
                    || (description != null && description.equalsIgnoreCase(String.valueOf(node.getContentDescription()))))) return node;
        for (int index = 0; index < node.getChildCount(); index++) {
            AccessibilityNodeInfo match = find(node.getChild(index), owner, text, description);
            if (match != null) return match;
        }
        return null;
    }
    private boolean clickIfPresent(String owner, String text, String description) {
        AccessibilityNodeInfo found = find(automation.getRootInActiveWindow(), owner, text, description);
        for (int depth = 0; found != null && depth < 5; depth++, found = found.getParent()) {
            if (found.isEnabled() && found.isClickable()) return found.performAction(AccessibilityNodeInfo.ACTION_CLICK);
        }
        return false;
    }
    private void click(String owner, String text, String description) throws Exception {
        long deadline = System.nanoTime() + 15_000_000_000L;
        while (System.nanoTime() < deadline) {
            if (clickIfPresent(owner, text, description)) { Thread.sleep(200); return; }
            Thread.sleep(100);
        }
        throw new IOException("UI control unavailable: " + owner + " / " + text + " / " + description);
    }
    private void selectFixture() throws Exception {
        click(MANAGER, "Install a user-selected APK", null); stage("SAF_OPENED_FROM_MANAGER");
        if (!clickIfPresent("com.android.documentsui", "MC SDK test APKs", null)) {
            click("com.android.documentsui", null, "Show roots");
            click("com.android.documentsui", "MC SDK test APKs", null);
        }
        click("com.android.documentsui", "MC SDK consent fixture.apk", null); stage("SAF_FIXTURE_SELECTED");
    }
    private AccessibilityNodeInfo scrollable(AccessibilityNodeInfo node) {
        if (node == null) return null;
        if (node.isScrollable()) return node;
        for (int index = 0; index < node.getChildCount(); index++) {
            AccessibilityNodeInfo match = scrollable(node.getChild(index)); if (match != null) return match;
        }
        return null;
    }
    private int unknownSources() {
        return Settings.Secure.getInt(getTargetContext().getContentResolver(), "install_non_market_apps", 0);
    }
    private void setUnknownSourcesInSystemUi(int desired) throws Exception {
        if (unknownSources() == desired) return;
        getTargetContext().startActivity(new Intent(Settings.ACTION_SECURITY_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        Thread.sleep(700);
        boolean clicked = false;
        for (int attempt = 0; attempt < 12 && !clicked; attempt++) {
            clicked = clickIfPresent("com.android.settings", "Unknown sources", null);
            if (!clicked) {
                AccessibilityNodeInfo container = scrollable(automation.getRootInActiveWindow());
                if (container != null) container.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD);
                Thread.sleep(200);
            }
        }
        if (!clicked) throw new IOException("system Unknown sources control unavailable");
        if (desired == 1) {
            // The platform owns this warning and consent, not the Manager.
            click("com.android.settings", "OK", null);
        }
        long deadline = System.nanoTime() + 5_000_000_000L;
        while (unknownSources() != desired && System.nanoTime() < deadline) Thread.sleep(100);
        if (unknownSources() != desired) throw new IOException("system source preference did not change");
        stage(desired == 1 ? "UNKNOWN_SOURCES_ENABLED_IN_SYSTEM_UI" : "UNKNOWN_SOURCES_RESTORED_IN_SYSTEM_UI");
    }
    private String prepareFixture() throws Exception {
        File supplied = new File(arguments.getString("apk", ""));
        if (!supplied.getCanonicalPath().equals(supplied.getAbsolutePath())
                || !supplied.getAbsolutePath().startsWith("/data/local/tmp/mc-sdk-consent-")
                || !supplied.isFile() || supplied.length() <= 0 || supplied.length() > 16 * 1024 * 1024) {
            throw new IOException("supply an explicit bounded developer APK fixture");
        }
        PackageInfo info = getTargetContext().getPackageManager().getPackageArchiveInfo(supplied.getAbsolutePath(), 0);
        if (info == null || !TEST_PACKAGE.equals(info.packageName)) throw new SecurityException("dedicated SDK test package required");
        MessageDigest hash = MessageDigest.getInstance("SHA-256");
        try (InputStream input = new FileInputStream(supplied)) {
            byte[] block = new byte[65536]; int count;
            while ((count = input.read(block)) != -1) hash.update(block, 0, count);
        }
        StringBuilder digest = new StringBuilder();
        for (byte value : hash.digest()) digest.append(String.format(java.util.Locale.ROOT, "%02x", value & 255));
        if (!digest.toString().equals(arguments.getString("sha256"))) throw new IOException("fixture digest mismatch");
        return digest.toString();
    }
    private void checkOriginalDoubleCloseFailure() throws Exception {
        PackageInstaller installer = getTargetContext().getPackageManager().getPackageInstaller();
        int id = installer.createSession(new PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL));
        boolean failed = false;
        try (PackageInstaller.Session session = installer.openSession(id)) {
            OutputStream bridge = session.openWrite("base.apk", 0, -1);
            try { bridge.write(new byte[]{1, 2, 3}); session.fsync(bridge); }
            finally { bridge.close(); }
            try { bridge.close(); } catch (IOException expected) { failed = true; }
        } finally { installer.abandonSession(id); }
        if (!failed) throw new IOException("expected API23 double-close behavior changed; reassess the regression evidence");
        stage("API23_DOUBLE_CLOSE_FAILURE_REPRODUCED");
    }
    @Override public void onStart() {
        Bundle result = new Bundle(); Activity activity = null;
        try {
            if (Build.VERSION.SDK_INT != 23 || !("goldfish".equals(Build.HARDWARE) || "ranchu".equals(Build.HARDWARE))) {
                throw new SecurityException("consent test requires the selected software API23 emulator");
            }
            if (installed()) throw new IOException("test fixture package already installed; preserve it and select a fresh test environment");
            String digest = prepareFixture(); automation = getUiAutomation();
            checkOriginalDoubleCloseFailure();
            originalUnknownSources = unknownSources();
            setUnknownSourcesInSystemUi(1);
            activity = startActivitySync(new Intent(getTargetContext(), ManagerActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            selectFixture();
            click("com.android.packageinstaller", "Cancel", null);
            Thread.sleep(600);
            if (installed()) throw new IOException("cancel installed the APK"); stage("USER_CANCEL_PRESERVED_ABSENCE");
            selectFixture();
            if (installed()) throw new IOException("APK installed before user confirmation");
            stage("INSTALL_CONSENT_REQUIRED"); click("com.android.packageinstaller", "Install", null);
            long deadline = System.nanoTime() + 30_000_000_000L;
            while (!installed() && System.nanoTime() < deadline) Thread.sleep(100);
            if (!installed()) throw new IOException("PackageInstaller did not install fixture"); stage("PACKAGE_INSTALLED_AFTER_UI_CONSENT");
            PackageInfo info = getTargetContext().getPackageManager().getPackageInfo(TEST_PACKAGE, 0);
            result.putBoolean("passed", true); result.putString("fixture_sha256", digest);
            result.putString("package", TEST_PACKAGE); result.putInt("installed_uid", info.applicationInfo.uid);
            result.putString("stages", stages.toString()); result.putBoolean("hardware_verified", false);
        } catch (Throwable failure) {
            result.putBoolean("passed", false); result.putString("detail", failure.toString());
        } finally {
            Activity owned = activity; if (owned != null) runOnMainSync(owned::finish);
            try { if (originalUnknownSources >= 0) setUnknownSourcesInSystemUi(originalUnknownSources); }
            catch (Exception failure) { result.putBoolean("passed", false); result.putString("cleanup_error", failure.toString()); }
        }
        result.putString("stages", stages.toString());
        finish(result.getBoolean("passed", false) ? Activity.RESULT_OK : Activity.RESULT_CANCELED, result);
    }
}
