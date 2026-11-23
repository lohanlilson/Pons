import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

val ver = Properties().apply { rootProject.file("version.properties").inputStream().use { load(it) } }

android {
    namespace = "io.github.lohanlilson.pons"
    compileSdk = 36

    defaultConfig {
        applicationId = "io.github.lohanlilson.pons"
        minSdk = 26
        targetSdk = 36
        versionCode = ver.getProperty("versionCode").toInt()
        versionName = ver.getProperty("versionName")
    }

    // Assinatura do APK: chave guardada nos segredos do GitHub (as atualizações precisam da mesma chave)
    val ks = System.getenv("PONS_KEYSTORE")
    signingConfigs {
        if (ks != null && file(ks).exists()) {
            create("release") {
                storeFile = file(ks)
                storePassword = System.getenv("PONS_KEYSTORE_PASS")
                keyAlias = System.getenv("PONS_KEY_ALIAS") ?: "pons"
                keyPassword = System.getenv("PONS_KEY_PASS") ?: System.getenv("PONS_KEYSTORE_PASS")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            signingConfig = signingConfigs.findByName("release") ?: signingConfigs.getByName("debug")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlin {
        compilerOptions { jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17) }
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
}

dependencies {
    val bom = platform("androidx.compose:compose-bom:2025.12.01")
    implementation(bom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.activity:activity-compose:1.11.0")
    implementation("androidx.core:core-ktx:1.17.0")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.9.4")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.2")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-play-services:1.10.2")
    implementation("com.google.android.gms:play-services-code-scanner:16.1.0")          // QR do PC, boleto e NF-e (sem pedir câmera)
    implementation("com.google.android.gms:play-services-mlkit-document-scanner:16.0.0") // escanear documento em PDF
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
}
