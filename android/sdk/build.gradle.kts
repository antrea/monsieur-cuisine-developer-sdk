plugins { kotlin("jvm"); `java-library`; `maven-publish` }
group = "org.blackstufflabs.monsieurcuisine"
version = "2.0.0-dev0"
java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
    withSourcesJar()
}
kotlin { compilerOptions { jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17) } }
dependencies { testImplementation("junit:junit:4.13.2"); testImplementation("org.json:json:20240303") }
tasks.test { useJUnit(); testLogging { events("passed", "failed", "skipped") } }
tasks.register<Jar>("hostJar") {
    dependsOn(tasks.testClasses)
    archiveClassifier.set("host-tests")
    duplicatesStrategy = DuplicatesStrategy.EXCLUDE
    from(sourceSets.main.get().output, sourceSets.test.get().output)
    from(configurations.testRuntimeClasspath.get().filter { it.extension=="jar" }.map { zipTree(it) })
    exclude("META-INF/*.SF", "META-INF/*.RSA", "META-INF/*.DSA")
}
tasks.register<Jar>("codecProbeJar") {
    dependsOn(tasks.testClasses)
    archiveClassifier.set("codec-probe")
    duplicatesStrategy = DuplicatesStrategy.EXCLUDE
    from(sourceSets.main.get().output, sourceSets.test.get().output)
    from(configurations.testRuntimeClasspath.get().filter { it.extension=="jar" }.map { zipTree(it) })
    exclude("META-INF/*.SF", "META-INF/*.RSA", "META-INF/*.DSA")
}
publishing {
    publications { create<MavenPublication>("sdk") { from(components["java"]); artifactId="monsieur-cuisine-sdk" } }
    repositories { maven { url=uri(rootProject.layout.buildDirectory.dir("repository")) } }
}
