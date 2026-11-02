import { useEffect, useRef, useState } from 'react'
import JSZip from 'jszip'
import {
  deletePrivatePack,
  exportAll,
  importAll,
  listPrivatePacks,
  resetAll,
  savePrivatePack,
  verifyPack,
  type ContentPack,
} from '@rl/core'
import { useApp } from '../store'

declare const __APP_VERSION__: string

async function download(name: string, text: string, type = 'application/json'): Promise<'shared' | 'downloaded'> {
  const capacitor = (window as unknown as { Capacitor?: { isNativePlatform?: () => boolean } }).Capacitor
  if (capacitor?.isNativePlatform?.()) {
    const [{ Filesystem, Directory, Encoding }, { Share }] = await Promise.all([
      import('@capacitor/filesystem'),
      import('@capacitor/share'),
    ])
    const saved = await Filesystem.writeFile({
      path: name,
      data: text,
      directory: Directory.Cache,
      encoding: Encoding.UTF8,
    })
    await Share.share({
      title: '工业机器人学习数据',
      text: '在桌面端设置页导入此 JSON 以迁移学习数据。',
      url: saved.uri,
    })
    return 'shared'
  }
  const blob = new Blob([text], { type })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
  return 'downloaded'
}

export default function SettingsPage() {
  const { pack, privatePacks, activePackId, platform, backend, load, switchPack, refresh } = useApp()
  const packRef = useRef<HTMLInputElement>(null)
  const dataRef = useRef<HTMLInputElement>(null)
  const [msg, setMsg] = useState('')
  const [verify, setVerify] = useState<{ ok: boolean; expected: string; actual: string } | null>(null)

  useEffect(() => {
    if (pack) setVerify(verifyPack(pack))
  }, [pack])

  async function importPack(file: File) {
    try {
      let json = ''
      if (file.name.endsWith('.zip')) {
        const zip = await JSZip.loadAsync(file)
        const entry = Object.keys(zip.files).find((n) => n.endsWith('pack.json'))
        if (!entry) throw new Error('zip 内没有 pack.json')
        json = await zip.files[entry].async('string')
      } else {
        json = await file.text()
      }
      const p = JSON.parse(json) as ContentPack
      if (!p.manifest || !Array.isArray(p.lessons)) throw new Error('不是有效的内容包')
      const v = verifyPack(p)
      await savePrivatePack(p)
      await load()
      await switchPack(p.manifest.id)
      setMsg(`已导入 ${p.manifest.id} · ${p.manifest.version}｜哈希校验${v.ok ? '通过' : '未通过（旧包或已修改）'}`)
      await refresh()
    } catch (e) {
      setMsg(`导入失败：${e instanceof Error ? e.message : String(e)}`)
    }
  }

  if (!pack) return null

  return (
    <div className="page">
      <h1>设置</h1>

      <section className="card">
        <h3>版本信息</h3>
        <dl className="kv">
          <dt>应用版本</dt><dd>{typeof __APP_VERSION__ !== 'undefined' ? __APP_VERSION__ : 'dev'}</dd>
          <dt>平台</dt><dd>{platform} · 实验后端：{backend}</dd>
          <dt>内容包</dt><dd>{pack.manifest.id} · v{pack.manifest.version}</dd>
          <dt>内容哈希</dt><dd><code className="hash">{pack.manifest.hash}</code></dd>
          <dt>构建时间</dt><dd>{new Date(pack.manifest.builtAt).toLocaleString('zh-CN')}</dd>
          <dt>课程数</dt><dd>{pack.manifest.lessonCount} 节 / {pack.manifest.stageCount} 阶段</dd>
          <dt>哈希校验</dt>
          <dd className={verify?.ok ? 'ok' : 'bad'}>
            {verify ? (verify.ok ? '通过（本地重算一致）' : `不一致：重算 ${verify.actual.slice(0, 16)}…`) : '…'}
          </dd>
        </dl>
        {pack.coverage && (
          <p className="muted">
            知识覆盖：知识库 {pack.coverage.total} 项已映射；章节级 teach {pack.coverage.chapterLevel.teach}/{pack.coverage.chapterLevel.teach + (pack.coverage.chapterLevel.read ?? 0)}。
          </p>
        )}
      </section>

      <section className="card">
        <h3>内容包</h3>
        <p className="muted">公开包内置随应用发布；私有包从本地导入，只存本机，不会进入安装包。</p>
        <div className="pack-list">
          <PackRow id="rl.public.core" label="公共课程包（内置）" active={activePackId === 'rl.public.core'} onUse={() => switchPack('rl.public.core')} />
          {privatePacks.map((p) => (
            <PackRow
              key={p.manifest.id}
              id={p.manifest.id}
              label={`${p.manifest.id} · v${p.manifest.version} · ${p.manifest.visibility}`}
              active={activePackId === p.manifest.id}
              onUse={() => switchPack(p.manifest.id)}
              onDelete={async () => { await deletePrivatePack(p.manifest.id); await load(); await refresh() }}
            />
          ))}
        </div>
        <input ref={packRef} type="file" accept=".json,.zip,.pack.json" hidden onChange={(e) => e.target.files?.[0] && importPack(e.target.files[0])} />
        <button className="btn" onClick={() => packRef.current?.click()}>导入私有内容包（.json / .zip）</button>
      </section>

      <section className="card">
        <h3>学习数据</h3>
        <p className="muted">默认只在本机。换设备时导出 JSON，在另一端点导入即可。</p>
        <div className="row gap">
          <button className="btn" onClick={async () => {
            try {
              const how = await download(`ros-learning-data-${Date.now()}.json`, await exportAll())
              if (how === 'shared') setMsg('已生成学习数据文件，请在分享面板中保存或发送到桌面端。')
            } catch (err) {
              const message = err instanceof Error ? err.message : String(err)
              if (!/cancel/i.test(message)) setMsg(`导出失败：${message}`)
            }
          }}>导出学习数据</button>
          <input ref={dataRef} type="file" accept=".json" hidden onChange={async (e) => {
            const f = e.target.files?.[0]
            if (!f) return
            try {
              const r = await importAll(await f.text(), 'merge')
              await refresh()
              setMsg(`导入 ${r.imported} 条记录`)
            } catch (err) {
              setMsg(`导入失败：${err instanceof Error ? err.message : String(err)}`)
            }
          }} />
          <button className="btn" onClick={() => dataRef.current?.click()}>导入学习数据</button>
          <button className="btn danger" onClick={async () => {
            if (!confirm('确定清空本机所有进度、笔记和测验记录？此操作不可撤销。')) return
            await resetAll()
            await refresh()
            setMsg('已清空本机学习数据')
          }}>清空数据</button>
        </div>
        {msg && <p className="notice">{msg}</p>}
      </section>

      <section className="card">
        <h3>实验后端</h3>
        <dl className="kv">
          <dt>当前</dt><dd>{backend}</dd>
          <dt>说明</dt>
          <dd>
            deb 端使用本地 Docker / ROS；exe 端使用 WSL2 或远程 SSH；apk 端使用远程 SSH，未配置时进入只读学习模式。
            界面、步骤与检查项三端一致。
          </dd>
        </dl>
        <p className="muted">
          当前 Android 端尚未接入 SSH 实验后端，实验区只显示步骤与检查项（只读模式），不会伪造执行结果。
          需要实际运行实验时请使用 Windows / Linux 桌面端；SSH 配置能力见仓库路线图。
        </p>
      </section>

      <section className="card">
        <h3>关于</h3>
        <p className="muted">
          工业机器人全栈学习系统 · 离线优先 · 三端同源。<br />
          公司内部课程请通过私有内容包导入；公开仓库只包含引擎与脱敏公共课程。
        </p>
      </section>
    </div>
  )
}

function PackRow({ id, label, active, onUse, onDelete }: { id: string; label: string; active: boolean; onUse: () => void; onDelete?: () => void }) {
  return (
    <div className={`pack-row ${active ? 'active' : ''}`}>
      <div>
        <b>{label}</b>
        <span className="muted">{id}</span>
      </div>
      <div className="row gap">
        {active ? <span className="pill done">使用中</span> : <button className="btn small" onClick={onUse}>切换</button>}
        {onDelete && <button className="link danger" onClick={onDelete}>删除</button>}
      </div>
    </div>
  )
}
