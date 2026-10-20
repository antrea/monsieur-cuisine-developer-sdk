package org.blackstufflabs.monsieurcuisine.demo

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import org.json.JSONObject
import java.io.File
import java.security.KeyStore
import javax.crypto.KeyGenerator
import javax.crypto.Mac

/** Controlled test-owned data for real API 23 update/rollback checks. No robot I/O. */
internal object AppDataFixture {
    fun run(context:Context, action:String):String {
        require(action in setOf("seed","mutate","inspect"))
        if(action!="inspect") {
            val value=if(action=="seed")"before" else "after"
            context.filesDir.mkdirs()
            File(context.filesDir,"settings.txt").writeText(value)
            File(context.noBackupFilesDir,"state.bin").writeBytes(value.toByteArray())
            File(context.cacheDir,"cached.bin").writeBytes(value.toByteArray())
            File(context.applicationInfo.dataDir,"root state.txt").writeText(value)
            File(context.filesDir,"state é.txt").writeText(value)
            File(context.filesDir,"long-"+"a".repeat(120)).writeText(value)
            File(context.getDir("custom",Context.MODE_PRIVATE),"state.txt").writeText(value)
            check(context.getSharedPreferences("sdk_fixture",Context.MODE_PRIVATE).edit().putString("value",value).commit())
            context.openOrCreateDatabase("sdkfixture.db",Context.MODE_PRIVATE,null).use { database ->
                database.execSQL("CREATE TABLE IF NOT EXISTS state (value TEXT)")
                database.execSQL("DELETE FROM state")
                database.execSQL("INSERT INTO state (value) VALUES (?)",arrayOf(value))
            }
            if(action=="mutate")File(context.filesDir,"new-only.txt").writeText("created after update")
        }
        val result=JSONObject()
        result.put("files",File(context.filesDir,"settings.txt").readText())
        result.put("no_backup",File(context.noBackupFilesDir,"state.bin").readText())
        result.put("cache",File(context.cacheDir,"cached.bin").readText())
        result.put("root",File(context.applicationInfo.dataDir,"root state.txt").readText())
        result.put("unicode",File(context.filesDir,"state é.txt").readText())
        result.put("long_name",File(context.filesDir,"long-"+"a".repeat(120)).readText())
        result.put("custom",File(context.getDir("custom",Context.MODE_PRIVATE),"state.txt").readText())
        result.put("preference",context.getSharedPreferences("sdk_fixture",Context.MODE_PRIVATE).getString("value",null))
        context.openOrCreateDatabase("sdkfixture.db",Context.MODE_PRIVATE,null).use { database ->
            database.rawQuery("SELECT value FROM state",null).use { cursor ->
                check(cursor.moveToFirst());result.put("database",cursor.getString(0))
            }
        }
        result.put("new_file",File(context.filesDir,"new-only.txt").exists())
        // A test-owned key remains inside AndroidKeyStore. Only its MAC is
        // compared; neither the key nor manufacturer credentials are exported.
        val store=KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        val alias="mc-sdk-data-fixture"
        if(action=="seed" && !store.containsAlias(alias)) {
            KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_HMAC_SHA256,"AndroidKeyStore").apply {
                init(KeyGenParameterSpec.Builder(alias,KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY)
                    .setDigests(KeyProperties.DIGEST_SHA256).build())
                generateKey()
            }
        }
        check(store.containsAlias(alias)) { "test-owned keystore key was lost" }
        val mac=Mac.getInstance("HmacSHA256").apply { init(store.getKey(alias,null)) }
        result.put("keystore_mac",mac.doFinal("SDK data rollback fixture".toByteArray()).joinToString("") { "%02x".format(it) })
        return result.toString()
    }
}
