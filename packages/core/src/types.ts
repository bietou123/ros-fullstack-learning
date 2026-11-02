export interface QuizQuestion {
  q: string
  options: string[]
  answer: number
  explain?: string
}

export interface LessonMeta {
  id: string
  stage: string
  title: string
  durationMin: number
  type: 'teach' | 'read' | 'field'
  output: string
  tags: string[]
  sources: string[]
  experiment: ExperimentSpec | null
  quiz: QuizQuestion[]
  markdown: string
}

export interface Stage {
  id: string
  title: string
  desc: string
  lessons: string[]
}

export interface PackManifest {
  id: string
  version: string
  minAppVersion: string
  visibility: 'public' | 'private'
  builtAt: string
  hash: string
  lessonCount: number
  stageCount: number
}

export interface ContentPack {
  manifest: PackManifest
  stages: Stage[]
  lessons: LessonMeta[]
  glossary: { term: string; en?: string; def: string }[]
  coverage?: {
    total: number
    byStatus: Record<string, number>
    chapterLevel: Record<string, number>
  } | null
}

export type BackendKind = 'local' | 'wsl2' | 'ssh' | 'read-only'

export interface ExperimentSpec {
  id: string
  ros: 'ros1' | 'ros2' | 'none'
  image?: string
  commands: string[]
  checks: string[]
  expected?: string
  timeoutSec: number
  headless: boolean
}

export interface ExperimentResult {
  backend: BackendKind
  ok: boolean
  steps: { cmd: string; code: number; stdout: string; stderr: string; ms: number }[]
  checks: { name: string; ok: boolean; detail: string }[]
  reason?: 'no-backend' | 'timeout' | 'failed' | 'denied'
}

export interface Progress {
  lessonId: string
  status: 'new' | 'reading' | 'done'
  percent: number
  lastAt: number
  seconds: number
}

export interface Note {
  id: string
  lessonId: string
  text: string
  createdAt: number
  updatedAt: number
}

export interface QuizResult {
  id: string
  lessonId: string
  answers: number[]
  correct: number
  total: number
  at: number
  nextReviewAt: number
  intervalDays: number
  ease: number
  kind?: 'lesson' | 'stage'
}

export interface Bookmark {
  lessonId: string
  at: number
  label: string
}
