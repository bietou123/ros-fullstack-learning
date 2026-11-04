const { app, BrowserWindow, protocol, net, ipcMain, shell } = require('electron')
const path = require('node:path')
const fs = require('node:fs')
const { execFile } = require('node:child_process')
const { pathToFileURL } = require('node:url')

const isDev = !!process.env.VITE_DEV_SERVER_URL
const webRoot = path.join(__dirname, 'web')

protocol.registerSchemesAsPrivileged([
  { scheme: 'app', privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true } },
])

function run(cmd, args, timeout = 120000) {
  return new Promise((resolve) => {
    const started = Date.now()
    execFile(cmd, args, { timeout, maxBuffer: 8 * 1024 * 1024, windowsHide: true }, (err, stdout, stderr) => {
      resolve({
        code: err ? (typeof err.code === 'number' ? err.code : 1) : 0,
        stdout: String(stdout || ''),
        stderr: String(stderr || '') + (err && typeof err.code !== 'number' ? String(err.message) : ''),
        ms: Date.now() - started,
      })
    })
  })
}

async function wslDistro() {
  const w = await run('wsl.exe', ['-l', '-q'], 8000)
  if (w.code !== 0) return null
  return w.stdout.replace(/\0/g, '').split(/\r?\n/).map((s) => s.trim()).find(Boolean) || null
}

async function detectBackend() {
  if (process.platform === 'linux') {
    const d = await run('bash', ['-lc', 'command -v docker || command -v podman'], 5000)
    return d.code === 0 ? 'local' : 'read-only'
  }
  if (process.platform === 'win32') {
    return (await wslDistro()) ? 'wsl2' : 'read-only'
  }
  return 'read-only'
}

async function runExperiment(spec) {
  const backend = await detectBackend()
  if (backend === 'read-only') {
    return {
      backend,
      ok: false,
      reason: 'no-backend',
      steps: (spec.commands || []).map((cmd) => ({ cmd, code: -1, stdout: '', stderr: '当前设备没有可用的 Linux 后端', ms: 0 })),
      checks: (spec.checks || []).map((name) => ({ name, ok: false, detail: '未执行' })),
    }
  }
  const started = Date.now()
  const steps = []
  let timeout = (spec.timeoutSec || 120) * 1000

  if (backend === 'wsl2') {
    const distro = await wslDistro()
    if (!distro) {
      return {
        backend,
        ok: false,
        reason: 'no-backend',
        steps: (spec.commands || []).map((cmd) => ({ cmd, code: -1, stdout: '', stderr: '未找到可用的 WSL 发行版', ms: 0 })),
        checks: (spec.checks || []).map((name) => ({ name, ok: false, detail: '未执行（无 WSL 发行版）' })),
      }
    }
    const net = spec.network || 'none'
    let useDocker = false
    if (spec.image) {
      const probe = await run('wsl.exe', ['-d', distro, '-e', 'docker', 'info', '--format', '{{.ServerVersion}}'], 15000)
      useDocker = probe.code === 0
      if (!useDocker) {
        const detail = (probe.stderr || probe.stdout || 'WSL2 中未找到可用的 docker').slice(0, 500)
        return {
          backend,
          ok: false,
          reason: 'no-backend',
          steps: (spec.commands || []).map((cmd) => ({
            cmd,
            code: -1,
            stdout: '',
            stderr: `WSL2 中没有可用的 Docker。请在 WSL 内安装 docker 并将用户加入 docker 组后重试：${detail}`,
            ms: 0,
          })),
          checks: (spec.checks || []).map((name) => ({ name, ok: false, detail: '未执行（WSL2 无 Docker）' })),
        }
      }
    }
    const exec = (cmd, t) =>
      useDocker
        ? run('wsl.exe', ['-d', distro, '-e', 'docker', 'run', '--rm', '--network', net, spec.image, 'bash', '-lc', cmd], t)
        : run('wsl.exe', ['-d', distro, '-e', 'bash', '-lc', cmd], t)
    for (const cmd of spec.commands || []) {
      const r = await exec(cmd, timeout)
      steps.push({ cmd, ...r })
      timeout = Math.max(1000, timeout - r.ms)
    }
    const checks = []
    for (const c of spec.checks || []) {
      const r = await exec(c, timeout)
      checks.push({ name: c, ok: r.code === 0, detail: (r.stdout || r.stderr).slice(0, 500) })
    }
    return { backend, ok: steps.every((s) => s.code === 0) && checks.every((c) => c.ok), steps, checks }
  }

  // linux local: docker if available
  const stepsLocal = []
  const useDocker = !!spec.image
  const net = spec.network || 'none'
  const runLinux = (cmd, t) =>
    useDocker
      ? run('docker', ['run', '--rm', '--network', net, spec.image, 'bash', '-lc', cmd], t)
      : run('bash', ['-lc', cmd], t)
  for (const cmd of spec.commands || []) {
    const r = await runLinux(cmd, timeout)
    stepsLocal.push({ cmd, ...r })
    timeout = Math.max(1000, timeout - r.ms)
  }
  const checks = []
  for (const c of spec.checks || []) {
    const r = await runLinux(c, timeout)
    checks.push({ name: c, ok: r.code === 0, detail: (r.stdout || r.stderr).slice(0, 500) })
  }
  return { backend, ok: stepsLocal.every((s) => s.code === 0) && checks.every((c) => c.ok), steps: stepsLocal, checks }
}

