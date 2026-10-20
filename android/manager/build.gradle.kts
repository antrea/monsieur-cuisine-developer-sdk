import java.util.Properties

plugins { id("com.android.application") }

// Optional release signing with a key the owner keeps outside the repository:
//   gradlew -PmcSigningProperties=PRIVATE/mc-sdk-apps.properties :manager:assembleRelease
// The properties file names the keystore, passwords and alias. A missing file
// or keystore fails the build; no key is ever generated automatically. Without
// the property the release APK stays unsigned, as before.
val signingProperties = providers.gradleProperty("mcSigningProperties").orNull?.let { path ->
    val source = file(path)
    require(source.isFile) { "mcSigningProperties points to a missing file: $path (no key is generated automatically)" }
    Properties().apply { source.inputStream().use { stream -> load(stream) } }
}

android {
    namespace = "org.blackstufflabs.monsieurcuisine.manager"
    compileSdk = 35
    defaultConfig {
        applicationId = "org.blackstufflabs.monsieurcuisine.manager"
        minSdk = 23
        targetSdk = 35
        versionCode = providers.gradleProperty("managerVersionCode").getOrElse("2").toInt()
        versionName = providers.gradleProperty("managerVersionName").getOrElse("2.0.0-dev1")
        testInstrumentationRunner = "org.blackstufflabs.monsieurcuisine.manager.ConsentInstrumentation"
    }
    buildFeatures { buildConfig = true }
    if (signingProperties != null) {
        signingConfigs {
            create("mcRelease") {
                val store = file(signingProperties.getProperty("mcSigningStoreFile"))
                require(store.isFile) { "signing keystore is missing: $store (no key is generated automatically)" }
                storeFile = store
                storePassword = signingProperties.getProperty("mcSigningStorePassword")
                keyAlias = signingProperties.getProperty("mcSigningKeyAlias")
                keyPassword = signingProperties.getProperty("mcSigningKeyPassword")
            }
        }
        buildTypes { release { signingConfig = signingConfigs.getByName("mcRelease") } }
    }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
}
// Ordinary user app; no OEM signing, shared UID, AndroidX or native UART code.
