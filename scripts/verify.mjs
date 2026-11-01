// 全量校验：内容包完整性、课程结构、覆盖率缺口、敏感信息扫描。
// 用法：node scripts/verify.mjs [--full]
//   --full 额外执行 typecheck / unit test / 前端构建
import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const full = process.argv.includes('--full')
const strict = process.argv.includes('--strict')
const failures = []
const warnings = []
const checks = []

function check(name, fn) {
  try {
    const detail = fn()
    checks.push({ name, ok: true, detail })
  } catch (e) {
    checks.push({ name, ok: false, detail: e.message })
    failures.push(name)
  }
}

function readJson(p) {
  return JSON.parse(fs.readFileSync(p, 'utf8'))
}

const CANONICAL_MANIFEST_FIELDS = [
  'id',
  'name',
  'version',
  'visibility',
  'minAppVersion',
  'license',
  'description',
]

// 与 packages/core/src/pack.ts、scripts/build-pack.mjs 保持同一规范。
function canonicalManifest(base) {
  const src = {
    id: base.id,
    name: base.name,
    version: base.version,
    visibility: base.visibility ?? 'public',
    minAppVersion: base.min_app_version ?? base.minAppVersion ?? '0.1.0',
    license: base.license,
    description: base.description,
  }
  const out = {}
  for (const key of CANONICAL_MANIFEST_FIELDS) {
    if (src[key] !== undefined) out[key] = src[key]
  }
  return out
}

const packPath = path.join(root, 'apps/web/public/content/pack.json')
const infoPath = path.join(root, 'apps/web/public/content/build-info.json')

check('内容包存在', () => {
  if (!fs.existsSync(packPath)) throw new Error('缺少 apps/web/public/content/pack.json，先运行 pnpm build:content')
  return 'ok'
})

const pack = fs.existsSync(packPath) ? readJson(packPath) : null
const info = fs.existsSync(infoPath) ? readJson(infoPath) : null

check('内容包哈希一致', () => {
  if (!pack || !info) throw new Error('缺少 pack.json 或 build-info.json')
  const basePath = path.join(root, 'content/packs/public/manifest.json')
  const baseManifest = fs.existsSync(basePath) ? readJson(basePath) : { id: pack.manifest.id, version: pack.manifest.version }
  const canonical = JSON.stringify({
    manifest: canonicalManifest(baseManifest),
    stages: pack.stages,
    lessons: pack.lessons,
    glossary: pack.glossary,
  })
  const actual = crypto.createHash('sha256').update(canonical).digest('hex')
  if (actual !== pack.manifest.hash) throw new Error(`manifest.hash=${pack.manifest.hash} 实际=${actual}`)
  if (info.hash !== pack.manifest.hash) throw new Error(`build-info.hash=${info.hash} 与 manifest 不一致`)
  return pack.manifest.hash.slice(0, 16) + '…'
})

check('课程数量与阶段数', () => {
  if (!pack) throw new Error('无内容包')
  if (pack.stages.length !== 11) throw new Error(`stages=${pack.stages.length}，应为 11`)
  if (pack.lessons.length !== 76) throw new Error(`lessons=${pack.lessons.length}，应为 76`)
  return `${pack.stages.length} 阶段 / ${pack.lessons.length} 节`
})

check('每节课结构完整', () => {
  if (!pack) throw new Error('无内容包')
  const bad = []
  const pending = []
  for (const l of pack.lessons) {
    if (!l.id || !l.title || !l.stage) bad.push(`${l.id || '?'} 缺 id/title/stage`)
    if (!Array.isArray(l.quiz)) bad.push(`${l.id} 缺少 quiz 字段`)
    else if (l.quiz.length < 3) pending.push(`${l.id} 测验 ${l.quiz.length} 题`)
    if (typeof l.markdown !== 'string') bad.push(`${l.id} 缺少正文`)
    else if (l.markdown.trim().length < 200) pending.push(`${l.id} 正文过短（骨架）`)
    for (const q of l.quiz || []) {
      if (!Array.isArray(q.options) || q.options.length < 2) bad.push(`${l.id} 题目选项不足`)
      if (typeof q.answer !== 'number' || q.answer < 0 || q.answer >= (q.options || []).length) bad.push(`${l.id} 答案下标越界`)
    }
  }
  if (bad.length) throw new Error(bad.slice(0, 8).join('；') + (bad.length > 8 ? ` …共 ${bad.length} 项` : ''))
  if (pending.length) {
    if (strict) throw new Error('未完成课程：' + pending.slice(0, 8).join('；') + ` …共 ${pending.length} 节`)
    warnings.push(`待补内容 ${pending.length} 节（骨架课程，--strict 会判失败）`)
  }
  return pending.length ? `结构合法；${pack.lessons.length - pending.length}/${pack.lessons.length} 节已补齐` : '全部通过'
})

check('课程 id 唯一且阶段有序', () => {
  if (!pack) throw new Error('无内容包')
  const ids = new Set()
  const dup = []
  for (const l of pack.lessons) {
    if (ids.has(l.id)) dup.push(l.id)
    ids.add(l.id)
  }
  if (dup.length) throw new Error('重复 id：' + dup.join(', '))
  const stageIds = pack.stages.map((s) => s.id)
  const order = new Map(stageIds.map((id, i) => [id, i]))
  let last = -1
  for (const l of pack.lessons) {
    const i = order.get(l.stage)
    if (i === undefined) throw new Error(`${l.id} 的 stage=${l.stage} 不存在`)
    if (i < last) throw new Error(`${l.id} 阶段顺序错乱`)
    last = i
  }
  return stageIds.join(' → ')
})

