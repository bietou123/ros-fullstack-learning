// 发布前敏感信息扫描：只扫描将要对外公开的内容与构建产物。
// 命中时只输出文件:行号与规则名，不输出明文，避免报告本身泄露。
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const SCAN_DIRS = ['content/packs/public', 'apps/web/public/content']
const SCAN_FILES = ['README.md', 'LICENSE']
const SKIP_EXT = new Set(['.png', '.jpg', '.jpeg', '.gif', '.webp', '.ico', '.woff', '.woff2', '.ttf', '.otf', '.zip', '.apk', '.exe', '.deb', '.keystore', '.jks', '.7z'])

const DOC_IP = /^(192\.0\.2|198\.51\.100|203\.0\.113)\.\d{1,3}$/
const ALLOWED_IP = new Set(['127.0.0.1', '0.0.0.0', '255.255.255.255'])

const RULES = [
  { name: 'private-key', re: /-----BEGIN [A-Z ]*PRIVATE KEY-----/g },
  { name: 'password-assignment', re: /(?<![A-Za-z0-9_$])(?:password|passwd|pwd)\s*[:=]\s*["']?[^\s"']{3,}/gi },
  { name: 'cn-password', re: /(?:密码|口令)\s*[:：=]\s*[^\s，。,;；]{2,}/g },
  { name: 'token-assignment', re: /(?:token|secret|api[_-]?key|access[_-]?key)\s*[:=]\s*["']?[A-Za-z0-9_\-.]{8,}/gi },
  { name: 'bearer-token', re: /Bearer\s+[A-Za-z0-9_\-.=]{10,}/g },
  { name: 'internal-url', re: /https?:\/\/[^\s)"']*(?:\.internal|\.corp|\.intra|confluence|jira|popo|oa\.|gitlab\.|gitea\.)[^\s)"']*/gi },
  { name: 'personal-path', re: /[A-Za-z]:[\\/](?:Users|Private data|Documents and Settings)[\\/][^\s)"'，。]*/gi },
  { name: 'email', re: /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g },
  { name: 'cn-mobile', re: /(?<!\d)1[3-9]\d{9}(?!\d)/g },
  { name: 'customer-name', re: /(柳工|广西柳工|网易|NetEase|伏羲)/g },
  { name: 'serial-number', re: /(?:SN|序列号|设备号)\s*[:：]?\s*[A-Z0-9][A-Z0-9-]{6,}/g },
  { name: 'price', re: /[¥￥]\s*\d[\d,.]*|\d+(?:\.\d+)?\s*万元/g },
]

const findings = []

function isAllowedIp(ip) {
  return ALLOWED_IP.has(ip) || DOC_IP.test(ip)
}

function scanText(rel, text) {
  for (const rule of RULES) {
    rule.re.lastIndex = 0
    let m
    while ((m = rule.re.exec(text)) !== null) {
      const raw = m[0]
      if (rule.name === 'email' && /@(?:users\.noreply\.github\.com|example\.(?:com|org|invalid))$/i.test(raw)) continue
      const line = text.slice(0, m.index).split('\n').length
      findings.push({ file: rel, line, rule: rule.name, sample: mask(raw) })
      if (findings.length > 500) return
    }
  }
  // IPv4 单独判断，排除文档保留段与回环
  const ipRe = /(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])/g
  let ipm
  while ((ipm = ipRe.exec(text)) !== null) {
    if (isAllowedIp(ipm[0])) continue
    const line = text.slice(0, ipm.index).split('\n').length
    findings.push({ file: rel, line, rule: 'ipv4', sample: mask(ipm[0]) })
  }
}

function mask(s) {
  const t = String(s).trim()
  if (t.length <= 4) return '*'.repeat(t.length)
  return t.slice(0, 2) + '*'.repeat(Math.min(10, t.length - 2))
}

function walk(dir) {
  if (!fs.existsSync(dir)) return
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      walk(full)
      continue
    }
    if (SKIP_EXT.has(path.extname(entry.name).toLowerCase())) continue
    if (entry.name.length > 2 * 1024 * 1024) continue
    const rel = path.relative(root, full).replace(/\\/g, '/')
    scanText(rel, fs.readFileSync(full, 'utf8'))
  }
}

for (const d of SCAN_DIRS) walk(path.join(root, d))
for (const f of SCAN_FILES) {
  const full = path.join(root, f)
  if (fs.existsSync(full)) scanText(f, fs.readFileSync(full, 'utf8'))
}

if (findings.length === 0) {
  console.log('SCAN_OK 未发现敏感信息')
  process.exit(0)
}

const byRule = new Map()
for (const f of findings) byRule.set(f.rule, (byRule.get(f.rule) || 0) + 1)
console.log(`SCAN_FAIL 命中 ${findings.length} 处：`)
for (const [k, v] of [...byRule.entries()].sort((a, b) => b[1] - a[1])) console.log(`  - ${k}: ${v}`)
for (const f of findings.slice(0, 60)) console.log(`  ${f.file}:${f.line} [${f.rule}] ${f.sample}`)
if (findings.length > 60) console.log(`  ... 其余 ${findings.length - 60} 条省略`)
process.exit(1)
