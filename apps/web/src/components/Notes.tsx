import { useEffect, useState } from 'react'
import { addNote, deleteNote, listNotes, type Note } from '@rl/core'

export default function Notes({ lessonId }: { lessonId: string }) {
  const [notes, setNotes] = useState<Note[]>([])
  const [text, setText] = useState('')

  async function reload() {
    setNotes((await listNotes(lessonId)).sort((a, b) => b.createdAt - a.createdAt))
  }

  useEffect(() => {
    reload()
    setText('')
  }, [lessonId])

  async function save() {
    if (!text.trim()) return
    await addNote(lessonId, text.trim())
    setText('')
    reload()
  }

  return (
    <div className="notes">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="记下现场对应关系、你的疑问、要回公司确认的参数…"
        rows={4}
      />
      <div className="row">
        <button className="btn primary" onClick={save} disabled={!text.trim()}>保存笔记</button>
        <span className="muted">笔记只存本机，可随学习数据一起导出。</span>
      </div>
      {notes.map((n) => (
        <div key={n.id} className="note-item">
          <p>{n.text}</p>
          <div className="note-meta">
            <span>{new Date(n.createdAt).toLocaleString('zh-CN')}</span>
            <button className="link" onClick={async () => { await deleteNote(n.id); reload() }}>删除</button>
          </div>
        </div>
      ))}
    </div>
  )
}
