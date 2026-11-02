import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'
import { execFileSync } from 'node:child_process'
import yaml from 'js-yaml'

const root = path.resolve(import.meta.dirname, '..')
const packRoot = path.join(root, 'content/packs/public')
const outDir = path.join(root, 'apps/web/public/content')
const manifestPath = path.join(packRoot, 'manifest.json')

if (!fs.existsSync(manifestPath)) throw new Error('missing content/packs/public/manifest.json')
const baseManifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'))

function walk(dir) {
  const out = []
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) out.push(...walk(p))
    else out.push(p)
  }
  return out
}

const courseDir = path.join(packRoot, 'courses')
const lessons = []
const stageOrder = []

for (const file of walk(courseDir)) {
  if (path.basename(file) !== 'meta.yaml') continue
  const dir = path.dirname(file)
  const meta = yaml.load(fs.readFileSync(file, 'utf8')) || {}
  const mdPath = path.join(dir, 'lesson.md')
  const markdown = fs.existsSync(mdPath) ? fs.readFileSync(mdPath, 'utf8') : ''
  lessons.push({
    id: meta.id,
    stage: meta.stage,
    title: meta.title,
    durationMin: meta.durationMin ?? 30,
    type: meta.type ?? 'teach',
    output: meta.output ?? '',
    tags: meta.tags ?? [],
    sources: meta.sources ?? [],
    experiment: meta.experiment ?? null,
    quiz: meta.quiz ?? [],
    markdown,
  })
  if (!stageOrder.includes(meta.stage)) stageOrder.push(meta.stage)
}

lessons.sort((a, b) => a.id.localeCompare(b.id, 'en', { numeric: true }))
stageOrder.sort((a, b) => Number(a.slice(1)) - Number(b.slice(1)))

const stageTitles = {
  s0: ['地图与工具', '从整机架构到 Linux / Git / Docker / 安全底线'],
  s1: ['ROS1 核心', '工作空间、节点、topic、service、launch、rosbag、TF'],
  s2: ['ROS2 核心与迁移', 'rclpy、QoS、action、lifecycle、composition、DDS、bag、bridge'],
  s3: ['建模与坐标', 'URDF / xacro、TF2、RViz、四连杆几何'],
  s4: ['硬件接口', 'CAN / vcan、CANopen、串口、PLC 报文、100Hz、时间同步'],
  s5: ['感知与标定', 'IMU、LiDAR、Camera、外参、20 点触地法、符号核对'],
  s6: ['控制与安全', '遥操映射、限幅、状态机、三级停机、看门狗、故障注入'],
  s7: ['导航与定位', 'SLAM、定位、Nav2、代价地图、调参'],
  s8: ['部署与运维', 'Compose、systemd、网络、日志、bag 诊断、升级回滚'],
  s9: ['业务专项复刻', '远控全链路、Edge Bridge、配置、演示、验收'],
  s10: ['全栈毕业项目', '仿真挖机远控全链路 + 自动测试 + 验收报告'],
}

const stages = stageOrder.map((id) => ({
  id,
  title: stageTitles[id]?.[0] ?? id.toUpperCase(),
  desc: stageTitles[id]?.[1] ?? '',
  lessons: lessons.filter((l) => l.stage === id).map((l) => l.id),
}))

let glossary = []
const glossaryPath = path.join(packRoot, 'glossary.json')
if (fs.existsSync(glossaryPath)) glossary = JSON.parse(fs.readFileSync(glossaryPath, 'utf8'))

let coverage = null
const coveragePath = path.join(root, 'docs/coverage-summary.json')
if (fs.existsSync(coveragePath)) coverage = JSON.parse(fs.readFileSync(coveragePath, 'utf8'))

const CANONICAL_MANIFEST_FIELDS = [
  'id',
  'name',
  'version',
  'visibility',
  'minAppVersion',
  'license',
  'description',
]

// 与 packages/core/src/pack.ts 保持同一规范；构建元数据不参与哈希。
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

const canonical = JSON.stringify({
  manifest: canonicalManifest(baseManifest),
  stages,
  lessons,
  glossary,
})
const hash = crypto.createHash('sha256').update(canonical).digest('hex')

const manifest = {
  ...baseManifest,
  id: baseManifest.id,
  version: baseManifest.version,
  minAppVersion: baseManifest.min_app_version ?? '0.1.0',
  visibility: baseManifest.visibility ?? 'public',
  builtAt: new Date().toISOString(),
  hash,
  lessonCount: lessons.length,
  stageCount: stages.length,
}

const pack = { manifest, stages, lessons, glossary, coverage }
fs.mkdirSync(outDir, { recursive: true })
fs.writeFileSync(path.join(outDir, 'pack.json'), JSON.stringify(pack), 'utf8')

// 同步媒体目录（如存在）
const mediaSrc = path.join(packRoot, 'media')
const mediaDst = path.join(outDir, 'media')
if (fs.existsSync(mediaSrc)) fs.cpSync(mediaSrc, mediaDst, { recursive: true })

function gitCommit() {
  try {
    return execFileSync('git', ['rev-parse', '--short', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim() || 'unknown'
  } catch {
    return 'unknown'
  }
}

const stats = {
  packId: manifest.id,
  version: manifest.version,
  hash,
  lessons: lessons.length,
  stages: stages.length,
  bytes: fs.statSync(path.join(outDir, 'pack.json')).size,
  commit: process.env.RL_GIT_COMMIT || gitCommit(),
  builtAt: new Date().toISOString(),
}
fs.writeFileSync(path.join(outDir, 'build-info.json'), JSON.stringify(stats, null, 2), 'utf8')
console.log(JSON.stringify(stats, null, 2))
