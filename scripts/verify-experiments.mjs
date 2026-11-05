// 全量课程实验回归：按 App 相同的「每条命令/检查独立容器」语义逐条执行。
// 用法：node scripts/verify-experiments.mjs [--only S1-01,S3-04] [--json <file>]
// Windows 上通过 WSL 调用 Docker/宿主 bash，可用 RL_WSL_DISTRO 指定发行版（默认 Ubuntu-24.04）。
import fs from 'node:fs'
import path from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import yaml from 'js-yaml'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const coursesDir = path.join(root, 'content/packs/public/courses')
const isWindows = process.platform === 'win32'
const distro = process.env.RL_WSL_DISTRO || 'Ubuntu-24.04'

const onlyArg = process.argv.find((a) => a.startsWith('--only'))
const only = onlyArg
  ? (onlyArg.includes('=') ? onlyArg.split('=')[1] : process.argv[process.argv.indexOf('--only') + 1] || '')
      .split(',').map((s) => s.trim()).filter(Boolean)
  : null
const jsonIdx = process.argv.indexOf('--json')
const jsonOut = jsonIdx >= 0 ? process.argv[jsonIdx + 1] : null

function loadExperiments() {
  const out = []
  for (const stage of fs.readdirSync(coursesDir)) {
    const stageDir = path.join(coursesDir, stage)
    if (!fs.statSync(stageDir).isDirectory()) continue
    for (const lessonDir of fs.readdirSync(stageDir)) {
      const metaPath = path.join(stageDir, lessonDir, 'meta.yaml')
      if (!fs.existsSync(metaPath)) continue
      const meta = yaml.load(fs.readFileSync(metaPath, 'utf8'))
      if (meta.experiment) out.push(meta)
    }
  }
  out.sort((a, b) => a.id.localeCompare(b.id, 'en', { numeric: true }))
  return out
}

function runShell(cmd, useDocker, image, network, timeoutMs) {
  if (isWindows) {
    if (!useDocker) {
      return spawnSync('wsl.exe', ['-d', distro, '-e', 'bash', '-lc', cmd], { encoding: 'utf8', timeout: timeoutMs })
    }
    const args = ['-d', distro, '-e', 'docker', 'run', '--rm']
    if (network) args.push('--network', network)
    args.push(image, 'bash', '-lc', cmd)
    return spawnSync('wsl.exe', args, { encoding: 'utf8', timeout: timeoutMs })
  }
  if (!useDocker) {
    return spawnSync('bash', ['-lc', cmd], { encoding: 'utf8', timeout: timeoutMs })
  }
  const args = ['run', '--rm']
  if (network) args.push('--network', network)
  args.push(image, 'bash', '-lc', cmd)
  return spawnSync('docker', args, { encoding: 'utf8', timeout: timeoutMs })
}

const experiments = loadExperiments().filter((m) => !only || only.includes(m.id))
if (experiments.length === 0) {
  console.error('没有匹配的课程实验')
  process.exit(1)
}

console.log(`experiments: ${experiments.length}${only ? ` (${only.join(', ')})` : ''}`)
let failures = 0
const results = []

for (const meta of experiments) {
  const exp = meta.experiment
  const useDocker = exp.ros && exp.ros !== 'none'
  const image = exp.image || (exp.ros === 'ros2' ? 'ros:humble-ros-base' : exp.ros === 'ros1' ? 'ros:noetic-ros-base' : null)
  if (useDocker && !image) {
    console.log(`FAIL ${meta.id} 缺少实验镜像`)
    failures++
    results.push({ id: meta.id, ok: false, failed: ['image'] })
    continue
  }
  const timeoutMs = (exp.timeoutSec || 300) * 1000 + 60000
  const commands = [...(exp.commands || []), ...(exp.checks || [])]
  const labels = [
    ...(exp.commands || []).map((_, i) => `cmd${i + 1}`),
    ...(exp.checks || []).map((_, i) => `check${i + 1}`),
  ]
  const start = Date.now()
  const failed = []
  for (let i = 0; i < commands.length; i++) {
    const r = runShell(commands[i], useDocker, image, exp.network, timeoutMs)
    if (r.status !== 0) {
      failures++
      failed.push(labels[i])
      console.log(`FAIL ${meta.id} ${labels[i]} exit=${r.status}`)
      console.log('  stderr:', (r.stderr || '').slice(-400).trim())
      console.log('  stdout:', (r.stdout || '').slice(-400).trim())
    }
  }
  const sec = Math.round((Date.now() - start) / 1000)
  const ok = failed.length === 0
  console.log(`${ok ? 'PASS' : 'FAIL'} ${meta.id} ${useDocker ? image : 'host'} ${labels.length}项 ${sec}s`)
  results.push({ id: meta.id, ok, sec, backend: useDocker ? image : 'host', failed })
}

const passed = results.filter((r) => r.ok).length
console.log(`\nTOTAL ${passed}/${results.length} lessons, failures=${failures}`)
if (jsonOut) {
  fs.writeFileSync(jsonOut, JSON.stringify({ generatedAt: new Date().toISOString(), passed, total: results.length, failures, results }, null, 2))
  console.log(`JSON ${jsonOut}`)
}
process.exit(failures === 0 ? 0 : 1)
