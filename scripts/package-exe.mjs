// 打包 Windows 安装包：内容包 + 前端 → 桌面端资源 → electron-builder。
// 用法：pnpm package:exe
import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'
import { execSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const releaseDir = path.join(root, 'release')
const desktopWeb = path.join(root, 'apps/desktop/web')
const webDist = path.join(root, 'apps/web/dist')

function run(cmd, opts = {}) {
  console.log(`\n$ ${cmd}`)
  execSync(cmd, { cwd: root, stdio: 'inherit', shell: true, ...opts })
}

function sha256(file) {
  return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')
}

run('pnpm build')
run('node scripts/scan-secrets.mjs')
run('node scripts/verify.mjs --strict')

fs.rmSync(desktopWeb, { recursive: true, force: true })
fs.cpSync(webDist, desktopWeb, { recursive: true })

run('pnpm --filter @rl/desktop exec electron-builder --win nsis --x64', {
  env: {
    ...process.env,
    ELECTRON_MIRROR: 'https://npmmirror.com/mirrors/electron/',
    ELECTRON_BUILDER_BINARIES_MIRROR: 'https://npmmirror.com/mirrors/electron-builder-binaries/',
    CSC_IDENTITY_AUTO_DISCOVERY: 'false',
  },
})

const distDir = path.join(root, 'dist')
const artifacts = fs.readdirSync(distDir).filter((f) => f.endsWith('.exe') && !f.endsWith('.blockmap'))
if (artifacts.length === 0) throw new Error('未找到 exe 产物，检查 electron-builder 输出')

fs.mkdirSync(releaseDir, { recursive: true })
for (const name of artifacts) {
  const src = path.join(distDir, name)
  const dst = path.join(releaseDir, name)
  fs.copyFileSync(src, dst)
  console.log(`RELEASE ${name} ${(fs.statSync(dst).size / 1024 / 1024).toFixed(2)} MB sha256=${sha256(dst)}`)
}
