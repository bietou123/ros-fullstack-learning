// 打包 Android APK：内容包 + 前端 → Capacitor 同步 → Gradle assembleRelease。
// 用法：pnpm package:apk（需要 JDK 17 与 Android SDK）
import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'
import { execSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const releaseDir = path.join(root, 'release')
const androidDir = path.join(root, 'apps/mobile/android')
const version = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8')).version

function run(cmd, opts = {}) {
  console.log(`\n$ ${cmd}`)
  execSync(cmd, { cwd: root, stdio: 'inherit', shell: true, ...opts })
}

function sha256(file) {
  return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')
}

function findSdk() {
  if (process.env.ANDROID_HOME) return process.env.ANDROID_HOME
  if (process.env.ANDROID_SDK_ROOT) return process.env.ANDROID_SDK_ROOT
  const localProps = path.join(androidDir, 'local.properties')
  if (fs.existsSync(localProps)) {
    const m = fs.readFileSync(localProps, 'utf8').match(/^sdk\.dir=(.+)$/m)
    if (m) return m[1].trim()
  }
  throw new Error('未找到 Android SDK：设置 ANDROID_HOME 或在 android/local.properties 配置 sdk.dir')
}

function findJavaHome() {
  if (process.env.JAVA_HOME) return process.env.JAVA_HOME
  const fallback = 'D:/Private data/AI/Tools/jdk-17.0.2'
  if (fs.existsSync(path.join(fallback, 'bin', process.platform === 'win32' ? 'java.exe' : 'java'))) return fallback
  throw new Error('未找到 JDK 17：设置 JAVA_HOME')
}

run('pnpm build')
run('node scripts/scan-secrets.mjs')
run('node scripts/verify.mjs --strict')
run('pnpm --filter @rl/mobile exec cap sync android')

const gradle = path.join(androidDir, process.platform === 'win32' ? 'gradlew.bat' : 'gradlew')
run(`"${gradle}" assembleRelease`, {
  cwd: androidDir,
  env: {
    ...process.env,
    JAVA_HOME: findJavaHome(),
    ANDROID_HOME: findSdk(),
    ANDROID_SDK_ROOT: findSdk(),
  },
})

const apk = path.join(androidDir, 'app/build/outputs/apk/release/app-release.apk')
if (!fs.existsSync(apk)) throw new Error(`未找到 APK：${apk}`)

fs.mkdirSync(releaseDir, { recursive: true })
const outName = `IndustryRoboticsLearning-${version}-arm64.apk`
const dst = path.join(releaseDir, outName)
fs.copyFileSync(apk, dst)
console.log(`RELEASE ${outName} ${(fs.statSync(dst).size / 1024 / 1024).toFixed(2)} MB sha256=${sha256(dst)}`)
