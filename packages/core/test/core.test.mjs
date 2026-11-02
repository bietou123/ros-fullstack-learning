import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { gradeQuiz, nextReview, makeQuizResult, dueReviews } from '../src/quiz.ts'
import { computePackHash, verifyPack, packStats } from '../src/pack.ts'
import { privatePackRecord } from '../src/store.ts'
import { buildIndex, search, searchLessons } from '../src/search.ts'
import { readOnlyAdapter, setPlatformAdapter, getPlatform, detectBackend, runExperiment } from '../src/platform.ts'

const DAY = 86400000

const quiz = [
  { q: '安全回路应如何设计？', options: ['软件互锁', '独立硬线', '仅靠 HMI'], answer: 1 },
  { q: '急停按钮的复位方式？', options: ['自动复位', '手动旋转复位', '重启软件'], answer: 1, explain: '急停必须是手动复位' },
  { q: '远端急停的延迟上限越小越好？', options: ['是', '不是'], answer: 0 },
]

test('gradeQuiz：计分、未作答与解析透传', () => {
  const out = gradeQuiz(quiz, [1, 1, 0])
  assert.equal(out.correct, 3)
  assert.equal(out.total, 3)
  assert.deepEqual(out.details.map((d) => d.ok), [true, true, true])
  assert.equal(out.details[1].explain, '急停必须是手动复位')

  const partial = gradeQuiz(quiz, [1, 0, 0])
  assert.equal(partial.correct, 2)
  assert.deepEqual(partial.details.map((d) => d.ok), [true, false, true])

  const unpaid = gradeQuiz(quiz, [1])
  assert.equal(unpaid.correct, 1)
  assert.equal(unpaid.details[1].chosen, -1)
  assert.equal(unpaid.details[1].ok, false)
})

test('nextReview：满分 15 天，60% 以上 3 天，不足 60% 1 天', () => {
  const now = 1_700_000_000_000
  const full = nextReview({ correct: 3, total: 3 }, now)
  assert.equal(full.ease, 2.2)
  assert.equal(full.intervalDays, 15)
  assert.equal(full.nextReviewAt, now + 15 * DAY)

  const pass = nextReview({ correct: 2, total: 3 }, now)
  assert.equal(pass.intervalDays, 3)
  assert.ok(Math.abs(pass.ease - 1.9) < 1e-9)

  const fail = nextReview({ correct: 1, total: 3 }, now)
  assert.equal(fail.intervalDays, 1)

  assert.equal(nextReview({ correct: 0, total: 0 }, now).intervalDays, 1)
})

test('nextReview：ease 被夹在 1.3–2.8', () => {
  const low = nextReview({ correct: 0, total: 3, ease: 1.35 })
  assert.equal(low.ease, 1.3)
  const high = nextReview({ correct: 3, total: 3, ease: 2.75 })
  assert.equal(high.ease, 2.8)
})

test('makeQuizResult 与 dueReviews：只取每课最新一次并按到期时间排序', () => {
  const now = 1_700_000_000_000
  const out = gradeQuiz(quiz, [1, 1, 0])
  const r = makeQuizResult('s1-01', [1, 1, 0], out)
  assert.equal(r.lessonId, 's1-01')
  assert.equal(r.correct, 3)
  assert.equal(r.total, 3)
  assert.deepEqual(r.answers, [1, 1, 0])
  assert.ok(r.id.startsWith('s1-01-'))
  assert.equal(r.intervalDays, 15)

  const results = [
    { lessonId: 'a', at: 1, nextReviewAt: now - DAY },
    { lessonId: 'a', at: 2, nextReviewAt: now + DAY },
    { lessonId: 'b', at: 3, nextReviewAt: now - 2 * DAY },
    { lessonId: 'c', at: 4, nextReviewAt: now - 3 * DAY },
  ]
  const due = dueReviews(results, now)
  assert.deepEqual(due.map((x) => x.lessonId), ['c', 'b'])
})

function makePack() {
  const pack = {
    manifest: {
      id: 'rl.test',
      version: '0.0.1',
      minAppVersion: '0.1.0',
      visibility: 'public',
      builtAt: '2026-11-02T00:00:00Z',
      hash: '',
      lessonCount: 2,
      stageCount: 1,
    },
    stages: [{ id: 's0', title: '入门与地图', desc: '测试阶段', lessons: ['s0-01', 's0-02'] }],
    lessons: [
      {
        id: 's0-01',
        stage: 's0',
        title: '机械臂坐标系',
        durationMin: 25,
        type: 'teach',
        output: '能画 TF 链',
        tags: ['TF', '坐标'],
        sources: [],
        experiment: null,
        quiz: quiz.slice(0, 2),
        markdown: '# 机械臂坐标系\n机械臂用 TF 描述连杆关系，`ros2 run tf2_tools view_frames` 可导出。',
      },
      {
        id: 's0-02',
        stage: 's0',
        title: '现场安全',
        durationMin: 30,
        type: 'field',
        output: '能执行开机 SOP',
        tags: ['安全'],
        sources: [],
        experiment: null,
        quiz: quiz.slice(2),
        markdown: '急停必须独立硬线，不依赖软件互锁。',
      },
    ],
    glossary: [{ term: 'TF', en: 'transform', def: '坐标变换树' }],
  }
  pack.manifest.hash = computePackHash(pack)
  return pack
}

