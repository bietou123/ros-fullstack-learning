// 生成桌面端应用图标（纯 Node，无第三方依赖）：build/icon.png + build/icon.ico
// 用法：node scripts/gen-icons.mjs
import fs from 'node:fs'
import path from 'node:path'
import zlib from 'node:zlib'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const outDir = path.join(root, 'apps/desktop/build')

const BG_TOP = [13, 17, 23]
const BG_BOTTOM = [22, 27, 34]
const INK = [230, 237, 243]
const CYAN = [34, 211, 238]
const AMBER = [245, 158, 11]

function clamp01(x) {
  return Math.max(0, Math.min(1, x))
}

function sdRoundRect(x, y, cx, cy, hw, hh, r) {
  const qx = Math.abs(x - cx) - (hw - r)
  const qy = Math.abs(y - cy) - (hh - r)
  return Math.hypot(Math.max(qx, 0), Math.max(qy, 0)) + Math.min(Math.max(qx, qy), 0) - r
}

function sdSegment(x, y, ax, ay, bx, by) {
  const vx = bx - ax
  const vy = by - ay
  const t = clamp01(((x - ax) * vx + (y - ay) * vy) / (vx * vx + vy * vy))
  return Math.hypot(x - (ax + t * vx), y - (ay + t * vy))
}

function mix(a, b, t) {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]
}

function colorAt(sx, sy, size) {
  const u = sx / size
  const v = sy / size
  const px = sx
  const py = sy

  // 背景：圆角矩形 + 纵向渐变 + 青色描边
  const d = sdRoundRect(px, py, size / 2, size / 2, size * 0.46, size * 0.46, size * 0.18)
  if (d > 1) return null
  let col = mix(BG_TOP, BG_BOTTOM, v)
  if (d > -size * 0.012) col = mix(col, CYAN, 0.9)

  // 底座
  const baseD = sdRoundRect(px, py, size * 0.5, size * 0.84, size * 0.17, size * 0.035, size * 0.02)
  if (baseD <= 0) col = INK

  // 机械臂连杆：base → elbow → wrist
  const w = size * 0.034
  const l1 = sdSegment(px, py, size * 0.42, size * 0.78, size * 0.66, size * 0.52)
  const l2 = sdSegment(px, py, size * 0.66, size * 0.52, size * 0.44, size * 0.3)
  if (l1 <= w || l2 <= w) col = INK

  // 关节
  const joints = [
    [size * 0.42, size * 0.78],
    [size * 0.66, size * 0.52],
    [size * 0.44, size * 0.3],
  ]
  for (const [jx, jy] of joints) {
    if (Math.hypot(px - jx, py - jy) <= size * 0.052) col = CYAN
  }

  // 夹爪
  const g1 = sdSegment(px, py, size * 0.44, size * 0.3, size * 0.35, size * 0.18)
  const g2 = sdSegment(px, py, size * 0.44, size * 0.3, size * 0.53, size * 0.18)
  if (g1 <= size * 0.022 || g2 <= size * 0.022) col = AMBER

  return col
}

function render(size) {
  const buf = Buffer.alloc(size * size * 4)
  const ss = 2
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      let r = 0
      let g = 0
      let b = 0
      let a = 0
      for (let sy = 0; sy < ss; sy++) {
        for (let sx = 0; sx < ss; sx++) {
          const c = colorAt(x + (sx + 0.5) / ss, y + (sy + 0.5) / ss, size)
          if (c) {
            r += c[0]
            g += c[1]
            b += c[2]
            a += 255
          }
        }
      }
      const n = ss * ss
      const i = (y * size + x) * 4
      buf[i] = Math.round(r / n)
      buf[i + 1] = Math.round(g / n)
      buf[i + 2] = Math.round(b / n)
      buf[i + 3] = Math.round(a / n)
    }
  }
  return buf
}

const crcTable = (() => {
  const t = new Int32Array(256)
  for (let n = 0; n < 256; n++) {
    let c = n
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    t[n] = c
  }
  return t
})()

function crc32(buf) {
  let c = -1
  for (const byte of buf) c = crcTable[(c ^ byte) & 0xff] ^ (c >>> 8)
  return (c ^ -1) >>> 0
}

function chunk(type, data) {
  const len = Buffer.alloc(4)
  len.writeUInt32BE(data.length)
  const body = Buffer.concat([Buffer.from(type, 'ascii'), data])
  const crc = Buffer.alloc(4)
  crc.writeUInt32BE(crc32(body))
  return Buffer.concat([len, body, crc])
}

function encodePng(size, rgba) {
  const ihdr = Buffer.alloc(13)
  ihdr.writeUInt32BE(size, 0)
  ihdr.writeUInt32BE(size, 4)
  ihdr[8] = 8
  ihdr[9] = 6
  const raw = Buffer.alloc((size * 4 + 1) * size)
  for (let y = 0; y < size; y++) {
    raw[y * (size * 4 + 1)] = 0
    rgba.copy(raw, y * (size * 4 + 1) + 1, y * size * 4, (y + 1) * size * 4)
  }
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr),
    chunk('IDAT', zlib.deflateSync(raw, { level: 9 })),
    chunk('IEND', Buffer.alloc(0)),
  ])
}

function encodeIco(png256) {
  const header = Buffer.alloc(6)
  header.writeUInt16LE(0, 0)
  header.writeUInt16LE(1, 2)
  header.writeUInt16LE(1, 4)
  const entry = Buffer.alloc(16)
  entry[0] = 0
  entry[1] = 0
  entry[2] = 0
  entry[3] = 0
  entry.writeUInt16LE(1, 4)
  entry.writeUInt16LE(32, 6)
  entry.writeUInt32LE(png256.length, 8)
  entry.writeUInt32LE(22, 12)
  return Buffer.concat([header, entry, png256])
}

fs.mkdirSync(outDir, { recursive: true })
const png512 = encodePng(512, render(512))
const png256 = encodePng(256, render(256))
fs.writeFileSync(path.join(outDir, 'icon.png'), png512)
fs.writeFileSync(path.join(outDir, 'icon.ico'), encodeIco(png256))
console.log(`ICON_OK ${path.join(outDir, 'icon.png')} ${png512.length}B`)
console.log(`ICON_OK ${path.join(outDir, 'icon.ico')} ${fs.statSync(path.join(outDir, 'icon.ico')).size}B`)
