import { sha256 } from 'js-sha256'
import type { ContentPack, PackManifest } from './types'

export const CANONICAL_MANIFEST_FIELDS = [
  'id',
  'name',
  'version',
  'visibility',
  'minAppVersion',
  'license',
  'description',
] as const

// 与 scripts/build-pack.mjs 保持同一规范；构建元数据（hash/builtAt/计数）不参与哈希。
export function canonicalManifest(manifest: PackManifest): Record<string, unknown> {
  const src = manifest as unknown as Record<string, unknown>
  const out: Record<string, unknown> = {}
  for (const key of CANONICAL_MANIFEST_FIELDS) {
    if (src[key] !== undefined) out[key] = src[key]
  }
  return out
}

export function computePackHash(pack: ContentPack): string {
  const canonical = JSON.stringify({
    manifest: canonicalManifest(pack.manifest),
    stages: pack.stages,
    lessons: pack.lessons,
    glossary: pack.glossary,
  })
  return sha256(canonical)
}

export function verifyPack(pack: ContentPack): { ok: boolean; expected: string; actual: string } {
  const actual = computePackHash(pack)
  return { ok: actual === pack.manifest.hash, expected: pack.manifest.hash, actual }
}

export function packStats(pack: ContentPack) {
  const totalMin = pack.lessons.reduce((a, l) => a + l.durationMin, 0)
  const quizzes = pack.lessons.reduce((a, l) => a + l.quiz.length, 0)
  return {
    lessons: pack.lessons.length,
    stages: pack.stages.length,
    minutes: totalMin,
    quizzes,
    words: pack.lessons.reduce((a, l) => a + l.markdown.length, 0),
  }
}

export async function loadPackFromUrl(url: string, init?: RequestInit): Promise<ContentPack> {
  const res = await fetch(url, init)
  if (!res.ok) throw new Error(`内容包加载失败：${res.status}`)
  return (await res.json()) as ContentPack
}
