import { useState } from 'react'
import { addQuizResult, gradeQuiz, makeQuizResult, type QuizQuestion } from '@rl/core'
import { useApp } from '../store'

export default function Quiz({ lessonId, quiz }: { lessonId: string; quiz: QuizQuestion[] }) {
  const { refresh } = useApp()
  const [answers, setAnswers] = useState<number[]>(quiz.map(() => -1))
  const [submitted, setSubmitted] = useState(false)
  const [outcome, setOutcome] = useState<ReturnType<typeof gradeQuiz> | null>(null)

  if (!quiz.length) {
    return <div className="card"><p className="muted">本节测验尚未编写（课程骨架阶段）。</p></div>
  }

  async function submit() {
    const out = gradeQuiz(quiz, answers)
    setOutcome(out)
    setSubmitted(true)
    await addQuizResult(makeQuizResult(lessonId, answers, out))
    await refresh()
  }

  return (
    <div className="quiz">
      {quiz.map((q, qi) => (
        <div key={qi} className="card question">
          <div className="q-head">第 {qi + 1} 题</div>
          <p className="q-text">{q.q}</p>
          <div className="options">
            {q.options.map((o, oi) => {
              const chosen = answers[qi] === oi
              const correct = submitted && oi === q.answer
              const wrong = submitted && chosen && oi !== q.answer
              return (
                <label key={oi} className={`option ${chosen ? 'chosen' : ''} ${correct ? 'correct' : ''} ${wrong ? 'wrong' : ''}`}>
                  <input
                    type="radio"
                    name={`${lessonId}-${qi}`}
                    checked={chosen}
                    disabled={submitted}
                    onChange={() => setAnswers((a) => a.map((v, i) => (i === qi ? oi : v)))}
                  />
                  <span>{String.fromCharCode(65 + oi)}. {o}</span>
                </label>
              )
            })}
          </div>
          {submitted && outcome?.details[qi] && (
            <div className={`explain ${outcome.details[qi].ok ? 'ok' : 'bad'}`}>
              {outcome.details[qi].ok ? '正确' : `正确答案：${String.fromCharCode(65 + q.answer)}`}
              {q.explain && <p>{q.explain}</p>}
            </div>
          )}
        </div>
      ))}
      {!submitted ? (
        <button className="btn primary" disabled={answers.some((a) => a < 0)} onClick={submit}>
          提交答案
        </button>
      ) : (
        <div className="card">
          <h3>得分 {outcome?.correct} / {outcome?.total}</h3>
          <p className="muted">已加入间隔重复队列：满分 7 天后复习，60% 以上 3 天后，低于 60% 明天再来。</p>
          <button
            className="btn"
            onClick={() => {
              setAnswers(quiz.map(() => -1))
              setSubmitted(false)
              setOutcome(null)
            }}
          >
            重做
          </button>
        </div>
      )}
    </div>
  )
}
