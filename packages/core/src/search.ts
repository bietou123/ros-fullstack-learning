import MiniSearch from 'minisearch'
import type { ContentPack, LessonMeta } from './types'

export interface SearchHit {
  id: string
  title: string
  stage: string
  type: string
  score: number
  snippet: string
}

export function buildIndex(pack: ContentPack) {
  const mini = new MiniSearch({
    fields: ['title', 'body', 'tags', 'stageTitle'],
    storeFields: ['title', 'stage', 'type', 'body'],
    tokenize: (text) => tokenizeZh(text),
    searchOptions: { boost: { title: 3, tags: 2 }, fuzzy: 0.2, prefix: true },
  })
  const stageTitle = new Map(pack.stages.map((s) => [s.id, s.title]))
  mini.addAll(
    pack.lessons.map((l) => ({
      id: l.id,
      title: l.title,
      body: stripMarkdown(l.markdown).slice(0, 20000),
      tags: l.tags.join(' '),
      stage: l.stage,
      stageTitle: stageTitle.get(l.stage) ?? l.stage,
      type: l.type,
    })),
  )
  return mini
}

export function search(mini: ReturnType<typeof buildIndex>, query: string, limit = 30): SearchHit[] {
  if (!query.trim()) return []
  return mini.search(query).slice(0, limit).map((r) => ({
    id: r.id as string,
    title: r.title as string,
    stage: r.stage as string,
    type: r.type as string,
    score: r.score,
    snippet: snippet(r.body as string, query),
  }))
}

export function searchLessons(lessons: LessonMeta[], query: string, limit = 30): SearchHit[] {
  const q = query.trim().toLowerCase()
  if (!q) return []
  const hits: SearchHit[] = []
  for (const l of lessons) {
    const idx = l.markdown.toLowerCase().indexOf(q)
    const inTitle = l.title.toLowerCase().includes(q)
    if (!inTitle && idx < 0) continue
    hits.push({
      id: l.id,
      title: l.title,
      stage: l.stage,
      type: l.type,
      score: inTitle ? 100 : 10,
      snippet: idx >= 0 ? l.markdown.slice(Math.max(0, idx - 40), idx + 120).replace(/\s+/g, ' ') : '',
    })
  }
  return hits.sort((a, b) => b.score - a.score).slice(0, limit)
}

function stripMarkdown(md: string) {
  return md
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/[#>*`_\-|]/g, ' ')
    .replace(/\s+/g, ' ')
}

function snippet(text: string, query: string) {
  const i = text.toLowerCase().indexOf(query.toLowerCase())
  if (i < 0) return text.slice(0, 110)
  return text.slice(Math.max(0, i - 40), i + 100)
}

function tokenizeZh(text: string): string[] {
  const out: string[] = []
  const normalized = text.toLowerCase()
  for (const token of normalized.split(/[\s,.;:!?，。；：！？、（）()【】\[\]{}"'`<>/\\|+=*#_-]+/)) {
    if (!token) continue
    if (/[一-鿿]/.test(token)) {
      for (let i = 0; i < token.length - 1; i++) out.push(token.slice(i, i + 2))
      if (token.length === 1) out.push(token)
    } else if (token.length > 1) {
      out.push(token)
    }
  }
  return out
}