check('覆盖率台账存在且无未映射资料', () => {
  const csvPath = path.join(root, 'docs/coverage.csv')
  if (!fs.existsSync(csvPath)) throw new Error('缺少 docs/coverage.csv，先运行 pnpm gen:coverage')
  const lines = fs.readFileSync(csvPath, 'utf8').trim().split(/\r?\n/)
  const header = lines.shift()
  if (!header.includes('lesson')) throw new Error('coverage.csv 缺少 lesson 列')
  const rows = lines.map(parseCsvLine)
  const missing = rows.filter((r) => !r.lesson || r.lesson === '—')
  if (missing.length) throw new Error(`${missing.length} 份资料未映射课程：${missing.slice(0, 5).map((r) => r.source).join('、')}`)
  const lessonsCovered = new Set(rows.map((r) => r.lesson))
  const declared = new Set(readLessonSources().map((r) => r.lesson))
  const packLessons = pack ? pack.lessons.map((l) => l.id) : []
  const uncovered = packLessons.filter((id) => !lessonsCovered.has(id) && !declared.has(id))
  if (uncovered.length) warnings.push(`无资料支撑的课程 ${uncovered.length} 节：${uncovered.slice(0, 6).join('、')}`)
  return `${rows.length} 份资料 → ${lessonsCovered.size} 节直接映射；${declared.size}/${packLessons.length} 节有来源声明`
})

check('课程来源声明完整', () => {
  if (!pack) throw new Error('无内容包')
  const csvPath = path.join(root, 'docs/coverage.csv')
  const lessonPath = path.join(root, 'docs/lesson-sources.csv')
  if (!fs.existsSync(lessonPath)) throw new Error('缺少 docs/lesson-sources.csv，先运行 pnpm gen:coverage')
  const known = new Set()
  for (const r of fs.readFileSync(csvPath, 'utf8').trim().split(/\r?\n/).slice(1).map(parseCsvLine)) {
    known.add(r.source)
    known.add(r.chapter)
  }
  const rows = readLessonSources()
  if (rows.length !== pack.lessons.length) throw new Error(`来源声明 ${rows.length} 节，课程包 ${pack.lessons.length} 节`)
  const byId = new Map(rows.map((r) => [r.lesson, r]))
  const bad = []
  for (const l of pack.lessons) {
    const r = byId.get(l.id)
    if (!r) bad.push(`${l.id} 缺少来源声明`)
    else if (!r.sources.length) bad.push(`${l.id} 来源为空`)
    else {
      const unknown = r.sources.filter((s) => !known.has(s))
      if (unknown.length) bad.push(`${l.id} 来源无法解析：${unknown.join('、')}`)
    }
  }
  if (bad.length) throw new Error(bad.slice(0, 6).join('；') + (bad.length > 6 ? ` …共 ${bad.length} 项` : ''))
  const total = rows.reduce((n, r) => n + r.sources.length, 0)
  return `${rows.length}/${pack.lessons.length} 节 → ${total} 条来源关联`
})

check('敏感信息扫描', () => {
  const r = spawnSync(process.execPath, [path.join(root, 'scripts/scan-secrets.mjs')], { encoding: 'utf8' })
  const out = (r.stdout || '') + (r.stderr || '')
  if (r.status !== 0) throw new Error(out.trim().split('\n').slice(0, 12).join(' | '))
  return 'SCAN_OK'
})

if (full) {
  for (const [name, cmd, args] of [
    ['类型检查', 'pnpm', ['typecheck']],
    ['单元测试', 'pnpm', ['test']],
    ['前端构建', 'pnpm', ['build']],
  ]) {
    check(name, () => {
      const r = spawnSync(cmd, args, { cwd: root, shell: true, encoding: 'utf8', timeout: 600000 })
      if (r.status !== 0) throw new Error(((r.stdout || '') + (r.stderr || '')).trim().split('\n').slice(-12).join(' | '))
      return 'ok'
    })
  }
}

function parseCsvRow(line) {
  const out = []
  let cur = ''
  let quoted = false
  for (let i = 0; i < line.length; i++) {
    const c = line[i]
    if (quoted) {
      if (c === '"' && line[i + 1] === '"') {
        cur += '"'
        i++
      } else if (c === '"') quoted = false
      else cur += c
    } else if (c === '"') quoted = true
    else if (c === ',') {
      out.push(cur)
      cur = ''
    } else cur += c
  }
  out.push(cur)
  return out
}

function parseCsvLine(line) {
  const out = parseCsvRow(line)
  return { source: out[0], chapter: out[1], status: out[2], lesson: out[3], note: out[4] }
}

function readLessonSources() {
  const file = path.join(root, 'docs/lesson-sources.csv')
  if (!fs.existsSync(file)) return []
  const lines = fs.readFileSync(file, 'utf8').trim().split(/\r?\n/)
  const header = parseCsvRow(lines.shift())
  const iLesson = header.indexOf('lesson')
  const iSources = header.indexOf('sources')
  if (iLesson < 0 || iSources < 0) throw new Error('lesson-sources.csv 缺少 lesson 或 sources 列')
  return lines.filter((l) => l.trim()).map((line) => {
    const r = parseCsvRow(line)
    return { lesson: r[iLesson], sources: (r[iSources] || '').split('、').filter(Boolean) }
  })
}

const width = Math.max(...checks.map((c) => c.name.length))
for (const c of checks) console.log(`${c.ok ? 'PASS' : 'FAIL'}  ${c.name.padEnd(width)}  ${c.detail}`)
for (const w of warnings) console.log(`WARN  ${w}`)
console.log(failures.length ? `\nVERIFY_FAIL ${failures.length}/${checks.length}` : `\nVERIFY_OK ${checks.length}/${checks.length}`)
process.exit(failures.length ? 1 : 0)
