// 构建前端、装配桌面端并运行隐藏窗口冒烟。
// 用法：pnpm smoke:desktop
//   RL_SMOKE_OFFLINE=1 时强制断网，并额外校验测验流程。
import fs from 'node:fs'
import path from 'node:path'
import { spawnSync } from 'node:child_process'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const desktopDir = path.join(root, 'apps/desktop')
const webDist = path.join(root, 'apps/web/dist')
const desktopWeb = path.join(desktopDir, 'web')
const infoPath = path.join(root, 'apps/web/public/content/build-info.json')

function run(cmd, args, opts = {}) {
  const r = spawnSync(cmd, args, { cwd: root, stdio: 'inherit', shell: process.platform === 'win32', ...opts })
  if (r.status !== 0) process.exit(r.status ?? 1)
}

console.log('构建内容包与前端…')
run('pnpm', ['build'])

if (!fs.existsSync(path.join(webDist, 'index.html'))) throw new Error('前端构建产物缺失：apps/web/dist')
fs.rmSync(desktopWeb, { recursive: true, force: true })
fs.cpSync(webDist, desktopWeb, { recursive: true })

const info = JSON.parse(fs.readFileSync(infoPath, 'utf8'))
const electron = createRequire(path.join(desktopDir, 'package.json'))('electron')
const env = {
  ...process.env,
  RL_SMOKE: '1',
  RL_EXPECTED_HASH: info.hash,
  RL_SMOKE_OUT: process.env.RL_SMOKE_OUT || path.join(desktopDir, 'smoke'),
}
if (process.env.RL_SMOKE_OFFLINE) env.RL_SMOKE_OFFLINE = '1'

console.log(`启动桌面冒烟（offline=${env.RL_SMOKE_OFFLINE === '1'}）…`)
const r = spawnSync(electron, ['.'], { cwd: desktopDir, stdio: 'inherit', env })
process.exit(r.status ?? 1)
