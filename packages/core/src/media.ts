export type MediaKind = 'video' | 'image' | 'other'

const VIDEO_EXT = /\.(mp4|webm|ogv|ogg|m4v)(?:[?#].*)?$/i
const IMAGE_EXT = /\.(png|jpe?g|gif|webp|avif|svg|bmp)(?:[?#].*)?$/i

export function mediaKind(src: string): MediaKind {
  if (VIDEO_EXT.test(src)) return 'video'
  if (IMAGE_EXT.test(src)) return 'image'
  return 'other'
}

export function packMediaEntry(name: string, packJsonEntry: string): string | null {
  const base = packJsonEntry.includes('/') ? packJsonEntry.slice(0, packJsonEntry.lastIndexOf('/') + 1) : ''
  if (!name.startsWith(base)) return null
  const rel = name.slice(base.length)
  return rel.startsWith('media/') ? rel : null
}
