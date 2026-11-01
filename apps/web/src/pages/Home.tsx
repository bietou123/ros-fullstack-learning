import { useEffect, useState } from 'react'
import { dueReviews, listQuizResults, packStats, type QuizResult } from '@rl/core'
import { useApp } from '../store'

export default function Home({ stageId }: { stageId?: string }) {
  const { pack, progress } = useApp()
  const [reviews, setReviews] = useState<QuizResult[]>([])

  useEffect(() => {
    listQuizResults().then((rows) => setReviews(dueReviews(rows)))
  }, [pack])

  if (!pack) return null
  const stats = packStats(pack)
  const lessons = pack.lessons

  if (stageId) {
    const stage = pack.stages.find((s) => s.id === stageId)
    if (!stage) return <div className="empty">阶段不存在</div>
    const items = stage.lessons.map((id) => lessons.find((l) => l.id === id)!).filter(Boolean)
    const done = items.filter((l) => progress[l.id]?.status === 'done').length
    return (
      <div className="page">
        <div className="crumbs"><a href="#/">首页</a> / {stage.title}</div>
        <h1>{stage.title}</h1>
        <p className="lead">{stage.desc}</p>
        <div className="progressbar big"><i style={{ width: `${(done / items.length) * 100}%` }} /></div>
        <p className="muted">完成 {done} / {items.length} 节</p>
        <div className="lesson-cards">
          {items.map((l) => {
            const p = progress[l.id]
            return (
              <a key={l.id} className="lesson-card" href={`#/lesson/${l.id}`}>
                <div className="lc-top">
                  <span className={`pill ${l.type}`}>{labelOf(l.type)}</span>
                  <span className="muted">{l.durationMin} 分钟</span>
                </div>
                <h3>{l.title}</h3>
                <p>{l.output}</p>
                <div className="progressbar"><i style={{ width: `${p?.percent ?? 0}%` }} /></div>
              </a>
            )
          })}
        </div>
      </div>
    )
  }

  const last = [...lessons]
    .filter((l) => progress[l.id] && progress[l.id].status !== 'done')
    .sort((a, b) => (progress[b.id]?.lastAt ?? 0) - (progress[a.id]?.lastAt ?? 0))[0]
    ?? lessons.find((l) => !progress[l.id])

  const doneCount = lessons.filter((l) => progress[l.id]?.status === 'done').length

  return (
    <div className="page">
      <section className="hero">
        <div>
          <div className="kicker">全栈 · 离线 · 三端同源</div>
          <h1>从座舱指令，<br />到电磁阀动作。</h1>
          <p className="lead">
            76 节课覆盖机械、电气、下位机、ROS1/ROS2、建模、感知标定、控制安全、导航、部署与交付。
            每节课都有可复制命令与自动检查；没有硬件也能完成大部分实验。
          </p>
          <div className="hero-actions">
            {last && <a className="btn primary" href={`#/lesson/${last.id}`}>继续学习 · {last.id}</a>}
            <a className="btn" href="#/progress">查看能力进度</a>
          </div>
        </div>
        <div className="stat-grid">
          <div><b>{stats.lessons}</b><span>节课</span></div>
          <div><b>{stats.stages}</b><span>阶段</span></div>
          <div><b>{Math.round(stats.minutes / 60)}</b><span>小时主线</span></div>
          <div><b>{doneCount}</b><span>已完成</span></div>
        </div>
      </section>

      {reviews.length > 0 && (
        <section className="card highlight">
          <h3>今天该复习 {reviews.length} 节</h3>
          <p className="muted">间隔重复已到期，重做测验可以巩固记忆。</p>
          <div className="chips">
            {reviews.slice(0, 8).map((r) => (
              <a key={r.id} className="chip" href={`#/lesson/${r.lessonId}`}>{r.lessonId}</a>
            ))}
          </div>
        </section>
      )}

      <h2 className="section-title">阶段路线</h2>
      <div className="stage-grid">
        {pack.stages.map((s) => {
          const items = s.lessons.map((id) => lessons.find((l) => l.id === id)!).filter(Boolean)
          const done = items.filter((l) => progress[l.id]?.status === 'done').length
          const pct = items.length ? (done / items.length) * 100 : 0
          return (
            <a key={s.id} className="stage-card" href={`#/stage/${s.id}`}>
              <div className="sc-head">
                <span className="sc-id">{s.id.toUpperCase()}</span>
                <span className="muted">{items.length} 节 · {items.reduce((a, l) => a + l.durationMin, 0)} 分钟</span>
              </div>
              <h3>{s.title}</h3>
              <p>{s.desc}</p>
              <div className="progressbar"><i style={{ width: `${pct}%` }} /></div>
            </a>
          )
        })}
      </div>

      <section className="card">
        <h3>诚实边界</h3>
        <p className="muted">
          仿真能覆盖约 90% 的软件链路；整车安装、线束预埋、真机验收必须现场完成，课程里标为 <b>field</b> 的条目不会假装能替代。
          标为 <b>⚠ 冲突</b> 的资料矛盾会原样保留，并附「现场确认项」编号。
        </p>
      </section>
    </div>
  )
}

function labelOf(t: string) {
  return t === 'teach' ? '可实操' : t === 'read' ? '读懂' : '现场'
}
