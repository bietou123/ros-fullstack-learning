import fs from 'node:fs'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const kbIndex = 'C:/Users/zjy33/Desktop/工程机器人/知识库/index.json'
const outDir = path.join(root, 'docs')

const LESSONS = {
  '01_产品与需求': ['S0-01', 'S9-01', 'S9-05'],
  '02_架构与协议': ['S4-05', 'S4-07', 'S9-01', 'S9-02'],
  '03_硬件与电气': ['S4-01', 'S4-02', 'S4-04', 'S5-02', 'S5-03'],
  '04_标定与算法': ['S3-05', 'S5-04', 'S5-05', 'S5-06', 'S5-07'],
  '05_交付实施SOP': ['S0-08', 'S5-06', 'S9-05', 'S9-06', 'S9-07'],
  '06_软件部署与运维': ['S8-01', 'S8-02', 'S8-03', 'S8-04', 'S8-06', 'S9-02'],
  '07_项目管理与流程': ['S0-05', 'S9-05', 'S9-04'],
  '08_市场销售与品牌': ['S0-01'],
  '09_培训与测试': ['S6-06', 'S6-07', 'S9-04', 'S9-05'],
  '10_参考资料': ['S3-05', 'S7-06'],
}

// 现场必做：整车安装/线束/验收/配置部署表/物料出货/SN 台账
const FIELD_PAT = /(线束预埋|线束制作|安装工艺|作业指导|施工|配置部署表|出货清单|物料清单|出厂测试报告|SN台账|硬件资产|验收签核|交接文档)/
// 可教学：协议/手册/教程/测试/部署/标定/算法
const TEACH_PAT = /(协议|手册|教程|指南|测试|用例|部署|标定|算法|方案|培训|命令|规范|需求|架构|流程|安全设计|电气接口|机械安装|项目说明|分工|索引|计划)/

function classify(name, category) {
  if (FIELD_PAT.test(name)) return 'field'
  if (category === '08_市场销售与品牌') return 'read'
  if (category === '10_参考资料') return 'read'
  if (category === '03_硬件与电气' && /(datasheet|说明书|图纸|规格书|BOM)/i.test(name)) return 'read'
  if (TEACH_PAT.test(name)) return 'teach'
  return 'read'
}

function lessonFor(category, name) {
  const base = LESSONS[category] || ['S0-01']
  if (/标定/.test(name)) return 'S5-05'
  if (/CAN|通信协议/.test(name)) return 'S4-05'
  if (/部署|LOT|IOT|信令/.test(name)) return 'S8-01'
  if (/测试|考核/.test(name)) return 'S6-06'
  if (/线束|安装|施工|验收/.test(name)) return 'S9-05'
  return base[0]
}

const rows = []
const idx = JSON.parse(fs.readFileSync(kbIndex, 'utf8'))
for (const f of idx.files) {
  const status = classify(f.file, f.category)
  rows.push({
    source: f.file,
    chapter: f.category,
    status,
    lesson: lessonFor(f.category, f.file),
    note: f.status === 'ok' ? `已抽取 ${f.chars} 字` : '无正文，仅图像/元数据',
  })
}

const specials = [
  ['A_术语表.md', 'A_术语表', 'teach', 'S0-01', '术语中英对照直接进课程'],
  ['B_设备与型号速查.md', 'B_设备与型号速查', 'read', 'S5-02', '型号速查，不作为教学主线'],
  ['C_现场踩坑与避雷清单.md', 'C_现场踩坑', 'teach', 'S0-08', '每节的「常见故障」来源'],
  ['D_文档索引.md', 'D_文档索引', 'read', 'S0-01', '资料地图'],
  ['E_ROS与Linux命令手册.md', 'E_命令手册', 'teach', 'S0-02', 'S0/S1 实验命令的主要来源'],
]

for (const [file, chapter, status, lesson, note] of specials) {
  rows.push({ source: file, chapter, status, lesson, note })
}

const liugong = [
  ['00-项目文档索引.md', 'read', 'S9-06'],
  ['01-CAN通信协议速查手册.md', 'teach', 'S9-01'],
  ['02-电气接口与引脚定义.md', 'teach', 'S4-05'],
  ['03-安全设计与状态机.md', 'teach', 'S6-03'],
  ['04-机械安装作业指导书.md', 'field', 'S9-05'],
  ['05-标定作业指导书.md', 'teach', 'S5-05'],
  ['06-部署验收签核表.md', 'field', 'S9-05'],
  ['07-物料与出货缺口台账.md', 'field', 'S9-07'],
  ['08-风险与待决事项台账.md', 'read', 'S9-07'],
  ['09-宝马展演示脚本与测试用例.md', 'teach', 'S9-04'],
  ['10-现场视频素材分析.md', 'read', 'S9-04'],
  ['11-硬件资产与SN台账.md', 'field', 'S9-06'],
  ['12-现场施工实施计划(8.06-8.14).md', 'field', 'S9-07'],
  ['柳工挖掘机智能化改造项目说明.md', 'teach', 'S9-01'],
  ['柳工项目交接文档.md', 'read', 'S9-06'],
  ['柳工项目各职能工作分工.md', 'read', 'S9-06'],
]
for (const [file, status, lesson] of liugong) {
  rows.push({ source: file, chapter: '工程机械专项', status, lesson, note: '仅进 private 包，受控' })
}

