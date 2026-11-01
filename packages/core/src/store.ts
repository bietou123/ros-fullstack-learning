import { openDB, type IDBPDatabase } from 'idb'
import type { Bookmark, Note, Progress, QuizResult } from './types'

const DB_NAME = 'rl-learning'
const DB_VERSION = 1

let dbp: Promise<IDBPDatabase> | null = null

function db() {
  if (!dbp) {
    dbp = openDB(DB_NAME, DB_VERSION, {
      upgrade(d) {
        d.createObjectStore('progress', { keyPath: 'lessonId' })
        const notes = d.createObjectStore('notes', { keyPath: 'id' })
        notes.createIndex('lessonId', 'lessonId')
        const quiz = d.createObjectStore('quiz', { keyPath: 'id' })
        quiz.createIndex('lessonId', 'lessonId')
        d.createObjectStore('bookmarks', { keyPath: 'lessonId' })
        d.createObjectStore('settings', { keyPath: 'key' })
        d.createObjectStore('packs', { keyPath: 'id' })
      },
    })
  }
  return dbp
}

export async function getProgress(lessonId: string): Promise<Progress | undefined> {
  return (await db()).get('progress', lessonId)
}

export async function getAllProgress(): Promise<Progress[]> {
  return (await db()).getAll('progress')
}

export async function setProgress(lessonId: string, percent: number, seconds: number): Promise<Progress> {
  const d = await db()
  const prev = await d.get('progress', lessonId)
  const status = percent >= 100 ? 'done' : percent > 0 ? 'reading' : 'new'
  const rec: Progress = {
    lessonId,
    status,
    percent: Math.max(prev?.percent ?? 0, Math.min(100, Math.round(percent))),
    lastAt: Date.now(),
    seconds: (prev?.seconds ?? 0) + seconds,
  }
  await d.put('progress', rec)
  return rec
}

export async function addNote(lessonId: string, text: string): Promise<Note> {
  const note: Note = {
    id: `${lessonId}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    lessonId,
    text,
    createdAt: Date.now(),
    updatedAt: Date.now(),
  }
  await (await db()).put('notes', note)
  return note
}

export async function updateNote(note: Note): Promise<void> {
  note.updatedAt = Date.now()
  await (await db()).put('notes', note)
}

export async function deleteNote(id: string): Promise<void> {
  await (await db()).delete('notes', id)
}

export async function listNotes(lessonId?: string): Promise<Note[]> {
  const d = await db()
  return lessonId ? d.getAllFromIndex('notes', 'lessonId', lessonId) : d.getAll('notes')
}

export async function addQuizResult(r: QuizResult): Promise<void> {
  await (await db()).put('quiz', r)
}

export async function listQuizResults(lessonId?: string): Promise<QuizResult[]> {
  const d = await db()
  return lessonId ? d.getAllFromIndex('quiz', 'lessonId', lessonId) : d.getAll('quiz')
}

export async function getBookmark(lessonId: string): Promise<Bookmark | undefined> {
  return (await db()).get('bookmarks', lessonId)
}

export async function toggleBookmark(lessonId: string, label = ''): Promise<boolean> {
  const d = await db()
  const cur = await d.get('bookmarks', lessonId)
  if (cur) {
    await d.delete('bookmarks', lessonId)
    return false
  }
  await d.put('bookmarks', { lessonId, at: Date.now(), label })
  return true
}

export async function listBookmarks(): Promise<Bookmark[]> {
  return (await db()).getAll('bookmarks')
}

export async function getSetting<T = unknown>(key: string, fallback?: T): Promise<T | undefined> {
  const row = await (await db()).get('settings', key)
  return row ? (row.value as T) : fallback
}

export async function setSetting(key: string, value: unknown): Promise<void> {
  await (await db()).put('settings', { key, value })
}

export async function savePrivatePack(pack: unknown): Promise<void> {
  await (await db()).put('packs', pack as never)
}

export async function listPrivatePacks(): Promise<unknown[]> {
  return (await db()).getAll('packs')
}

export async function deletePrivatePack(id: string): Promise<void> {
  await (await db()).delete('packs', id)
}

export async function exportAll(): Promise<string> {
  const d = await db()
  const payload = {
    schemaVersion: 1,
    exportedAt: new Date().toISOString(),
    app: 'ros-fullstack-learning',
    progress: await d.getAll('progress'),
    notes: await d.getAll('notes'),
    quiz: await d.getAll('quiz'),
    bookmarks: await d.getAll('bookmarks'),
    settings: await d.getAll('settings'),
  }
  return JSON.stringify(payload, null, 2)
}

export async function importAll(json: string, mode: 'merge' | 'replace' = 'merge'): Promise<{ imported: number }> {
  const data = JSON.parse(json)
  if (data.schemaVersion !== 1) throw new Error('不支持的数据格式版本')
  const d = await db()
  if (mode === 'replace') {
    for (const s of ['progress', 'notes', 'quiz', 'bookmarks', 'settings'] as const) {
      await d.clear(s)
    }
  }
  let n = 0
  const KEY_FIELD = { progress: 'lessonId', notes: 'id', quiz: 'id', bookmarks: 'lessonId', settings: 'key' } as const
  for (const k of ['progress', 'notes', 'quiz', 'bookmarks', 'settings'] as const) {
    for (const row of data[k] ?? []) {
      const rec = row as Record<string, unknown>
      const key = rec[KEY_FIELD[k]]
      if (typeof key !== 'string') continue
      const existing = await d.get(k, key)
      if (existing && mode === 'merge') {
        const a = existing as { updatedAt?: number; lastAt?: number; at?: number }
        const b = row as { updatedAt?: number; lastAt?: number; at?: number }
        const older = (b.updatedAt ?? b.lastAt ?? b.at ?? 0) < (a.updatedAt ?? a.lastAt ?? a.at ?? 0)
        if (older) continue
      }
      await d.put(k, row as never)
      n++
    }
  }
  return { imported: n }
}

export async function resetAll(): Promise<void> {
  const d = await db()
  for (const s of ['progress', 'notes', 'quiz', 'bookmarks', 'settings'] as const) await d.clear(s)
}
