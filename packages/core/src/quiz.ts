import type { QuizQuestion, QuizResult } from './types'

export interface GradeOutcome {
  correct: number
  total: number
  details: { q: string; ok: boolean; chosen: number; answer: number; explain?: string }[]
}

export function gradeQuiz(quiz: QuizQuestion[], answers: number[]): GradeOutcome {
  const details = quiz.map((q, i) => ({
    q: q.q,
    ok: answers[i] === q.answer,
    chosen: answers[i] ?? -1,
    answer: q.answer,
    explain: q.explain,
  }))
  return { correct: details.filter((d) => d.ok).length, total: quiz.length, details }
}

// SM-2 简化版：满分 7 天，60%–99% 3 天，<60% 1 天
export function nextReview(result: { correct: number; total: number; ease?: number }, now = Date.now()): {
  nextReviewAt: number
  intervalDays: number
  ease: number
} {
  const ratio = result.total ? result.correct / result.total : 0
  const ease = Math.max(1.3, Math.min(2.8, (result.ease ?? 2.1) + (ratio >= 0.8 ? 0.1 : -0.2)))
  const intervalDays = ratio >= 0.999 ? Math.round(7 * ease) : ratio >= 0.6 ? 3 : 1
  return { nextReviewAt: now + intervalDays * 86400000, intervalDays, ease }
}

export function makeQuizResult(lessonId: string, answers: number[], out: GradeOutcome): QuizResult {
  const sched = nextReview(out)
  return {
    id: `${lessonId}-${Date.now()}`,
    lessonId,
    answers,
    correct: out.correct,
    total: out.total,
    at: Date.now(),
    ...sched,
  }
}

export function latestQuizResults(results: QuizResult[]): QuizResult[] {
  const latest = new Map<string, QuizResult>()
  for (const r of results) {
    const cur = latest.get(r.lessonId)
    if (!cur || r.at > cur.at) latest.set(r.lessonId, r)
  }
  return [...latest.values()]
}

export function dueReviews(results: QuizResult[], now = Date.now()): QuizResult[] {
  return latestQuizResults(results).filter((r) => r.nextReviewAt <= now).sort((a, b) => a.nextReviewAt - b.nextReviewAt)
}