test('computePackHash：忽略构建元数据，课程改动会失效', () => {
  const pack = makePack()
  const base = computePackHash(pack)
  assert.match(base, /^[0-9a-f]{64}$/)

  const bumped = structuredClone(pack)
  bumped.manifest.builtAt = '2099-01-01T00:00:00Z'
  bumped.manifest.lessonCount = 999
  bumped.manifest.hash = 'deadbeef'
  assert.equal(computePackHash(bumped), base)

  const tampered = structuredClone(pack)
  tampered.lessons[0].markdown += ' 改动'
  assert.notEqual(computePackHash(tampered), base)

  assert.deepEqual(verifyPack(pack), { ok: true, expected: base, actual: base })
  assert.equal(verifyPack(tampered).ok, false)
})

test('packStats：累计课时、题目与字数', () => {
  const stats = packStats(makePack())
  assert.equal(stats.lessons, 2)
  assert.equal(stats.stages, 1)
  assert.equal(stats.minutes, 55)
  assert.equal(stats.quizzes, 3)
  assert.equal(
    stats.words,
    makePack().lessons.reduce((a, l) => a + l.markdown.length, 0),
  )
})

test('buildIndex/search：中文二元分词可命中正文与标题', () => {
  const mini = buildIndex(makePack())
  const hits = search(mini, '机械臂')
  assert.ok(hits.length >= 1)
  assert.equal(hits[0].id, 's0-01')
  assert.equal(hits[0].title, '机械臂坐标系')
  assert.equal(hits[0].stage, 's0')
  assert.equal(hits[0].type, 'teach')
  assert.ok(hits[0].snippet.length > 0)

  const tagHits = search(mini, 'TF')
  assert.equal(tagHits[0].id, 's0-01')

  assert.deepEqual(search(mini, '   '), [])
})

test('searchLessons：标题命中权重高于正文，大小写不敏感', () => {
  const pack = makePack()
  const byTitle = searchLessons(pack.lessons, '机械臂')
  assert.equal(byTitle[0].id, 's0-01')
  assert.equal(byTitle[0].score, 100)

  const byBody = searchLessons(pack.lessons, 'tf')
  assert.equal(byBody[0].id, 's0-01')
  assert.equal(byBody[0].score, 10)

  assert.deepEqual(searchLessons(pack.lessons, ''), [])
})

test('readOnlyAdapter：明确返回 no-backend，不伪造结果', async () => {
  assert.equal(await readOnlyAdapter.detectBackend(), 'read-only')
  const spec = {
    id: 'x',
    ros: 'none',
    commands: ['echo hi'],
    checks: ['out==hi'],
    timeoutSec: 5,
    headless: true,
  }
  const r = await readOnlyAdapter.runExperiment(spec)
  assert.equal(r.ok, false)
  assert.equal(r.reason, 'no-backend')
  assert.equal(r.backend, 'read-only')
  assert.equal(r.steps.length, 1)
  assert.equal(r.steps[0].code, -1)
  assert.equal(r.checks[0].ok, false)
})

test('平台适配器：可切换，异常时降级为 failed 而非抛错', async () => {
  const original = getPlatform()
  setPlatformAdapter({
    name: 'desktop',
    async detectBackend() {
      throw new Error('boom')
    },
    async runExperiment() {
      throw new Error('boom')
    },
  })
  try {
    assert.equal(await detectBackend(), 'read-only')
    const r = await runExperiment({ id: 'x', ros: 'none', commands: [], checks: [], timeoutSec: 1, headless: true })
    assert.equal(r.ok, false)
    assert.equal(r.reason, 'failed')
  } finally {
    setPlatformAdapter(original)
  }
})

test('privatePackRecord：私有包存储键取自 manifest.id', () => {
  const pack = makePack()
  const row = privatePackRecord(pack)
  assert.equal(row.id, 'rl.test')
  assert.equal(row.manifest.id, 'rl.test')
  assert.deepEqual(row.lessons, pack.lessons)

  assert.throws(() => privatePackRecord({ manifest: {} }), /manifest\.id/)
  assert.throws(() => privatePackRecord(null), /manifest\.id/)
})

test('构建脚本产出的内容包必须通过核心库校验（防哈希算法漂移）', (t) => {
  const file = path.join(fileURLToPath(new URL('.', import.meta.url)), '../../../apps/web/public/content/pack.json')
  if (!fs.existsSync(file)) {
    t.skip('尚未执行 pnpm build:content')
    return
  }
  const pack = JSON.parse(fs.readFileSync(file, 'utf8'))
  const v = verifyPack(pack)
  assert.equal(v.ok, true, `manifest.hash=${v.expected} 核心库=${v.actual}`)
})
