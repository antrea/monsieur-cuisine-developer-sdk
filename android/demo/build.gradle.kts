plugins { id("com.android.application"); kotlin("android") }
android {
    namespace = "org.blackstufflabs.monsieurcuisine.demo"
    compileSdk = 35
    defaultConfig {
        applicationId = providers.gradleProperty("demoApplicationId").getOrElse("org.blackstufflabs.monsieurcuisine.demo")
        minSdk = 23
        targetSdk = 35
        versionCode = providers.gradleProperty("demoVersionCode").getOrElse("1").toInt()
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
