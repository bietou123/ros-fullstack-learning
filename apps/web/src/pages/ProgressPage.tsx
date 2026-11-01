import { useEffect, useMemo, useState } from 'react'
import { dueReviews, listBookmarks, listNotes, listQuizResults, type QuizResult } from '@rl/core'
import { useApp } from '../store'

const DIMS: { name: string; ids: string[] }[] = [
  { name: '工具链', ids: ['S0'] },
  { name: '电气', ids: ['S4-01', 'S4-02', 'S4-04'] },
  { name: '下位机', ids: ['S4-05', 'S4-06', 'S4-07', 'S9-02'] },
  { name: 'ROS 基础', ids: ['S1'] },
  { name: 'ROS 进阶', ids: ['S2'] },
  { name: '建模', ids: ['S3'] },
  { name: '感知', ids: ['S5-01', 'S5-02', 'S5-03'] },
  { name: '标定', ids: ['S5-04', 'S5-05', 'S5-06', 'S5-07'] },
  { name: '控制', ids: ['S6-01', 'S6-02', 'S6-03'] },
  { name: '安全', ids: ['S6-04', 'S6-05', 'S6-06', 'S6-07'] },
  { name: '导航', ids: ['S7'] },
  { name: '部署', ids: ['S8'] },
  { name: '交付', ids: ['S9', 'S10'] },
]

export default function ProgressPage() {
  const { pack, progress } = useApp()
  const [quiz, setQuiz] = useState<QuizResult[]>([])
  const [notes, setNotes] = useState(0)
  const [marks, setMarks] = useState(0)

  useEffect(() => {
    listQuizResults().then(setQuiz)
    listNotes().then((n) => setNotes(n.length))
    listBookmarks().then((b) => setMarks(b.length))
  }, [pack])

  const dimValues = useMemo(() => {
    if (!pack) return []
    return DIMS.map((d) => {
      const ids = pack.lessons.filter((l) => d.ids.some((p) => l.id.startsWith(p))).map((l) => l.id)
      const done = ids.filter((id) => progress[id]?.status === 'done').length
      const avg = ids.length ? ids.reduce((a, id) => a + (progress[id]?.percent ?? 0), 0) / ids.length : 0
      return { ...d, value: ids.length ? Math.round((done / ids.length) * 70 + (avg / 100) * 30) : 0 }
    })
  }, [pack, progress])

  if (!pack) return null
  const lessons = pack.lessons
  const done = lessons.filter((l) => progress[l.id]?.status === 'done').length
  const overall = Math.round((done / lessons.length) * 100)
  const due = dueReviews(quiz)
  const totalCorrect = quiz.reduce((a, r) => a + r.correct, 0)
  const totalQuestions = quiz.reduce((a, r) => a + r.total, 0)

  return (
    <div className="page">
      <h1>能力进度</h1>
      <div className="kpi-grid">
        <div className="kpi"><b>{overall}%</b><span>课程完成率</span></div>
        <div className="kpi"><b>{done}/{lessons.length}</b><span>已完成课程</span></div>
        <div className="kpi"><b>{totalQuestions ? Math.round((totalCorrect / totalQuestions) * 100) : 0}%</b><span>测验正确率</span></div>
        <div className="kpi"><b>{due.length}</b><span>待复习</span></div>
        <div className="kpi"><b>{notes}</b><span>笔记</span></div>
        <div className="kpi"><b>{marks}</b><span>收藏</span></div>
      </div>

      <section className="card">
        <h3>能力雷达</h3>
        <Radar values={dimValues} />
      </section>

      <section className="card">
        <h3>阶段进度</h3>
        {pack.stages.map((s) => {
          const items = s.lessons.map((id) => lessons.find((l) => l.id === id)!).filter(Boolean)
          const d = items.filter((l) => progress[l.id]?.status === 'done').length
          return (
            <div key={s.id} className="stage-row">
              <span className="sc-id">{s.id.toUpperCase()}</span>
              <span className="stage-name">{s.title}</span>
              <div className="progressbar"><i style={{ width: `${(d / items.length) * 100}%` }} /></div>
              <span className="muted">{d}/{items.length}</span>
            </div>
          )
        })}
      </section>

      {due.length > 0 && (
        <section className="card">
          <h3>待复习</h3>
          <div className="chips">{due.slice(0, 20).map((r) => <a key={r.id} className="chip" href={`#/lesson/${r.lessonId}`}>{r.lessonId}</a>)}</div>
        </section>
      )}
    </div>
  )
}

function Radar({ values }: { values: { name: string; value: number }[] }) {
  const size = 340
  const cx = size / 2
  const cy = size / 2
  const r = 120
  const n = values.length
  const point = (i: number, v: number) => {
    const a = (Math.PI * 2 * i) / n - Math.PI / 2
    const rr = (v / 100) * r
    return [cx + Math.cos(a) * rr, cy + Math.sin(a) * rr]
  }
  const poly = values.map((v, i) => point(i, Math.max(4, v.value)).join(',')).join(' ')
  return (
    <div className="radar">
      <svg viewBox={`0 0 ${size} ${size}`}>
        {[0.25, 0.5, 0.75, 1].map((k) => (
          <polygon
            key={k}
            points={values.map((_, i) => point(i, k * 100).join(',')).join(' ')}
            className="grid"
          />
        ))}
        {values.map((_, i) => {
          const [x, y] = point(i, 100)
          return <line key={i} x1={cx} y1={cy} x2={x} y2={y} className="grid" />
        })}
        <polygon points={poly} className="area" />
        {values.map((v, i) => {
          const [x, y] = point(i, 118)
          return <text key={v.name} x={x} y={y} textAnchor="middle" className="axis-label">{v.name}</text>
        })}
      </svg>
    </div>
  )
}
