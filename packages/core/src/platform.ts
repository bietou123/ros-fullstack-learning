import type { BackendKind, ExperimentResult, ExperimentSpec } from './types'

export interface PlatformAdapter {
  name: 'web' | 'desktop' | 'mobile'
  detectBackend(): Promise<BackendKind>
  runExperiment(spec: ExperimentSpec): Promise<ExperimentResult>
  pickTextFile?(accept: string): Promise<string | null>
  saveTextFile?(name: string, content: string): Promise<boolean>
}

export const readOnlyAdapter: PlatformAdapter = {
  name: 'web',
  async detectBackend() {
    return 'read-only'
  },
  async runExperiment(spec) {
    return {
      backend: 'read-only',
      ok: false,
      reason: 'no-backend',
      steps: spec.commands.map((cmd) => ({ cmd, code: -1, stdout: '', stderr: '当前设备没有可用的 Linux 后端', ms: 0 })),
      checks: spec.checks.map((name) => ({ name, ok: false, detail: '未执行' })),
    }
  },
}

let adapter: PlatformAdapter = readOnlyAdapter

export function setPlatformAdapter(a: PlatformAdapter) {
  adapter = a
}

export function getPlatform(): PlatformAdapter {
  return adapter
}

export async function detectBackend(): Promise<BackendKind> {
  try {
    return await adapter.detectBackend()
  } catch {
    return 'read-only'
  }
}

export async function runExperiment(spec: ExperimentSpec): Promise<ExperimentResult> {
  try {
    return await adapter.runExperiment(spec)
  } catch (e) {
    return {
      backend: 'read-only',
      ok: false,
      reason: 'failed',
      steps: [],
      checks: [],
    }
  }
}
