import { create } from 'zustand'
import {
  getAllProgress,
  getSetting,
  listPrivatePacks,
  loadPackFromUrl,
  setPlatformAdapter,
  type ContentPack,
  type Progress,
  type PlatformAdapter,
} from '@rl/core'

interface AppState {
  pack: ContentPack | null
  privatePacks: ContentPack[]
  activePackId: string
  progress: Record<string, Progress>
  loading: boolean
  error: string
  platform: string
  backend: string
  load: () => Promise<void>
  refresh: () => Promise<void>
  switchPack: (id: string) => Promise<void>
}

export const useApp = create<AppState>((set, get) => ({
  pack: null,
  privatePacks: [],
  activePackId: 'rl.public.core',
  progress: {},
  loading: true,
  error: '',
  platform: 'web',
  backend: 'read-only',

  async load() {
    try {
      const injected = (window as unknown as { __RL_PLATFORM__?: PlatformAdapter }).__RL_PLATFORM__
      if (injected) {
        setPlatformAdapter(injected)
        set({ platform: injected.name })
        injected.detectBackend().then((b) => set({ backend: b })).catch(() => {})
      }

      const builtin = await loadPackFromUrl('./content/pack.json')
      const privates = (await listPrivatePacks()) as ContentPack[]
      const activePackId = (await getSetting<string>('activePackId', builtin.manifest.id)) ?? builtin.manifest.id

      let pack = builtin
      if (activePackId !== builtin.manifest.id) {
        const p = privates.find((x) => x?.manifest?.id === activePackId)
        if (p) pack = p
      }

      const rows = await getAllProgress()
      const progress: Record<string, Progress> = {}
      for (const r of rows) progress[r.lessonId] = r

      set({ pack, privatePacks: privates, activePackId: pack.manifest.id, progress, loading: false })
    } catch (e) {
      set({ loading: false, error: e instanceof Error ? e.message : String(e) })
    }
  },

  async refresh() {
    const rows = await getAllProgress()
    const progress: Record<string, Progress> = {}
    for (const r of rows) progress[r.lessonId] = r
    const privates = (await listPrivatePacks()) as ContentPack[]
    set({ progress, privatePacks: privates })
  },

  async switchPack(id: string) {
    const { privatePacks } = get()
    const builtin = await loadPackFromUrl('./content/pack.json')
    const pack = id === builtin.manifest.id ? builtin : privatePacks.find((p) => p?.manifest?.id === id)
    if (!pack) return
    await (await import('@rl/core')).setSetting('activePackId', id)
    set({ pack, activePackId: id })
  },
}))
