import { useEffect, useState } from 'react'
import { getPackMedia } from '@rl/core'

const MEDIA_RE = /(!\[[^\]]*\]\()((?:\.\/)?media\/[^)\s]+)(\))/g

export function useResolvedMarkdown(markdown: string, packId: string, isPublic: boolean): string {
  const [resolved, setResolved] = useState(markdown)

  useEffect(() => {
    let alive = true
    const urls: string[] = []
    setResolved(markdown)
    const refs = [...new Set([...markdown.matchAll(MEDIA_RE)].map((m) => m[2]))]
    if (!refs.length) return

    ;(async () => {
      let next = markdown
      for (const ref of refs) {
        const clean = ref.replace(/^\.\//, '')
        let url = ''
        if (isPublic) {
          url = `content/${clean}`
        } else {
          const blob = await getPackMedia(packId, clean)
          if (blob) {
            url = URL.createObjectURL(blob) + '#' + clean
            urls.push(url)
          }
        }
        if (url) next = next.split(`(${ref})`).join(`(${url})`)
      }
      if (alive) setResolved(next)
    })().catch(() => {})

    return () => {
      alive = false
      for (const u of urls) URL.revokeObjectURL(u)
    }
  }, [markdown, packId, isPublic])

  return resolved
}
