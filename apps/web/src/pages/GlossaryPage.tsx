import { useState } from 'react'
import { useApp } from '../store'

export default function GlossaryPage() {
  const { pack } = useApp()
  const [q, setQ] = useState('')
  const terms = (pack?.glossary ?? []).filter((g) => !q || g.term.includes(q) || (g.en ?? '').toLowerCase().includes(q.toLowerCase()) || g.def.includes(q))
  return (
    <div className="page">
      <h1>术语表</h1>
      <form className="big-search" onSubmit={(e) => e.preventDefault()}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="中文 / English / 缩写" />
      </form>
      {terms.length === 0 && <div className="card"><p className="muted">术语表尚未导入。可在内容包 glossary.json 中维护。</p></div>}
      <div className="glossary">
        {terms.map((g) => (
          <div key={g.term} className="term card">
            <div className="term-head"><b>{g.term}</b>{g.en && <span className="en">{g.en}</span>}</div>
            <p>{g.def}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
