// 校验 release/ 中的 deb / apk 是否内嵌当前内容包（哈希、课程结构、正文一致）。
// 用法：pnpm verify:release [release目录]
// 依赖：xz + tar（Windows Git Bash / Linux 均可用），@electron/asar，jszip。
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import zlib from 'node:zlib'
import crypto from 'node:crypto'
import { spawnSync } from 'node:child_process'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const releaseDir = path.resolve(process.argv[2] || path.join(root, 'release'))
const requireRoot = createRequire(path.join(root, 'package.json'))
const requireWeb = createRequire(path.join(root, 'apps/web/package.json'))
const asar = requireRoot('@electron/asar')
const JSZip = requireWeb('jszip')

const localPack = JSON.parse(fs.readFileSync(path.join(root, 'apps/web/public/content/pack.json'), 'utf8'))
const info = JSON.parse(fs.readFileSync(path.join(root, 'apps/web/public/content/build-info.json'), 'utf8'))
if (localPack.manifest.hash !== info.hash) {
  console.error(`本地内容包自相矛盾：pack=${localPack.manifest.hash} build-info=${info.hash}`)
  process.exit(1)
}

const expectedHash = info.hash
const EXPECTED_LESSONS = 76
const EXPECTED_STAGES = 11
const CANONICAL = ['id', 'name', 'version', 'visibility', 'minAppVersion', 'license', 'description', 'hash', 'lessonCount', 'stageCount']

function normalize(pack) {
  const manifest = {}
  for (const key of CANONICAL) if (pack.manifest?.[key] !== undefined) manifest[key] = pack.manifest[key]
  return JSON.stringify({ manifest, stages: pack.stages, lessons: pack.lessons, glossary: pack.glossary })
}

const expectedContent = normalize(localPack)

function checkPack(pack, label) {
  if (pack.manifest?.hash !== expectedHash) throw new Error(`${label} 内容哈希=${pack.manifest?.hash}，期望=${expectedHash}`)
  if (pack.stages?.length !== EXPECTED_STAGES) throw new Error(`${label} 阶段数=${pack.stages?.length}`)
  if (pack.lessons?.length !== EXPECTED_LESSONS) throw new Error(`${label} 课程数=${pack.lessons?.length}`)
  if (normalize(pack) !== expectedContent) throw new Error(`${label} 课程内容与当前工作区不一致（哈希相同但正文不同）`)
  return `${pack.lessons.length} 节 / ${pack.stages.length} 阶段 / ${expectedHash.slice(0, 16)}…`
}

function sha256File(file) {
  return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')
}

function readArEntries(file) {
  const buf = fs.readFileSync(file)
  if (buf.subarray(0, 8).toString() !== '!<arch>\n') throw new Error('不是 ar 归档')
  const entries = []
  let off = 8
  while (off + 60 <= buf.length) {
    const header = buf.subarray(off, off + 60)
    const name = header.subarray(0, 16).toString().trim().replace(/\/$/, '')
    const size = Number.parseInt(header.subarray(48, 58).toString().trim(), 10)
    if (!name || !Number.isFinite(size)) break
    const start = off + 60
    entries.push({ name, data: buf.subarray(start, start + size) })
    off = start + size + (size % 2)
  }
  return entries
}

function msysPath(p) {
  if (process.platform !== 'win32') return p
  return '/' + p.replace(/\\/g, '/').replace(/^([A-Za-z]):/, (_, drive) => drive.toLowerCase())
}

function extractDeb(file, tmp) {
  const entry = readArEntries(file).find((e) => e.name.startsWith('data.tar.'))
  if (!entry) throw new Error('deb 内没有 data.tar.*')
  const out = path.join(tmp, 'root')
  fs.mkdirSync(out, { recursive: true })
  let tarInput
  if (entry.name.endsWith('.xz')) {
    const dataFile = path.join(tmp, entry.name)
    fs.writeFileSync(dataFile, entry.data)
    const r = spawnSync('xz', ['-dc', dataFile], { maxBuffer: 512 * 1024 * 1024 })
    if (r.status !== 0) throw new Error(`xz 解压失败：${(r.stderr || '').toString().slice(0, 300)}`)
    tarInput = r.stdout
  } else if (entry.name.endsWith('.gz')) {
    tarInput = zlib.gunzipSync(entry.data)
  } else {
    throw new Error(`不支持的压缩格式：${entry.name}`)
  }
  const t = spawnSync('tar', ['--force-local', '-xf', '-', '-C', msysPath(out)], { input: tarInput, maxBuffer: 64 * 1024 * 1024 })
  if (t.status !== 0) throw new Error(`tar 解包失败：${(t.stderr || '').toString().slice(0, 300)}`)
  return out
}

function findFile(dir, name) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      const found = findFile(p, name)
      if (found) return found
    } else if (entry.name === name) return p
  }
  return null
}