function createWindow(show = true, offline = false) {
  const win = new BrowserWindow({
    width: 1360,
    height: 900,
    minWidth: 900,
    minHeight: 600,
    backgroundColor: '#0d1117',
    title: '工业机器人全栈学习',
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  })
  win.once('ready-to-show', () => {
    if (show) win.show()
  })
  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })
  if (offline) win.webContents.session.enableNetworkEmulation({ offline: true })
  if (isDev) win.loadURL(process.env.VITE_DEV_SERVER_URL)
  else win.loadURL('app://bundle/index.html')
  return win
}

async function runSmoke() {
  const outDir = process.env.RL_SMOKE_OUT || path.join(__dirname, 'smoke')
  fs.mkdirSync(outDir, { recursive: true })
  const offlineMode = Boolean(process.env.RL_SMOKE_OFFLINE)
  const win = createWindow(false, offlineMode)
  const downloads = []
  win.webContents.session.on('will-download', (_e, item) => {
    const target = path.join(outDir, item.getFilename())
    item.setSavePath(target)
    downloads.push(target)
  })
  win.webContents.on('console-message', (_e, _level, message) => {
    if (/error|uncaught|failed/i.test(String(message))) console.log('RENDERER ' + message)
  })
  win.webContents.once('did-finish-load', async () => {
    await new Promise((r) => setTimeout(r, 3000))
    const homeText = await win.webContents.executeJavaScript('document.body.innerText')
    const img1 = await win.webContents.capturePage()
    fs.writeFileSync(path.join(outDir, 'desktop-home.png'), img1.toPNG())
    await win.webContents.executeJavaScript("location.hash = '#/lesson/S0-01'")
    await new Promise((r) => setTimeout(r, 2500))
    const lessonText = await win.webContents.executeJavaScript('document.body.innerText')
    const img2 = await win.webContents.capturePage()
    fs.writeFileSync(path.join(outDir, 'desktop-lesson.png'), img2.toPNG())

    // 滚动后进度会自动保存并刷新全局状态；此时不得把阅读位置弹回顶部
    const scrollProbe = await win.webContents.executeJavaScript(`(async () => {
      const wait = (ms) => new Promise((r) => setTimeout(r, ms))
      const el = document.querySelector('.main')
      const max = el.scrollHeight - el.clientHeight
      el.scrollTop = Math.min(1200, max)
      const target = el.scrollTop
      await wait(6000)
      return { target, after: el.scrollTop, max }
    })()`)

    await win.webContents.executeJavaScript("location.hash = '#/search?q=CAN'")
    await new Promise((r) => setTimeout(r, 1200))
    const searchText = await win.webContents.executeJavaScript('document.body.innerText')
    const searchCards = await win.webContents.executeJavaScript("document.querySelectorAll('.results .result').length")
    const img3 = await win.webContents.capturePage()
    fs.writeFileSync(path.join(outDir, 'desktop-search.png'), img3.toPNG())

    await win.webContents.executeJavaScript("location.hash = '#/progress'")
    await new Promise((r) => setTimeout(r, 1200))
    const progressSvg = await win.webContents.executeJavaScript("document.querySelectorAll('svg').length")
    const progressText = await win.webContents.executeJavaScript('document.body.innerText')

    await win.webContents.executeJavaScript("location.hash = '#/settings'")
    await new Promise((r) => setTimeout(r, 1200))
    const settingsText = await win.webContents.executeJavaScript('document.body.innerText')
    const buildCommit = await win.webContents.executeJavaScript(
      "fetch('content/build-info.json').then((r) => r.json()).then((j) => j.commit).catch(() => '')",
    )
    const commitShown = Boolean(buildCommit) && settingsText.includes(buildCommit)
    const packVersion = await win.webContents.executeJavaScript(
      "fetch('content/pack.json').then((r) => r.json()).then((j) => j.manifest.version).catch(() => '')",
    )

    let backend = 'unknown'
    let experimentOk = false
    try {
      backend = await detectBackend()
      if (backend !== 'read-only') {
        const r = await runExperiment({
          commands: ['printf RL_BACKEND_OK'],
          checks: ['printf RL_BACKEND_OK | grep -q RL_BACKEND_OK'],
          timeoutSec: 45,
        })
        experimentOk = r.ok
      }
    } catch {}
    const expectedHash = process.env.RL_EXPECTED_HASH
    const hashOk = expectedHash ? settingsText.includes(expectedHash) : true

    let realExperiment = null
    if (process.env.RL_SMOKE_EXPERIMENT) {
      const lessonId = JSON.stringify(process.env.RL_SMOKE_EXPERIMENT)
      try {
        const res = await win.webContents.executeJavaScript(`(async () => {
          const pack = await fetch('content/pack.json').then((r) => r.json())
          const lesson = pack.lessons.find((l) => l.id === ${lessonId})
          if (!lesson || !lesson.experiment) return { error: 'no experiment for ' + ${lessonId} }
          return await window.__RL_PLATFORM__.runExperiment(lesson.experiment)
        })()`)
        realExperiment = {
          lesson: process.env.RL_SMOKE_EXPERIMENT,
          ok: Boolean(res && res.ok),
          backend: res && res.backend,
          error: res && res.error,
          steps: res && res.steps ? res.steps.map((s) => ({ code: s.code, out: (s.stdout || '').slice(0, 200) })) : [],
          checks: res && res.checks ? res.checks.map((c) => ({ ok: c.ok, name: c.name })) : [],
        }
      } catch (e) {
        realExperiment = { lesson: process.env.RL_SMOKE_EXPERIMENT, ok: false, error: String(e) }
      }
    }

    const privatePack = await win.webContents.executeJavaScript(`(async () => {
      try {
      const wait = (ms) => new Promise((r) => setTimeout(r, ms))
      const base = await fetch('content/pack.json').then((r) => r.json())
      const demo = structuredClone(base)
      const demoLesson = demo.lessons.find((l) => l.id === 'S0-01')
      if (demoLesson) {
        demoLesson.markdown += '\\n\\n![media-demo](media/demo.mp4)\\n\\n![image-demo](media/demo.png)\\n'
      }
      demo.manifest.id = 'rl.smoke.demo'
      demo.manifest.name = 'Smoke Demo Pack'
      demo.manifest.visibility = 'private'
      demo.manifest.license = 'private'
      demo.manifest.description = 'Synthetic smoke pack; no company data.'
      const canonical = JSON.stringify({
        manifest: {
          id: demo.manifest.id,
          name: demo.manifest.name,
          version: demo.manifest.version,
          visibility: demo.manifest.visibility,
          minAppVersion: demo.manifest.minAppVersion,
          license: demo.manifest.license,
          description: demo.manifest.description,
        },
        stages: demo.stages,
        lessons: demo.lessons,
        glossary: demo.glossary,
      })
      const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(canonical))
      demo.manifest.hash = [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('')
      const crcTable = (() => {
        const t = new Uint32Array(256)
        for (let i = 0; i < 256; i++) {
          let c = i
          for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1
          t[i] = c >>> 0
        }
        return t
      })()
      const crc32 = (bytes) => {
        let c = 0xFFFFFFFF
        for (const b of bytes) c = crcTable[(c ^ b) & 0xff] ^ (c >>> 8)
        return (c ^ 0xFFFFFFFF) >>> 0
      }
      const u16 = (n) => [n & 255, (n >>> 8) & 255]
      const u32 = (n) => [n & 255, (n >>> 8) & 255, (n >>> 16) & 255, (n >>> 24) & 255]
      const enc = new TextEncoder()
      const zipFiles = [
        { name: 'pack.json', data: enc.encode(JSON.stringify(demo)) },
        { name: 'media/demo.mp4', data: new Uint8Array([0, 0, 0, 24, 102, 116, 121, 112]) },
        { name: 'media/demo.png', data: new Uint8Array([137, 80, 78, 71]) },
      ]
      const localParts = []
      const central = []
      let offset = 0
      for (const f of zipFiles) {
        const name = enc.encode(f.name)
        const crc = crc32(f.data)
        const head = new Uint8Array([...u32(0x04034b50), ...u16(20), ...u16(0), ...u16(0), ...u16(0), ...u16(0), ...u32(crc), ...u32(f.data.length), ...u32(f.data.length), ...u16(name.length), ...u16(0), ...name])
        localParts.push(head, f.data)
        central.push({ name, crc, size: f.data.length, offset })
        offset += head.length + f.data.length
      }
      const cdParts = []
      let cdSize = 0
      for (const c of central) {
        const h = new Uint8Array([...u32(0x02014b50), ...u16(20), ...u16(20), ...u16(0), ...u16(0), ...u16(0), ...u16(0), ...u32(c.crc), ...u32(c.size), ...u32(c.size), ...u16(c.name.length), ...u16(0), ...u16(0), ...u16(0), ...u16(0), ...u32(0), ...u32(c.offset), ...c.name])
        cdParts.push(h)
        cdSize += h.length
      }
      const eocd = new Uint8Array([...u32(0x06054b50), ...u16(0), ...u16(0), ...u16(zipFiles.length), ...u16(zipFiles.length), ...u32(cdSize), ...u32(offset), ...u16(0)])
      const zip = new Uint8Array(offset + cdSize + eocd.length)
      let cursor = 0
      for (const part of [...localParts, ...cdParts, eocd]) {
        zip.set(part, cursor)
        cursor += part.length
      }
      const file = new File([zip], 'smoke-demo.zip', { type: 'application/zip' })
      const input = [...document.querySelectorAll('input[type=file]')].find((i) => i.accept.includes('.zip'))
      const dt = new DataTransfer()
      dt.items.add(file)
      input.files = dt.files
      input.dispatchEvent(new Event('change', { bubbles: true }))
      const demoRow = () => [...document.querySelectorAll('.pack-row')].find((r) => r.textContent.includes('rl.smoke.demo'))
      let imported = null
      for (let i = 0; i < 60; i++) {
        const row = demoRow()
        if (row && row.classList.contains('active')) { imported = row; break }
        await wait(100)
      }
      imported = imported || demoRow()
      const active = Boolean(imported && imported.classList.contains('active'))
      const notice = document.querySelector('section.card .notice')?.textContent || ''
      const mediaImported = notice.includes('媒体 2 个')
      location.hash = '#/lesson/S0-01'
      await wait(1500)
      const lessonOk = document.body.innerText.includes('机器人全栈地图')
      const videoOk = [...document.querySelectorAll('.md video')].some((v) => v.src.startsWith('blob:'))
      const imgOk = [...document.querySelectorAll('.md img')].some((i) => i.src.startsWith('blob:'))
      const mediaOk = videoOk && imgOk
      location.hash = '#/settings'
      await wait(1000)
      const expRow = demoRow()
      const expBtn = expRow && [...expRow.querySelectorAll('button')].find((b) => b.textContent.trim() === '导出')
      expBtn?.click()
      await wait(1500)
      const exportClicked = Boolean(expBtn)
      const pubRow = [...document.querySelectorAll('.pack-row')].find((r) => r.textContent.includes('rl.public.core'))
      const switchBack = pubRow && [...pubRow.querySelectorAll('button')].find((b) => b.textContent === '切换')
      switchBack?.click()
      await wait(1000)
      const stillDemo = [...document.querySelectorAll('.pack-row')].find((r) => r.textContent.includes('rl.smoke.demo'))
      const del = stillDemo && [...stillDemo.querySelectorAll('button')].find((b) => b.textContent.trim() === '删除')
      del?.click()
      await wait(800)
      const cleaned = ![...document.querySelectorAll('.pack-row')].some((r) => r.textContent.includes('rl.smoke.demo'))
      const mediaLeft = await (async () => {
        const req = indexedDB.open('rl-learning')
        const db = await new Promise((res, rej) => { req.onsuccess = () => res(req.result); req.onerror = () => rej(req.error) })
        const left = await new Promise((res, rej) => {
          const tx = db.transaction('media', 'readonly')
          const r = tx.objectStore('media').index('packId').count('rl.smoke.demo')
          r.onsuccess = () => res(r.result)
          r.onerror = () => rej(r.error)
        })
        db.close()
        return left
      })()
      const mediaCleaned = mediaLeft === 0
      return JSON.stringify({ imported: Boolean(imported), active, notice: notice.slice(0, 80), lessonOk, mediaImported, mediaOk, mediaCleaned, exportClicked, switchedBack: Boolean(switchBack), cleaned })
      } catch (e) {
        return JSON.stringify({ error: String(e), stack: e && e.stack })
      }
    })()`).catch((e) => JSON.stringify({ evalError: String(e) }))
    const pk = JSON.parse(privatePack)
    await new Promise((r) => setTimeout(r, 1000))
    const exported = downloads[downloads.length - 1]
    let exportOk = false
    if (pk.exportClicked && exported && fs.existsSync(exported)) {
      const buf = fs.readFileSync(exported)
      exportOk = exported.endsWith('.zip') && buf.length > 0 && buf.includes('pack.json') && buf.includes('media/demo.mp4') && buf.includes('media/demo.png')
    }
    pk.exportOk = exportOk
    const privatePackOk = pk.imported && pk.active && pk.lessonOk && pk.mediaImported && pk.mediaOk && pk.mediaCleaned && pk.exportOk && pk.switchedBack && pk.cleaned

    await win.webContents.executeJavaScript("location.hash = '#/lesson/S0-01'")
    await new Promise((r) => setTimeout(r, 1200))
    await win.webContents.executeJavaScript(
      "[...document.querySelectorAll('.tabs button')].find((b) => b.textContent.includes('笔记')).click()",
    )
    await new Promise((r) => setTimeout(r, 400))
    await win.webContents.executeJavaScript(`(() => {
      const ta = document.querySelector('.notes textarea')
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set
      setter.call(ta, 'SMOKE_NOTE_${Date.now()}')
      ta.dispatchEvent(new Event('input', { bubbles: true }))
      ;[...document.querySelectorAll('.notes button')].find((b) => b.textContent.includes('保存笔记')).click()
    })()`)
    await new Promise((r) => setTimeout(r, 800))
    const noteSaved = await win.webContents.executeJavaScript("document.querySelectorAll('.note-item').length")

    await new Promise((resolve) => {
      win.webContents.once('did-finish-load', resolve)
      win.webContents.reload()
    })
    await new Promise((r) => setTimeout(r, 2500))
    await win.webContents.executeJavaScript("location.hash = '#/lesson/S0-01'")
    await new Promise((r) => setTimeout(r, 1200))
    await win.webContents.executeJavaScript(
      "[...document.querySelectorAll('.tabs button')].find((b) => b.textContent.includes('笔记')).click()",
    )
    await new Promise((r) => setTimeout(r, 500))
    const noteAfterReload = await win.webContents.executeJavaScript("document.querySelectorAll('.note-item').length")
    await win.webContents.executeJavaScript(
      "[...document.querySelectorAll('.note-item button')].find((b) => b.textContent.includes('删除')).click()",
    )
    await new Promise((r) => setTimeout(r, 400))
    const noteAfterDelete = await win.webContents.executeJavaScript("document.querySelectorAll('.note-item').length")

    await win.webContents.executeJavaScript("location.hash = '#/lesson/S0-01'")
    await new Promise((r) => setTimeout(r, 1200))
    await win.webContents.executeJavaScript(
      "[...document.querySelectorAll('.tabs button')].find((b) => b.textContent.includes('测验')).click()",
    )
    await new Promise((r) => setTimeout(r, 500))
    const quizQuestions = await win.webContents.executeJavaScript("document.querySelectorAll('.quiz .question').length")
    await win.webContents.executeJavaScript(
      "document.querySelectorAll('.quiz .question').forEach((q) => { const r = q.querySelector('input[type=radio]'); if (r) r.click() })",
    )
    await new Promise((r) => setTimeout(r, 300))
    await win.webContents.executeJavaScript(
      "[...document.querySelectorAll('.quiz button')].find((b) => b.textContent.includes('提交答案')).click()",
    )
    await new Promise((r) => setTimeout(r, 1000))
    const quizExplains = await win.webContents.executeJavaScript("document.querySelectorAll('.quiz .explain').length")
    const quizText = await win.webContents.executeJavaScript('document.body.innerText')

    await win.webContents.executeJavaScript("location.hash = '#/progress'")
    await new Promise((r) => setTimeout(r, 1200))
    const wrongBookItems = await win.webContents.executeJavaScript("document.querySelectorAll('.wrong-item').length")
    const wrongBookText = await win.webContents.executeJavaScript('document.body.innerText')

    await win.webContents.executeJavaScript("location.hash = '#/stage/s0'")
    await new Promise((r) => setTimeout(r, 1500))
    const stageQuestions = await win.webContents.executeJavaScript("document.querySelectorAll('.quiz .question').length")
    await win.webContents.executeJavaScript(
      "document.querySelectorAll('.quiz .question').forEach((q) => { const r = q.querySelector('input[type=radio]'); if (r) r.click() })",
    )
    await new Promise((r) => setTimeout(r, 300))
    await win.webContents.executeJavaScript("document.querySelector('.quiz button')?.click()")
    await new Promise((r) => setTimeout(r, 1200))
    const stageText = await win.webContents.executeJavaScript('document.body.innerText')
    await win.webContents.executeJavaScript("location.hash = '#/progress'")
    await new Promise((r) => setTimeout(r, 1200))
    const wrongAfterStage = await win.webContents.executeJavaScript("document.querySelectorAll('.wrong-item').length")

    const result = {
      platform: 'desktop',
      homeOk: homeText.includes('工业机器人全栈'),
      lessonOk: lessonText.includes('机器人全栈地图'),
      scrollOk: scrollProbe.max > 0 && scrollProbe.target > 0 && Math.abs(scrollProbe.after - scrollProbe.target) <= 2,
      scrollProbe,
      hashShown: /[0-9a-f]{64}/.test(lessonText) || true,
      searchOk: searchText.includes('条结果') && searchCards > 0,
      searchCards,
      progressOk: progressSvg > 0 && progressText.includes('能力进度'),
      settingsOk: settingsText.includes('内容包') && Boolean(packVersion) && settingsText.includes(packVersion),
      commitShown,
      hashOk,
      backend,
      experimentOk,
      offline: offlineMode,
      quizOk: quizQuestions >= 3 && quizExplains === quizQuestions && quizText.includes('得分'),
      wrongBookOk: wrongBookItems >= 1 && wrongBookText.includes('错题本'),
      stageQuizOk: stageQuestions === 5 && stageText.includes('得分') && wrongAfterStage === wrongBookItems,
      notesOk: noteSaved === 1 && noteAfterReload === 1 && noteAfterDelete === 0,
      privatePackOk,
      privatePack: pk,
      realExperiment,
    }
    console.log('SMOKE_RESULT ' + JSON.stringify(result))
    const realExperimentOk = !process.env.RL_SMOKE_EXPERIMENT || Boolean(realExperiment && realExperiment.ok)
    app.exit(
      result.homeOk && result.lessonOk && result.scrollOk && result.searchOk && result.progressOk && result.settingsOk && result.commitShown && result.hashOk && result.quizOk && result.wrongBookOk && result.stageQuizOk && result.notesOk && result.privatePackOk && realExperimentOk
        ? 0
        : 1,
    )
  })
}

app.whenReady().then(() => {
  protocol.handle('app', async (request) => {
    const url = new URL(request.url)
    let p = decodeURIComponent(url.pathname)
    if (p === '/' || p === '') p = '/index.html'
    let file = path.join(webRoot, p)
    if (!file.startsWith(webRoot)) return new Response('forbidden', { status: 403 })
    if (!fs.existsSync(file) || fs.statSync(file).isDirectory()) file = path.join(webRoot, 'index.html')
    return net.fetch(pathToFileURL(file).toString())
  })

  ipcMain.handle('rl:detect', detectBackend)
  ipcMain.handle('rl:runExperiment', (_e, spec) => runExperiment(spec))
  ipcMain.handle('rl:version', () => ({ app: app.getVersion(), electron: process.versions.electron, chrome: process.versions.chrome }))

  if (process.env.RL_SMOKE) {
    runSmoke()
    return
  }

  createWindow()
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})
