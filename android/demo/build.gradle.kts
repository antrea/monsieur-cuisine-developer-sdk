import java.util.Properties

plugins { id("com.android.application"); kotlin("android") }

// Optional release signing, shared with the Manager: see manager/build.gradle.kts.
val signingProperties = providers.gradleProperty("mcSigningProperties").orNull?.let { path ->
    val source = file(path)
    require(source.isFile) { "mcSigningProperties points to a missing file: $path (no key is generated automatically)" }
    Properties().apply { source.inputStream().use { stream -> load(stream) } }
}

android {
    namespace = "org.blackstufflabs.monsieurcuisine.demo"
    compileSdk = 35
    defaultConfig {
        applicationId = providers.gradleProperty("demoApplicationId").getOrElse("org.blackstufflabs.monsieurcuisine.demo")
        // demoMinSdk exists only to build a deliberately incompatible test fixture.
        minSdk = providers.gradleProperty("demoMinSdk").getOrElse("23").toInt()
        targetSdk = 35
        versionCode = providers.gradleProperty("demoVersionCode").getOrElse("1").toInt()
        versionName = providers.gradleProperty("demoVersionName").getOrElse("2.0.0-dev0")
        testInstrumentationRunner = "org.blackstufflabs.monsieurcuisine.demo.BridgeInstrumentation"
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
    }
    buildTypes {
        debug { applicationIdSuffix = ".debug"; versionNameSuffix = "-debug" }
        release {
            isMinifyEnabled = false
            if (signingProperties != null) signingConfig = signingConfigs.getByName("mcRelease")
        }
    }
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
}
kotlin { compilerOptions { jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17) } }
dependencies { implementation(project(":sdk")) }
