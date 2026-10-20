package org.blackstufflabs.monsieurcuisine.manager;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInstaller;
import android.widget.Toast;

/** Native PackageInstaller callback. User consent is never bypassed; every outcome is journaled
 * and handed to the Manager screen, which also re-checks what is really installed.
 */
public final class InstallStatusReceiver extends BroadcastReceiver {
    static final String ACTION_RESULT = "org.blackstufflabs.monsieurcuisine.manager.INSTALL_RESULT";

    @Override public void onReceive(Context context, Intent intent) {
        int status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE);
        InstallJournal journal = new InstallJournal(context);
        if (status == PackageInstaller.STATUS_PENDING_USER_ACTION) {
            journal.awaitingConsent();
            Intent confirmation = intent.getParcelableExtra(Intent.EXTRA_INTENT);
            if (confirmation != null) {
                confirmation.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                context.startActivity(confirmation);
            }
            return;
        }
        journal.result(status, intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE));
        Toast.makeText(context, status == PackageInstaller.STATUS_SUCCESS ? "Application installed"
            : "Installation failed or was cancelled", Toast.LENGTH_LONG).show();
        // Bring the result to the Manager screen; singleTop delivers it to an open instance.
        context.startActivity(new Intent(context, ManagerActivity.class).setAction(ACTION_RESULT)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP));
    }
}
