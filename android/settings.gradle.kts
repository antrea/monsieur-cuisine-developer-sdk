pluginManagement { repositories { google(); mavenCentral(); gradlePluginPortal() } }
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories { google(); mavenCentral() }
}
rootProject.name = "Monsieur Cuisine Developer SDK"
include(":sdk")
if (providers.gradleProperty("includeAndroidDemo").orNull != "false") include(":demo", ":oemprobe", ":manager")
