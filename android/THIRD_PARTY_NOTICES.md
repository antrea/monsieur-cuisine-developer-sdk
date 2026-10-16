# Android build and runtime components

The developer SDK and demo combine the MIT-licensed MCC and MCS toolkit contributions with new shared code. See the repository [LICENSE](../LICENSE) for the retained copyright and permission notices. Original protocol research is implemented as independent Kotlin codecs; no manufacturer APK, decompiled implementation, firmware, recipes, logos or other OEM assets are included.

The Gradle wrapper JAR and generated launcher scripts are Gradle build tooling under the Apache License, Version 2.0. Their [license](gradle/wrapper/LICENSE) and [notice](gradle/wrapper/NOTICE) are included. The wrapper selects Gradle 8.13, and `gradle/wrapper/gradle-wrapper.properties` pins the official distribution SHA-256. These licensed build-tool files are the only binaries intentionally committed with the Android source.

Kotlin compiler and standard library 2.3.21 are provided by JetBrains s.r.o. and Kotlin contributors under Apache-2.0. Kotlin standard library is a runtime dependency of the developer APK. The APK includes its attribution and the Apache license in `demo/src/main/assets`. Source: <https://github.com/JetBrains/kotlin/tree/v2.3.21/libraries/stdlib>.

Android Gradle Plugin, Android SDK, emulator and JDK are separately obtained development tools under their own licenses. They and their caches/system images are not bundled in the public repository. JUnit 4.13.2, Hamcrest and org.json 20240303 are test dependencies, not application code. The optional host-test JAR is a generated private integration artifact containing those test dependencies and is not part of the source distribution.
