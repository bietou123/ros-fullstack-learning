import { useEffect, useState } from 'react'
import { detectBackend, runExperiment, type BackendKind, type ExperimentResult, type ExperimentSpec } from '@rl/core'

export default function Experiment({ spec }: { spec: ExperimentSpec }) {
  const [backend, setBackend] = useState<BackendKind | null>(null)
  const [result, setResult] = useState<ExperimentResult | null>(null)
  const [running, setRunning] = useState(false)

  useEffect(() => {
    detectBackend().then(setBackend)
    setResult(null)
  }, [spec.id])

  async function run() {
    setRunning(true)
    setResult(await runExperiment(spec))
    setRunning(false)
  }

  const canRun = backend === 'local' || backend === 'wsl2' || backend === 'ssh'

  return (
    <div className="card experiment">
      <div className="exp-head">
        <h3>动手实验</h3>
        <span className={`pill backend ${backend ?? 'unknown'}`}>{backendLabel(backend)}</span>
      </div>
      <dl className="kv">
        <dt>环境</dt><dd>{spec.image ?? '宿主 ROS 环境'}</dd>
        <dt>超时</dt><dd>{spec.timeoutSec}s</dd>
        <dt>Headless</dt><dd>{spec.headless ? '是' : '否'}</dd>
      </dl>
      <ol className="cmds">
        {spec.commands.map((c, i) => (
          <li key={i}><code>{c}</code></li>
        ))}
      </ol>
      {spec.expected && <p className="muted">预期：{spec.expected}</p>}

      {!canRun && (
        <div className="notice">
          当前设备不能运行实验。可以查看步骤，或到设置页配置 Linux 后端（WSL2 / SSH）。
        </div>
      )}

      <button className="btn primary" disabled={running} onClick={run}>
        {running ? '运行中…' : canRun ? '运行实验' : '查看只读结果'}
      </button>

      {result && (
        <div className={`exp-result ${result.ok ? 'ok' : 'bad'}`}>
          <div className="row"><b>后端</b><span>{result.backend}</span><b>结果</b><span>{result.ok ? '通过' : result.reason ?? '失败'}</span></div>
          {result.steps.map((s, i) => (
            <details key={i} open={s.code !== 0}>
              <summary>步骤 {i + 1} · 退出码 {s.code} · {s.ms}ms</summary>
              <pre>{s.cmd}</pre>
              {s.stdout && <pre className="out">{s.stdout}</pre>}
              {s.stderr && <pre className="err">{s.stderr}</pre>}
            </details>
          ))}
          {result.checks.length > 0 && (
            <ul className="checks">
              {result.checks.map((c, i) => (
                <li key={i} className={c.ok ? 'ok' : 'bad'}>{c.ok ? '✓' : '✗'} {c.name} — {c.detail}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

function backendLabel(b: BackendKind | null) {
  if (!b) return '检测中…'
  return { local: '本地 Docker / ROS', wsl2: 'WSL2', ssh: '远程 SSH', 'read-only': '只读模式' }[b]
}