async function checkApk(file) {
  const zip = await JSZip.loadAsync(fs.readFileSync(file))
  const find = (suffix) => Object.keys(zip.files).find((n) => n.endsWith(suffix))
  const infoEntry = find('assets/public/content/build-info.json')
  const packEntry = find('assets/public/content/pack.json')
  if (!infoEntry || !packEntry) throw new Error('APK 内缺少 content/build-info.json 或 pack.json')
  const embeddedInfo = JSON.parse(await zip.files[infoEntry].async('string'))
  if (embeddedInfo.hash !== expectedHash) throw new Error(`build-info 哈希=${embeddedInfo.hash}`)
  return checkPack(JSON.parse(await zip.files[packEntry].async('string')), 'APK')
}

function checkAsar(asarPath, label) {
  const entries = asar.listPackage(asarPath)
  const pick = (suffix) => {
    const hit = entries.find((n) => n.replace(/\\/g, '/').endsWith(suffix))
    return hit ? hit.replace(/^[\\/]+/, '') : null
  }
  const infoEntry = pick('web/content/build-info.json')
  const packEntry = pick('web/content/pack.json')
  if (!infoEntry || !packEntry) throw new Error(`${label} 的 asar 内缺少 web/content/build-info.json 或 pack.json`)
  const embeddedInfo = JSON.parse(asar.extractFile(asarPath, infoEntry).toString('utf8'))
  if (embeddedInfo.hash !== expectedHash) throw new Error(`${label} build-info 哈希=${embeddedInfo.hash}`)
  const pack = JSON.parse(asar.extractFile(asarPath, packEntry).toString('utf8'))
  return checkPack(pack, label)
}

function checkDeb(file) {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'rl-deb-'))
  try {
    const extracted = extractDeb(file, tmp)
    const asarPath = findFile(extracted, 'app.asar')
    if (!asarPath) throw new Error('deb 内缺少 app.asar')
    return checkAsar(asarPath, 'deb')
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true })
  }
}

function find7za() {
  if (process.env.RL_7ZA) return process.env.RL_7ZA
  const pnpmDir = path.join(root, 'node_modules/.pnpm')
  const platform = process.platform === 'win32' ? 'win' : process.platform === 'darwin' ? 'mac' : 'linux'
  const arch = { x64: 'x64', arm64: 'arm64', ia32: 'ia32', arm: 'arm' }[process.arch] || 'x64'
  if (fs.existsSync(pnpmDir)) {
    for (const dir of fs.readdirSync(pnpmDir)) {
      if (!dir.startsWith('7zip-bin@')) continue
      const p = path.join(pnpmDir, dir, 'node_modules/7zip-bin', platform, arch, platform === 'win' ? '7za.exe' : '7za')
      if (!fs.existsSync(p)) continue
      if (platform !== 'win') {
        try { fs.chmodSync(p, 0o755) } catch {}
      }
      return p
    }
  }
  for (const name of ['7za', '7z']) {
    if (spawnSync(name, ['i'], { stdio: 'ignore' }).status === 0) return name
  }
  return null
}

function checkExe(file, sevenZip) {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'rl-exe-'))
  try {
    const out = path.join(tmp, 'exe')
    fs.mkdirSync(out, { recursive: true })
    const r = spawnSync(sevenZip, ['x', file, `-o${out}`, '-y'], { maxBuffer: 256 * 1024 * 1024 })
    if (r.status !== 0) {
      const detail = `${r.error?.message || ''} ${r.stdout || ''}${r.stderr || ''}`.toString().trim().slice(0, 300)
      throw new Error(`7za 解包失败（${r.status}）：${detail}`)
    }
    const asarPath = findFile(out, 'app.asar')
    if (!asarPath) throw new Error('exe 内缺少 resources/app.asar')
    return checkAsar(asarPath, 'exe')
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true })
  }
}

const files = fs.existsSync(releaseDir) ? fs.readdirSync(releaseDir) : []
const apks = files.filter((f) => f.endsWith('.apk')).sort()
const debs = files.filter((f) => f.endsWith('.deb')).sort()
if (!apks.length && !debs.length) {
  console.error(`未找到 deb/apk：${releaseDir}`)
  process.exit(1)
}

let failed = 0
for (const [kind, list] of [['apk', apks], ['deb', debs]]) {
  for (const name of list) {
    const file = path.join(releaseDir, name)
    try {
      const detail = kind === 'apk' ? await checkApk(file) : checkDeb(file)
      console.log(`PASS  ${name}  ${detail}  sha256=${sha256File(file).slice(0, 16)}…`)
    } catch (e) {
      failed++
      console.log(`FAIL  ${name}  ${e.message}`)
    }
  }
}

const exes = files.filter((f) => f.toLowerCase().endsWith('.exe'))
if (exes.length) {
  const sevenZip = find7za()
  for (const name of exes) {
    const file = path.join(releaseDir, name)
    if (!sevenZip) {
      console.log(`SKIP  ${name}  未找到 7za/7z，无法解包（设置 RL_7ZA 后重试）`)
      continue
    }
    try {
      const detail = checkExe(file, sevenZip)
      console.log(`PASS  ${name}  ${detail}  sha256=${sha256File(file).slice(0, 16)}…`)
    } catch (e) {
      failed++
      console.log(`FAIL  ${name}  ${e.message}`)
    }
  }
}

console.log(failed ? `\nVERIFY_RELEASE_FAIL ${failed}` : '\nVERIFY_RELEASE_OK')
process.exit(failed ? 1 : 0)
