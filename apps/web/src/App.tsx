import { useEffect, useMemo, useState } from 'react'
import { useApp } from './store'
import Home from './pages/Home'
import LessonPage from './pages/LessonPage'
import SearchPage from './pages/SearchPage'
import ProgressPage from './pages/ProgressPage'
import SettingsPage from './pages/SettingsPage'
import GlossaryPage from './pages/GlossaryPage'

function parseHash(hash: string) {
  const clean = hash.replace(/^#\/?/, '')
  const [path, query] = clean.split('?')
  const parts = path.split('/').filter(Boolean)
  return { parts, query: new URLSearchParams(query ?? '') }
}

export default function App() {
  const { pack, loading, error, load, progress, activePackId } = useApp()
  const [route, setRoute] = useState(() => parseHash(location.hash))
  const [navOpen, setNavOpen] = useState(false)

  useEffect(() => {
    load()
    const onHash = () => {
      setRoute(parseHash(location.hash))
      setNavOpen(false)
      document.querySelector('.main')?.scrollTo({ top: 0 })
    }
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const lessons = pack?.lessons ?? []
  const doneCount = useMemo(() => lessons.filter((l) => progress[l.id]?.status === 'done').length, [lessons, progress])

  if (loading) {
    return <div className="boot">正在加载课程内容…</div>
  }
  if (error) {
    return (
      <div className="boot error">
        <h2>内容包加载失败</h2>
        <p>{error}</p>
        <p className="muted">请确认已执行 `pnpm build:content`。</p>
      </div>
    )
  }
  if (!pack) return <div className="boot">内容包为空</div>

  const [first, second] = route.parts
  let page = <Home />
  if (first === 'lesson' && second) page = <LessonPage lessonId={second} />
  else if (first === 'search') page = <SearchPage initial={route.query.get('q') ?? ''} />
  else if (first === 'progress') page = <ProgressPage />
  else if (first === 'settings') page = <SettingsPage />
  else if (first === 'glossary') page = <GlossaryPage />
  else if (first === 'stage' && second) page = <Home stageId={second} />

  return (
    <div className="app">
      <header className="topbar">
        <button className="icon-btn nav-toggle" onClick={() => setNavOpen((v) => !v)} aria-label="菜单">☰</button>
        <a className="brand" href="#/">
          工业机器人全栈
          <span className="brand-sub">ROS1 · ROS2 · 交付实战</span>
        </a>
        <form
          className="searchbox"
          onSubmit={(e) => {
            e.preventDefault()
            const q = new FormData(e.currentTarget).get('q') as string
            location.hash = `/search?q=${encodeURIComponent(q)}`
          }}
        >
          <input name="q" placeholder="搜索课程、命令、术语…" defaultValue={route.query.get('q') ?? ''} />
        </form>
        <nav className="topnav">
          <a href="#/progress">进度 {doneCount}/{lessons.length}</a>
          <a href="#/glossary">术语</a>
          <a href="#/settings">设置</a>
        </nav>
      </header>

      <aside className={navOpen ? 'sidebar open' : 'sidebar'}>
        <div className="side-label">课程目录</div>
        {pack.stages.map((s) => {
          const items = s.lessons.map((id) => lessons.find((l) => l.id === id)!).filter(Boolean)
          const sdone = items.filter((l) => progress[l.id]?.status === 'done').length
          return (
            <div key={s.id} className="stage-block">
              <a className="stage-title" href={`#/stage/${s.id}`}>
                <span>{s.title}</span>
                <em>{sdone}/{items.length}</em>
              </a>
              <div className="stage-lessons">
                {items.map((l) => (
                  <a key={l.id} className={`lesson-link ${l.id === (first === 'lesson' ? second : '') ? 'active' : ''}`} href={`#/lesson/${l.id}`}>
                    <i className={`dot ${progress[l.id]?.status ?? 'new'}`} />
                    <span className="lid">{l.id}</span>
                    <span className="lt">{l.title}</span>
                  </a>
                ))}
              </div>
            </div>
          )
        })}
        <div className="side-meta">
          内容包 {pack.manifest.version} · {pack.manifest.id}
          {activePackId !== 'rl.public.core' && <span className="private-tag">私有</span>}
        </div>
      </aside>

      <main className="main">{page}</main>
    </div>
  )
}
