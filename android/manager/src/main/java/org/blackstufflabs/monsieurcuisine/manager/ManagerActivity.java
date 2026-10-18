package org.blackstufflabs.monsieurcuisine.manager;

import android.app.Activity;
import android.app.PendingIntent;
import android.content.ComponentName;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageInstaller;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.util.Log;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import android.content.pm.PackageInfo;
import java.util.Collections;
import java.util.List;

/** Small API 23 user-space launcher, app list and consent-based APK installer.
 * Coexists with the manufacturer package; never disables/replaces it or opens
 * UART, PowerBoard, root, a device-owner role or protected system components.
 */
public final class ManagerActivity extends Activity {
    private static final String OEM = "de.silpion.mc2";
    private static final int PICK_APK = 23;
    private LinearLayout content;
    private TextView status;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        content = new LinearLayout(this); content.setOrientation(LinearLayout.VERTICAL); content.setPadding(20, 20, 20, 20);
        ScrollView scroll = new ScrollView(this); scroll.addView(content); setContentView(scroll);
        rememberPreviousHome();
        render();
    }

    private void rememberPreviousHome() {
        if (getPreferences(0).contains("previous_home")) return;
        ResolveInfo home = getPackageManager().resolveActivity(new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME), PackageManager.MATCH_DEFAULT_ONLY);
        if (home != null && !home.activityInfo.packageName.equals(getPackageName()) && !home.activityInfo.name.contains("ResolverActivity")) {
            String component = new ComponentName(home.activityInfo.packageName, home.activityInfo.name).flattenToShortString();
            getPreferences(0).edit().putString("previous_home", component).apply();
        }
    }

    private TextView label(String text, float size) {
        TextView label = new TextView(this); label.setText(text); label.setTextSize(size); content.addView(label); return label;
    }
    private void button(String text, Runnable action) {
        Button button = new Button(this); button.setText(text);
        button.setOnClickListener(view -> { try { action.run(); } catch (Exception error) { status.setText("Unavailable: " + error.getClass().getSimpleName()); } });
        content.addView(button);
    }
    private void openPackage(String name) {
        Intent launch = getPackageManager().getLaunchIntentForPackage(name);
        if (launch == null) { status.setText("Application has no launchable activity: " + name); return; }
        startActivity(launch);
    }
    private void render() {
        content.removeAllViews();
        label("MC Developer Home", 24);
        label("blackstufflabs.com · Independent SDK · No PowerBoard access", 12);
        status = label("Android " + Build.VERSION.RELEASE + " / API " + Build.VERSION.SDK_INT + " · " + Build.MODEL, 15);
        try {
            label("OEM application: " + getPackageManager().getPackageInfo(OEM, 0).versionName, 13);
        } catch (PackageManager.NameNotFoundException missing) { label("OEM application is not installed in this environment", 13); }
        ResolveInfo home = getPackageManager().resolveActivity(new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME), PackageManager.MATCH_DEFAULT_ONLY);
        label("Current HOME: " + (home == null ? "unresolved" : home.activityInfo.packageName), 13);
        button("Open original Monsieur Cuisine interface", () -> openPackage(OEM));
        button("Choose default HOME in Android settings", () -> startActivity(new Intent(Settings.ACTION_HOME_SETTINGS)));
        button("Clear this launcher's HOME preference / return", () -> {
            getPackageManager().clearPackagePreferredActivities(getPackageName());
            String previous = getPreferences(0).getString("previous_home", "");
            ComponentName component = ComponentName.unflattenFromString(previous);
            Intent intent = new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME);
            if (component != null) intent.setComponent(component);
            startActivity(intent);
        });
        button("Install a user-selected APK", () -> startActivityForResult(new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("application/vnd.android.package-archive").addCategory(Intent.CATEGORY_OPENABLE), PICK_APK));
        button("Refresh applications", this::render);
        label("Launchable applications", 19);
        PackageManager pm = getPackageManager();
        List<ResolveInfo> apps = pm.queryIntentActivities(new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER), 0);
        Collections.sort(apps, (a,b) -> a.loadLabel(pm).toString().compareToIgnoreCase(b.loadLabel(pm).toString()));
        for (ResolveInfo app : apps) {
            String name = app.activityInfo.packageName;
            button(app.loadLabel(pm) + " · " + name, () -> openPackage(name));
            if ((app.activityInfo.applicationInfo.flags & ApplicationInfo.FLAG_SYSTEM) == 0 && !name.equals(OEM) && !name.equals(getPackageName())) {
                button("Uninstall user app: " + name, () -> startActivity(new Intent(Intent.ACTION_DELETE, Uri.parse("package:" + name))));
            }
        }
    }

    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request != PICK_APK || result != RESULT_OK || data == null || data.getData() == null) return;
        Uri uri = data.getData();
        status.setText("Preparing user-selected APK; Android will request installation consent");
        new Thread(() -> {
            PackageInstaller installer = getPackageManager().getPackageInstaller();
            int id = -1;
            boolean committed = false;
            File cached = null;
            try {
                cached = File.createTempFile("selected-", ".apk", getCacheDir());
                try (InputStream selected = getContentResolver().openInputStream(uri);
                     FileOutputStream copy = new FileOutputStream(cached)) {
                    if (selected == null) throw new java.io.IOException("no selected APK stream");
                    byte[] block = new byte[65536]; int read; long total = 0;
                    while ((read = selected.read(block)) != -1) {
                        total += read; if (total > 512L * 1024 * 1024) throw new java.io.IOException("APK size bound exceeded");
                        copy.write(block, 0, read);
                    }
                    copy.getFD().sync();
                }
                PackageInfo archive = getPackageManager().getPackageArchiveInfo(cached.getAbsolutePath(), 0);
                if (archive == null || archive.packageName.equals(OEM) || archive.packageName.equals(getPackageName())
                    || archive.packageName.equals("android") || archive.packageName.startsWith("android.")) {
                    throw new SecurityException("protected/invalid application");
                }
                try {
                    ApplicationInfo existing = getPackageManager().getApplicationInfo(archive.packageName, 0);
                    if ((existing.flags & ApplicationInfo.FLAG_SYSTEM) != 0) throw new SecurityException("system replacement is not supported");
                } catch (PackageManager.NameNotFoundException newApplication) { /* new user application */ }
                id = installer.createSession(new PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL));
                try (PackageInstaller.Session session = installer.openSession(id)) {
                    // Close the FileBridge stream exactly once, before commit.
                    // API23's second close can throw; abandoning after commit
                    // would invalidate the system's pending consent session.
                    try (InputStream input = new FileInputStream(cached);
                         OutputStream output = session.openWrite("base.apk", 0, -1)) {
                        byte[] block = new byte[65536]; int read; long total = 0;
                        while ((read = input.read(block)) != -1) {
                            total += read; if (total > 512L * 1024 * 1024) throw new java.io.IOException("APK size bound exceeded");
                            output.write(block, 0, read);
                        }
                        session.fsync(output);
                    }
                    Intent statusIntent = new Intent(this, InstallStatusReceiver.class);
                    int flags = PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= 31 ? PendingIntent.FLAG_MUTABLE : 0);
                    session.commit(PendingIntent.getBroadcast(this, id, statusIntent, flags).getIntentSender());
                    committed = true;
                }
            } catch (Exception error) {
                Log.e("MCSDK_INSTALL", "User-selected APK installation failed", error);
                if (id >= 0 && !committed) { try { installer.abandonSession(id); } catch (Exception ignored) { /* already closed */ } }
                runOnUiThread(() -> status.setText("APK installation unavailable: " + error.getClass().getSimpleName()));
            } finally {
                if (cached != null) cached.delete();
            }
        }, "selected-apk-install").start();
    }
}