const csv = ['source,chapter,status,lesson,note']
for (const r of rows) {
  csv.push([r.source, r.chapter, r.status, r.lesson, r.note].map((v) => `"${String(v).replace(/"/g, '""')}"`).join(','))
}
fs.writeFileSync(path.join(outDir, 'coverage.csv'), csv.join('\n') + '\n', 'utf8')

// 课程级来源：以每节课 meta.yaml 的 sources 为准，避免把章级资料硬绑到单节课。
const sourceNames = new Set(rows.map((r) => r.source))
const chapterNames = new Set(rows.map((r) => r.chapter))
const SOURCE_ALIASES = {
  C_现场踩坑: 'C_现场踩坑与避雷清单.md',
  E_ROS与Linux命令手册: 'E_ROS与Linux命令手册.md',
  A_术语表: 'A_术语表.md',
  B_设备与型号速查: 'B_设备与型号速查.md',
  D_文档索引: 'D_文档索引.md',
}

function readLessonsMeta() {
  const coursesRoot = path.join(root, 'content/packs/public/courses')
  const out = []
  for (const stage of fs.readdirSync(coursesRoot)) {
    const stageDir = path.join(coursesRoot, stage)
    if (!fs.statSync(stageDir).isDirectory()) continue
    for (const dir of fs.readdirSync(stageDir)) {
      const metaPath = path.join(stageDir, dir, 'meta.yaml')
      if (!fs.existsSync(metaPath)) continue
      const text = fs.readFileSync(metaPath, 'utf8')
      const id = (text.match(/^id:\s*"?([^"\n]+)"?\s*$/m) || [])[1]
      const raw = (text.match(/^sources:\s*(\[.*\])\s*$/m) || [])[1]
      if (!id || !raw) throw new Error(`${metaPath} 缺少 id 或 sources`)
      const sources = JSON.parse(raw).map((s) => SOURCE_ALIASES[s] || s)
      const unknown = sources.filter((s) => !sourceNames.has(s) && !chapterNames.has(s))
      if (unknown.length) throw new Error(`${id} 的来源无法解析：${unknown.join('、')}`)
      if (!sources.length) throw new Error(`${id} 没有任何来源`)
      out.push({ lesson: id, stage, sources })
    }
  }
  return out.sort((a, b) => a.lesson.localeCompare(b.lesson, 'en', { numeric: true }))
}

const courseSources = readLessonsMeta()
const lessonCsv = ['lesson,stage,source_count,sources']
for (const r of courseSources) {
  lessonCsv.push([r.lesson, r.stage, r.sources.length, r.sources.join('、')].map((v) => `"${String(v).replace(/"/g, '""')}"`).join(','))
}
fs.writeFileSync(path.join(outDir, 'lesson-sources.csv'), lessonCsv.join('\n') + '\n', 'utf8')

const byChapter = {}
for (const r of rows) {
  byChapter[r.chapter] ??= { teach: 0, read: 0, field: 0 }
  byChapter[r.chapter][r.status]++
}

const chapterLevel = [
  ...Object.keys(LESSONS).map((c) => [c, chapterLevelStatus(c)]),
  ['A_术语表', 'teach'], ['B_设备与型号速查', 'read'], ['C_现场踩坑', 'teach'],
  ['D_文档索引', 'read'], ['E_命令手册', 'teach'], ['工程机械专项', 'teach'],
]

function chapterLevelStatus(c) {
  if (['08_市场销售与品牌', '10_参考资料'].includes(c)) return 'read'
  return 'teach'
}

const summary = {
  total: rows.length,
  byStatus: rows.reduce((a, r) => ((a[r.status] = (a[r.status] || 0) + 1), a), {}),
  byChapter,
  chapterLevel: chapterLevel.reduce((a, [c, s]) => ((a[s] = (a[s] || 0) + 1), a), {}),
}

fs.writeFileSync(path.join(outDir, 'coverage-summary.json'), JSON.stringify(summary, null, 2), 'utf8')
console.log(JSON.stringify({ total: summary.total, byStatus: summary.byStatus, chapterLevel: summary.chapterLevel }, null, 2))
