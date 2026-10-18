plugins { id("com.android.application"); kotlin("android") }
android {
    namespace = "org.blackstufflabs.monsieurcuisine.demo"
    compileSdk = 35
    defaultConfig {
        applicationId = "org.blackstufflabs.monsieurcuisine.demo"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "2.0.0-dev0"
        testInstrumentationRunner = "org.blackstufflabs.monsieurcuisine.demo.BridgeInstrumentation"
    }
    buildFeatures { buildConfig = true }
    buildTypes {
        debug { applicationIdSuffix = ".debug"; versionNameSuffix = "-debug" }
        release { isMinifyEnabled = false }
    }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
}
kotlin { compilerOptions { jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17) } }
dependencies { implementation(project(":sdk")) }
