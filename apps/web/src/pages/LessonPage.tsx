import { useEffect, useMemo, useRef, useState } from 'react'
import { getBookmark, setProgress, toggleBookmark } from '@rl/core'
import { useApp } from '../store'
import Markdown from '../components/Markdown'
import Quiz from '../components/Quiz'
import Notes from '../components/Notes'
import Experiment from '../components/Experiment'

type Tab = 'text' | 'quiz' | 'notes' | 'exp'

export default function LessonPage({ lessonId }: { lessonId: string }) {
  const { pack, progress, refresh } = useApp()
  const [tab, setTab] = useState<Tab>('text')
  const [bookmarked, setBookmarked] = useState(false)
  const [pct, setPct] = useState(0)
  const mainRef = useRef<Element | null>(null)
  const lastSave = useRef(0)
  const visitedAt = useRef(Date.now())

  const lesson = pack?.lessons.find((l) => l.id === lessonId)
  const idx = pack?.lessons.findIndex((l) => l.id === lessonId) ?? -1
  const prev = idx > 0 ? pack!.lessons[idx - 1] : null
  const next = idx >= 0 && idx < (pack?.lessons.length ?? 0) - 1 ? pack!.lessons[idx + 1] : null

  useEffect(() => {
    setTab('text')
    setPct(progress[lessonId]?.percent ?? 0)
    getBookmark(lessonId).then((b) => setBookmarked(!!b))
    visitedAt.current = Date.now()
  }, [lessonId])

  useEffect(() => {
    const el = document.querySelector('.main')
    if (!el) return
    mainRef.current = el
    el.scrollTo({ top: 0 })
    const onScroll = () => {
      const denom = el.scrollHeight - el.clientHeight
      const p = denom <= 0 ? 100 : Math.min(100, Math.round((el.scrollTop / denom) * 100))
      setPct((old) => Math.max(old, p))
      const now = Date.now()
      if (now - lastSave.current > 4000 && p > (progress[lessonId]?.percent ?? 0)) {
        lastSave.current = now
        setProgress(lessonId, p, Math.round((now - visitedAt.current) / 1000)).then(refresh)
      }
    }
    el.addEventListener('scroll', onScroll, { passive: true })
    onScroll()
    return () => el.removeEventListener('scroll', onScroll)
  }, [lessonId, progress[lessonId]?.percent])

  const totalQuiz = useMemo(() => lesson?.quiz.length ?? 0, [lesson])

  if (!lesson) return <div className="page"><div className="empty">课程不存在：{lessonId}</div></div>

  return (
    <div className="page lesson-page">
      <div className="crumbs">
        <a href="#/">首页</a> / <a href={`#/stage/${lesson.stage}`}>{lesson.stage.toUpperCase()}</a> / {lesson.id}
      </div>

      <header className="lesson-head">
        <div>
          <div className="row gap">
            <span className={`pill ${lesson.type}`}>{lesson.type === 'teach' ? '可实操' : lesson.type === 'read' ? '读懂' : '现场'}</span>
            <span className="muted">{lesson.durationMin} 分钟 · 产出：{lesson.output}</span>
          </div>
          <h1>{lesson.title}</h1>
          <div className="tags">
            {lesson.tags.map((t) => <span key={t} className="tag">{t}</span>)}
            {lesson.sources.map((s) => <span key={s} className="tag src">来源：{s}</span>)}
          </div>
        </div>
        <div className="lesson-actions">
          <button className={`btn ${bookmarked ? 'active' : ''}`} onClick={async () => setBookmarked(await toggleBookmark(lessonId, lesson.title))}>
            {bookmarked ? '★ 已收藏' : '☆ 收藏'}
          </button>
          <button
            className="btn primary"
            onClick={async () => {
              await setProgress(lessonId, 100, 0)
              await refresh()
              setPct(100)
            }}
          >
            标记完成
          </button>
        </div>
      </header>

      <div className="progressbar reading"><i style={{ width: `${pct}%` }} /></div>

      <div className="tabs">
        <button className={tab === 'text' ? 'active' : ''} onClick={() => setTab('text')}>正文</button>
        <button className={tab === 'quiz' ? 'active' : ''} onClick={() => setTab('quiz')}>测验 {totalQuiz > 0 && <em>{totalQuiz}</em>}</button>
        <button className={tab === 'exp' ? 'active' : ''} onClick={() => setTab('exp')}>实验</button>
        <button className={tab === 'notes' ? 'active' : ''} onClick={() => setTab('notes')}>笔记</button>
      </div>

      {tab === 'text' && <Markdown>{lesson.markdown}</Markdown>}
      {tab === 'quiz' && <Quiz lessonId={lessonId} quiz={lesson.quiz} />}
      {tab === 'exp' && (lesson.experiment ? <Experiment spec={lesson.experiment} /> : <div className="card"><p className="muted">本节没有可运行实验，完成复盘题即可。</p></div>)}
      {tab === 'notes' && <Notes lessonId={lessonId} />}

      <nav className="lesson-nav">
        {prev ? <a className="btn" href={`#/lesson/${prev.id}`}>← {prev.id} {prev.title}</a> : <span />}
        {next ? <a className="btn" href={`#/lesson/${next.id}`}>{next.id} {next.title} →</a> : <a className="btn" href="#/progress">去看能力进度 →</a>}
      </nav>
    </div>
  )
}
