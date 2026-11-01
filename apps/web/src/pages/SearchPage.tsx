import { useEffect, useMemo, useState } from 'react'
import { buildIndex, search } from '@rl/core'
import { useApp } from '../store'

export default function SearchPage({ initial }: { initial: string }) {
  const { pack, progress } = useApp()
  const [q, setQ] = useState(initial)
  const mini = useMemo(() => (pack ? buildIndex(pack) : null), [pack])
  const [hits, setHits] = useState<ReturnType<typeof search>>([])

  useEffect(() => {
    if (!mini) return
    const t = setTimeout(() => setHits(search(mini, q, 40)), 120)
    return () => clearTimeout(t)
  }, [q, mini])

  return (
    <div className="page">
      <h1>全文搜索</h1>
      <form className="big-search" onSubmit={(e) => e.preventDefault()}>
        <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="命令、协议、标定、术语…" />
      </form>
      <p className="muted">{q ? `${hits.length} 条结果` : '输入关键词开始搜索，支持中文二字词与模糊匹配。'}</p>
      <div className="results">
        {hits.map((h) => {
          const l = pack?.lessons.find((x) => x.id === h.id)
          return (
            <a key={h.id} className="result" href={`#/lesson/${h.id}`}>
              <div className="r-head">
                <span className="lid">{h.id}</span>
                <span className="r-title">{h.title}</span>
                {progress[h.id]?.status === 'done' && <span className="pill done">已完成</span>}
              </div>
              <p className="snippet">{highlight(h.snippet, q)}</p>
              <div className="r-meta">{l?.stage.toUpperCase()} · {l?.type}</div>
            </a>
          )
        })}
      </div>
    </div>
  )
}

function highlight(text: string, q: string) {
  const i = text.toLowerCase().indexOf(q.toLowerCase())
  if (i < 0 || !q) return text
  return <>{text.slice(0, i)}<mark>{text.slice(i, i + q.length)}</mark>{text.slice(i + q.length)}</>
}
