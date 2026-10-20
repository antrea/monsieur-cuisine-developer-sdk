package org.blackstufflabs.monsieurcuisine.manager;

import android.app.Activity;
import android.app.PendingIntent;
import android.content.ComponentName;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageInfo;
import android.content.pm.PackageInstaller;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.content.pm.Signature;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.OpenableColumns;
import android.provider.Settings;
import android.util.Log;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileNotFoundException;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/** Small API 23 user-space launcher, app list and consent-based APK installer.
 * Coexists with the manufacturer package; never disables/replaces it or opens
 * UART, PowerBoard, root, a device-owner role or protected system components.
 * Installation: the user picks an APK through Android's document picker (a USB
 * drive appears there when the system mounts it), the Manager inspects it, copies
 * it to private storage, and hands it to Android's PackageInstaller, which asks
 * the user for consent and performs its own signature/compatibility checks.
 */
public final class ManagerActivity extends Activity {
    private static final String OEM = "de.silpion.mc2";
    private static final int PICK_APK = 23;
    private static final long APK_BOUND = 512L * 1024 * 1024;
    private LinearLayout content;
    private TextView status;
    private TextView details;
    private LinearLayout resultActions;
    private InstallJournal journal;
    private volatile boolean installing;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        journal = new InstallJournal(this);
        content = new LinearLayout(this); content.setOrientation(LinearLayout.VERTICAL); content.setPadding(20, 20, 20, 20);
        ScrollView scroll = new ScrollView(this); scroll.addView(content); setContentView(scroll);
        rememberPreviousHome();
        render();
        recoverJournal();
    }

    @Override protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        if (InstallStatusReceiver.ACTION_RESULT.equals(intent.getAction())) { installing = false; showJournalResult(); }
    }

    @Override protected void onResume() {
        super.onResume();
        if (!installing) recoverJournal();
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
    private Button button(LinearLayout parent, String text, Runnable action) {
        Button button = new Button(this); button.setText(text);
        button.setOnClickListener(view -> { try { action.run(); } catch (Exception error) { status.setText("Unavailable: " + error.getClass().getSimpleName()); } });
        parent.addView(button); return button;
    }
    private void openPackage(String name) {
        Intent launch = getPackageManager().getLaunchIntentForPackage(name);
        if (launch == null) { status.setText("Application has no launchable activity: " + name); return; }
        startActivity(launch);
    }
    private void render() {
        content.removeAllViews();
        label("MC Developer Home", 24);
        label("blackstufflabs.com · Independent SDK · No PowerBoard access · Manager " + BuildConfig.VERSION_NAME + " (" + BuildConfig.VERSION_CODE + ")", 12);
        label("Android " + Build.VERSION.RELEASE + " / API " + Build.VERSION.SDK_INT + " · " + Build.MODEL, 13);
        try {
            label("OEM application: " + getPackageManager().getPackageInfo(OEM, 0).versionName, 13);
        } catch (PackageManager.NameNotFoundException missing) { label("OEM application is not installed in this environment", 13); }
        ResolveInfo home = getPackageManager().resolveActivity(new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME), PackageManager.MATCH_DEFAULT_ONLY);
        label("Current HOME: " + (home == null ? "unresolved" : home.activityInfo.packageName), 13);
        label("Install or update an application", 19);
        label("Choose an APK file from the document picker (a USB drive appears there when Android mounts it). "
            + "Android shows its own confirmation and checks the signature and compatibility; nothing is installed without it.", 12);
        button(content, "Install a user-selected APK", () -> {
            if (installing) { status.setText("An installation is already in progress."); return; }
            startActivityForResult(new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("application/vnd.android.package-archive").addCategory(Intent.CATEGORY_OPENABLE), PICK_APK);
        });
        status = label("No installation in progress.", 15);
        status.setContentDescription("install-status");
        details = label("", 12);
        details.setContentDescription("install-details");
        resultActions = new LinearLayout(this); resultActions.setOrientation(LinearLayout.VERTICAL); content.addView(resultActions);
        label("Launcher", 19);
        button(content, "Open original Monsieur Cuisine interface", () -> openPackage(OEM));
        button(content, "Choose default HOME in Android settings", () -> startActivity(new Intent(Settings.ACTION_HOME_SETTINGS)));
        button(content, "Clear this launcher's HOME preference / return", () -> {
            getPackageManager().clearPackagePreferredActivities(getPackageName());
            String previous = getPreferences(0).getString("previous_home", "");
            ComponentName component = ComponentName.unflattenFromString(previous);
            Intent intent = new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME);
            if (component != null) intent.setComponent(component);
            startActivity(intent);
        });
        button(content, "Refresh applications", this::render);
        label("Launchable applications", 19);
        PackageManager pm = getPackageManager();
        List<ResolveInfo> apps = pm.queryIntentActivities(new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER), 0);
        Collections.sort(apps, (a,b) -> a.loadLabel(pm).toString().compareToIgnoreCase(b.loadLabel(pm).toString()));
        for (ResolveInfo app : apps) {
            String name = app.activityInfo.packageName;
            String version = "";
            try { PackageInfo info = pm.getPackageInfo(name, 0); version = " · v" + info.versionName + " (" + info.versionCode + ")"; }
            catch (PackageManager.NameNotFoundException ignored) { /* listed but gone */ }
            button(content, app.loadLabel(pm) + " · " + name + version, () -> openPackage(name));
            if ((app.activityInfo.applicationInfo.flags & ApplicationInfo.FLAG_SYSTEM) == 0 && !name.equals(OEM) && !name.equals(getPackageName())) {
                button(content, "Uninstall user app: " + name, () -> startActivity(new Intent(Intent.ACTION_DELETE, Uri.parse("package:" + name))));
            }
        }
    }

    // -- installation flow ----------------------------------------------------------------
    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request != PICK_APK) return;
        if (result != RESULT_OK || data == null || data.getData() == null) {
            status.setText("No file selected."); return;
        }
        Uri uri = data.getData();
        String name = displayName(uri);
        installing = true;
        journal.begin(name);
        resultActions.removeAllViews();
        details.setText("");
        status.setText("Reading " + name + " …");
        new Thread(() -> install(uri, name), "selected-apk-install").start();
    }

    private String displayName(Uri uri) {
        try (Cursor cursor = getContentResolver().query(uri, new String[]{OpenableColumns.DISPLAY_NAME}, null, null, null)) {
            if (cursor != null && cursor.moveToFirst() && !cursor.isNull(0)) return cursor.getString(0);
        } catch (Exception ignored) { /* provider without metadata */ }
        String last = uri.getLastPathSegment();
        return last == null ? "selected file" : last;
    }

    private static String hex(byte[] raw) {
        StringBuilder text = new StringBuilder();
        for (byte value : raw) text.append(String.format(Locale.ROOT, "%02x", value & 255));
        return text.toString();
    }

    private void fail(String text) {
        installing = false;
        journal.result(PackageInstaller.STATUS_FAILURE, text);
        runOnUiThread(() -> { status.setText(text); showInstalledState(journal.packageName()); });
    }

    private void install(Uri uri, String name) {
        PackageInstaller installer = getPackageManager().getPackageInstaller();
        File cached = null;
        int id = -1;
        boolean committed = false;
        try {
            cached = File.createTempFile("selected-", ".apk", getCacheDir());
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            long total = 0;
            try (InputStream selected = getContentResolver().openInputStream(uri);
                 FileOutputStream copy = new FileOutputStream(cached)) {
                if (selected == null) throw new FileNotFoundException("no stream");
                byte[] block = new byte[65536]; int read;
                while ((read = selected.read(block)) != -1) {
                    total += read; if (total > APK_BOUND) throw new IOException("APK size bound exceeded");
                    copy.write(block, 0, read); digest.update(block, 0, read);
                }
                copy.getFD().sync();
            } catch (FileNotFoundException | SecurityException gone) {
                fail("The selected file is no longer accessible (removed drive, or the file was deleted). Nothing was installed."); return;
            } catch (IOException unreadable) {
                fail("The selected file could not be read completely: " + unreadable.getMessage() + ". Nothing was installed."); return;
            }
            if (total == 0) { fail("The selected file is empty. Nothing was installed."); return; }

            PackageManager pm = getPackageManager();
            @SuppressWarnings("deprecation")
            PackageInfo archive = pm.getPackageArchiveInfo(cached.getAbsolutePath(), PackageManager.GET_SIGNATURES);
            if (archive == null || archive.packageName == null) {
                // API 23 also returns null for a well-formed APK whose minimum SDK is above this device.
                fail(looksLikeApk(cached)
                    ? "Android cannot read this package on this device: it is damaged, or built for a newer Android version "
                      + "(its minimum SDK is above API " + Build.VERSION.SDK_INT + "). Nothing was installed."
                    : "This file is not a valid Android app package (damaged, incomplete or not an APK). Nothing was installed."); return;
            }
            archive.applicationInfo.sourceDir = cached.getAbsolutePath();
            archive.applicationInfo.publicSourceDir = cached.getAbsolutePath();
            String label = String.valueOf(archive.applicationInfo.loadLabel(pm));
            String packageName = archive.packageName;
            if (packageName.equals(OEM) || packageName.equals("android") || packageName.startsWith("android.")) {
                fail("Protected application: the Manager does not install or replace manufacturer or system packages."); return;
            }
            StringBuilder summary = new StringBuilder();
            summary.append("Application: ").append(label).append('\n')
                   .append("Package: ").append(packageName).append('\n')
                   .append("Version: ").append(archive.versionName).append(" (code ").append(archive.versionCode).append(")\n")
                   .append("File: ").append(name).append(", ").append(total / 1024).append(" KiB, SHA-256 ")
                   .append(hex(digest.digest()), 0, 16).append("…\n");
            boolean update = false;
            PackageInfo installed = null;
            try { installed = pm.getPackageInfo(packageName, PackageManager.GET_SIGNATURES); }
            catch (PackageManager.NameNotFoundException newApplication) { /* new user application */ }
            if (installed != null) {
                if ((installed.applicationInfo.flags & ApplicationInfo.FLAG_SYSTEM) != 0) {
                    fail("Protected application: " + packageName + " is a system package and is not replaced by the Manager."); return;
                }
                update = true;
                summary.append("Operation: UPDATE of installed version ").append(installed.versionName)
                       .append(" (code ").append(installed.versionCode).append(")\n");
                if (archive.versionCode < installed.versionCode) {
                    summary.append("Warning: the file is an OLDER version than the installed one; Android refuses downgrades.\n");
                } else if (archive.versionCode == installed.versionCode) {
                    summary.append("Note: same version code as the installed copy; Android reinstalls it in place.\n");
                }
                if (!sameSigners(archive.signatures, installed.signatures)) {
                    summary.append("Warning: signed with a DIFFERENT key than the installed copy; Android will refuse this update "
                                 + "(uninstalling the app first deletes its data).\n");
                }
                if (packageName.equals(getPackageName())) summary.append("Note: this updates the Manager itself; it restarts after Android confirms.\n");
            } else {
                summary.append("Operation: NEW installation\n");
            }
            summary.append("Android now shows its confirmation and performs the final signature and compatibility checks.");
            journal.inspected(packageName, label, archive.versionCode, String.valueOf(archive.versionName), update);
            String text = summary.toString();
            runOnUiThread(() -> { details.setText(text); status.setText("Waiting for Android's confirmation …"); });

            id = installer.createSession(new PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL));
            try (PackageInstaller.Session session = installer.openSession(id)) {
                // Close the FileBridge stream exactly once, before commit.
                // API23's second close can throw; abandoning after commit
                // would invalidate the system's pending consent session.
                try (InputStream input = new FileInputStream(cached);
                     OutputStream output = session.openWrite("base.apk", 0, -1)) {
                    byte[] block = new byte[65536]; int read; long written = 0;
                    while ((read = input.read(block)) != -1) {
                        written += read; if (written > APK_BOUND) throw new IOException("APK size bound exceeded");
                        output.write(block, 0, read);
                    }
                    session.fsync(output);
                }
                journal.committed(id);
                Intent statusIntent = new Intent(this, InstallStatusReceiver.class);
                int flags = PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= 31 ? PendingIntent.FLAG_MUTABLE : 0);
                session.commit(PendingIntent.getBroadcast(this, id, statusIntent, flags).getIntentSender());
                committed = true;
            }
        } catch (Exception error) {
            Log.e("MCSDK_INSTALL", "User-selected APK installation failed", error);
            if (id >= 0 && !committed) { try { installer.abandonSession(id); } catch (Exception ignored) { /* already closed */ } }
            fail("Installation could not be prepared: " + error.getClass().getSimpleName() + ". Nothing was installed.");
        } finally {
            if (cached != null) cached.delete();
        }
    }

    /** A readable ZIP with a manifest and code: well-formed as a file even if this Android cannot parse it. */
    private static boolean looksLikeApk(File file) {
        try (java.util.zip.ZipFile zip = new java.util.zip.ZipFile(file)) {
            return zip.getEntry("AndroidManifest.xml") != null && zip.getEntry("classes.dex") != null;
        } catch (IOException unreadable) {
            return false;
        }
    }

    private static boolean sameSigners(Signature[] first, Signature[] second) {
        if (first == null || second == null) return false;
        Set<Signature> a = new HashSet<>(Arrays.asList(first)), b = new HashSet<>(Arrays.asList(second));
        return a.equals(b);
    }

    // -- results and recovery -------------------------------------------------------------
    private String installedState(String packageName) {
        if (packageName == null || packageName.isEmpty()) return "";
        try {
            PackageInfo info = getPackageManager().getPackageInfo(packageName, 0);
            return "Installed now: " + packageName + " version " + info.versionName + " (code " + info.versionCode + ").";
        } catch (PackageManager.NameNotFoundException absent) {
            return "Installed now: " + packageName + " is not installed.";
        }
    }

    private void showInstalledState(String packageName) {
        resultActions.removeAllViews();
        String state = installedState(packageName);
        if (!state.isEmpty()) {
            TextView view = new TextView(this); view.setText(state); view.setTextSize(13);
            view.setContentDescription("installed-state"); resultActions.addView(view);
            if (!state.endsWith("not installed.") && getPackageManager().getLaunchIntentForPackage(packageName) != null) {
                Button open = button(resultActions, "Open " + (journal.label().isEmpty() ? packageName : journal.label()), () -> openPackage(packageName));
                open.setContentDescription("open-installed-app");
            }
        }
        button(resultActions, "Dismiss message", () -> { journal.clear(); status.setText("No installation in progress."); details.setText(""); resultActions.removeAllViews(); });
    }

    private void showJournalResult() {
        int code = journal.status();
        String packageName = journal.packageName();
        String text;
        if (code == PackageInstaller.STATUS_SUCCESS) {
            text = (journal.update() ? "Updated " : "Installed ") + journal.label() + " " + journal.versionName() + " (code " + journal.versionCode() + ").";
        } else {
            text = InstallJournal.describe(code, journal.message());
        }
        status.setText(text);
        showInstalledState(packageName);
        render(); // refresh the application list (new versions, new apps)
        status.setText(text);
        if (code == PackageInstaller.STATUS_SUCCESS) {
            details.setText("Android confirmed the installation of " + packageName + ".");
        }
        showInstalledState(packageName);
    }

    /** Explain an interrupted flow after the Manager was closed or replaced, and tidy up. */
    private void recoverJournal() {
        String phase = journal.phase();
        if (InstallJournal.PHASE_NONE.equals(phase)) return;
        if (InstallJournal.PHASE_RESULT.equals(phase)) { showJournalResult(); return; }
        String packageName = journal.packageName();
        if (InstallJournal.PHASE_COPYING.equals(phase)) {
            for (File leftover : getCacheDir().listFiles() == null ? new File[0] : getCacheDir().listFiles()) {
                if (leftover.getName().startsWith("selected-")) leftover.delete();
            }
            journal.result(PackageInstaller.STATUS_FAILURE, "The Manager was closed while reading " + journal.fileName() + ".");
            status.setText("The previous installation was interrupted while reading " + journal.fileName() + ". Nothing was installed; select the file again.");
            showInstalledState(packageName);
            return;
        }
        // Committed or awaiting consent: did Android complete it while the Manager was away?
        try {
            PackageInfo info = getPackageManager().getPackageInfo(packageName, 0);
            if (info.versionCode == journal.versionCode()) {
                journal.result(PackageInstaller.STATUS_SUCCESS, "completed while the Manager was closed");
                showJournalResult(); return;
            }
        } catch (PackageManager.NameNotFoundException absent) { /* not installed */ }
        PackageInstaller installer = getPackageManager().getPackageInstaller();
        boolean pending = false;
        for (PackageInstaller.SessionInfo session : installer.getMySessions()) {
            if (session.getSessionId() == journal.sessionId()) {
                pending = true;
                try { installer.abandonSession(session.getSessionId()); } catch (Exception ignored) { /* already gone */ }
            }
        }
        journal.result(PackageInstaller.STATUS_FAILURE_ABORTED, pending
            ? "The Manager was closed before Android's confirmation; the pending request was discarded."
            : "The Manager was closed before Android reported the result.");
        status.setText("The previous installation of " + journal.label() + " was not completed: " + journal.message()
            + " Select the file again to retry.");
        showInstalledState(packageName);
    }
}
