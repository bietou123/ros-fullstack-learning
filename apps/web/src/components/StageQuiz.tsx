import { useCallback, useEffect, useMemo, useState } from 'react'
import { listQuizResults, type LessonMeta, type QuizQuestion, type QuizResult } from '@rl/core'
import Quiz from './Quiz'

const PER_STAGE = 5

function pick(lessons: LessonMeta[]): QuizQuestion[] {
  const pool = lessons.flatMap((l) => l.quiz.map((q) => ({ ...q, q: `${l.id} · ${q.q}` })))
  if (pool.length <= PER_STAGE) return pool
  const step = pool.length / PER_STAGE
  return Array.from({ length: PER_STAGE }, (_, i) => pool[Math.floor(i * step)])
}

export default function StageQuiz({ stageId, lessons }: { stageId: string; lessons: LessonMeta[] }) {
  const quiz = useMemo(() => pick(lessons), [lessons])
  const [last, setLast] = useState<QuizResult | null>(null)

  const loadLast = useCallback(() => {
    listQuizResults().then((rows) => {
      const mine = rows
        .filter((r) => r.lessonId === stageId && r.kind === 'stage')
        .sort((a, b) => b.at - a.at)
      setLast(mine[0] ?? null)
    })
  }, [stageId])

  useEffect(loadLast, [loadLast])

  return (
    <section className="stage-quiz">
      <h2 className="section-title">阶段测验</h2>
      <p className="muted">
        从本阶段各课测验中抽取 {quiz.length} 题，检查阶段掌握程度；不计入课程错题本与间隔重复。
        {last && ` 上次得分 ${last.correct}/${last.total}（${new Date(last.at).toLocaleString('zh-CN')}）。`}
      </p>
      <Quiz lessonId={stageId} quiz={quiz} kind="stage" onSubmitted={loadLast} />
    </section>
  )
}
