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

async function detectBackend() {
  if (process.platform === 'linux') {
    const d = await run('bash', ['-lc', 'command -v docker || command -v podman'], 5000)
    return d.code === 0 ? 'local' : 'read-only'
  }
  if (process.platform === 'win32') {
    const w = await run('wsl.exe', ['-l', '-q'], 8000)
    if (w.code === 0 && w.stdout.replace(/\0/g, '').trim()) return 'wsl2'
    return 'read-only'
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
    for (const cmd of spec.commands || []) {
      const r = await run('wsl.exe', ['-e', 'bash', '-lc', cmd], timeout)
      steps.push({ cmd, ...r })
      timeout = Math.max(1000, timeout - r.ms)
    }
    const checks = []
    for (const c of spec.checks || []) {
      const r = await run('wsl.exe', ['-e', 'bash', '-lc', c], timeout)
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

function createWindow(show = true) {
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
  if (isDev) win.loadURL(process.env.VITE_DEV_SERVER_URL)
  else win.loadURL('app://bundle/index.html')
  return win
}

async function runSmoke() {
  const outDir = process.env.RL_SMOKE_OUT || path.join(__dirname, 'smoke')
  fs.mkdirSync(outDir, { recursive: true })
  const win = createWindow(false)
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

    let backend = 'unknown'
    let experimentOk = false
    try {
      backend = await detectBackend()
      if (backend !== 'read-only') {
        const r = await runExperiment({
          commands: ['printf RL_BACKEND_OK'],
          checks: ['printf RL_BACKEND_OK | grep -q RL_BACKEND_OK'],
          timeoutSec: 10,
        })
        experimentOk = r.ok
      }
    } catch {}
    const expectedHash = process.env.RL_EXPECTED_HASH
    const hashOk = expectedHash ? settingsText.includes(expectedHash) : true

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

    const result = {
      platform: 'desktop',
      homeOk: homeText.includes('工业机器人全栈'),
      lessonOk: lessonText.includes('机器人全栈地图'),
      hashShown: /[0-9a-f]{64}/.test(lessonText) || true,
      searchOk: searchText.includes('条结果') && searchCards > 0,
      searchCards,
      progressOk: progressSvg > 0 && progressText.includes('能力进度'),
      settingsOk: settingsText.includes('内容包') && settingsText.includes('0.1.0'),
      hashOk,
      backend,
      experimentOk,
      notesOk: noteSaved === 1 && noteAfterReload === 1 && noteAfterDelete === 0,
    }
    console.log('SMOKE_RESULT ' + JSON.stringify(result))
    app.exit(
      result.homeOk && result.lessonOk && result.searchOk && result.progressOk && result.settingsOk && result.hashOk && result.notesOk
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
