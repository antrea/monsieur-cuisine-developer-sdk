plugins { id("com.android.application") }
android {
    namespace = "org.blackstufflabs.monsieurcuisine.oemprobe"
    compileSdk = 35
    defaultConfig {
        applicationId = "org.blackstufflabs.monsieurcuisine.oemprobe"
        minSdk = 23
        targetSdk = 23
        versionCode = 1
        versionName = "2.0.0-dev0"
    }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
}
// No SDK, OEM classes, assets, network library or third-party dependency.
