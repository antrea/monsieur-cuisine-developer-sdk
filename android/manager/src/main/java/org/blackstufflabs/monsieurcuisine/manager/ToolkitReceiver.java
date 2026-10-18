package org.blackstufflabs.monsieurcuisine.manager;

import android.content.BroadcastReceiver;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import org.json.JSONArray;
import org.json.JSONObject;

/** Shell/system-only interoperability queries and clearing this app's own HOME.
 * The manifest requires DUMP. No OEM preference is modified, no arbitrary
 * package operation is accepted, and no network/hardware API is used.
 */
public final class ToolkitReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) {
        try {
            JSONObject result = new JSONObject();
            if ("org.blackstufflabs.monsieurcuisine.manager.CLEAR_OWN_HOME".equals(intent.getAction())) {
                context.getPackageManager().clearPackagePreferredActivities(context.getPackageName());
                result.put("own_home_cleared", true);
            } else if ("org.blackstufflabs.monsieurcuisine.manager.QUERY_HOMES".equals(intent.getAction())) {
                PackageManager pm = context.getPackageManager();
                Intent home = new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME);
                JSONArray homes = new JSONArray();
                for (ResolveInfo info : pm.queryIntentActivities(home, 0)) {
                    homes.put(new JSONObject().put("component", new ComponentName(info.activityInfo.packageName, info.activityInfo.name).flattenToShortString())
                        .put("label", info.loadLabel(pm).toString()));
                }
                ResolveInfo current = pm.resolveActivity(home, PackageManager.MATCH_DEFAULT_ONLY);
                String effective = current == null ? "" : new ComponentName(current.activityInfo.packageName, current.activityInfo.name).flattenToShortString();
                result.put("homes", homes).put("effective_home", effective);
            } else {
                setResultCode(1); setResultData("unsupported action"); return;
            }
            setResultCode(0); setResultData(result.toString());
        } catch (Exception error) {
            setResultCode(1); setResultData("toolkit query failed: " + error.getClass().getSimpleName());
        }
    }
}
