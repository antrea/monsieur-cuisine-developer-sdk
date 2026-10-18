plugins { id("com.android.application") }
android {
    namespace = "org.blackstufflabs.monsieurcuisine.manager"
    compileSdk = 35
    defaultConfig {
        applicationId = "org.blackstufflabs.monsieurcuisine.manager"
        minSdk = 23
        targetSdk = 35
        versionCode = 1
        versionName = "2.0.0-dev0"
    }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
}
// Ordinary user app; no OEM signing, shared UID, AndroidX or native UART code.
