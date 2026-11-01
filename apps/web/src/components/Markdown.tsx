import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import type { Components } from 'react-markdown'
import type { LanguageInput } from 'shiki/core'

const LANG_MAP: Record<string, string> = {
  sh: 'bash', shell: 'bash', console: 'bash', zsh: 'bash',
  py: 'python', 'c++': 'cpp', ts: 'typescript', js: 'javascript',
  yml: 'yaml', text: 'text', txt: 'text',
}

let hlPromise: Promise<unknown> | null = null

async function highlight(code: string, lang: string): Promise<string> {
  try {
    if (!hlPromise) {
      hlPromise = (async () => {
        const [{ createHighlighterCore }, { createOnigurumaEngine }, theme, ...langs] = await Promise.all([
          import('shiki/core'),
          import('shiki/engine/oniguruma'),
          import('shiki/themes/github-dark.mjs'),
          import('shiki/langs/bash.mjs'),
          import('shiki/langs/python.mjs'),
          import('shiki/langs/cpp.mjs'),
          import('shiki/langs/yaml.mjs'),
          import('shiki/langs/json.mjs'),
          import('shiki/langs/typescript.mjs'),
          import('shiki/langs/javascript.mjs'),
          import('shiki/langs/xml.mjs'),
          import('shiki/langs/cmake.mjs'),
          import('shiki/langs/ini.mjs'),
          import('shiki/langs/diff.mjs'),
        ])
        return createHighlighterCore({
          themes: [theme.default],
          langs: langs.map((l) => (l as { default: LanguageInput }).default),
          engine: createOnigurumaEngine(import('shiki/wasm')),
        })
      })()
    }
    const hl = (await hlPromise) as { codeToHtml: (c: string, o: unknown) => string; getLoadedLanguages: () => string[] }
    const l = LANG_MAP[lang] ?? lang
    const safe = hl.getLoadedLanguages().includes(l) ? l : 'text'
    return hl.codeToHtml(code, { lang: safe, theme: 'github-dark' })
  } catch {
    return ''
  }
}

function CodeBlock({ code, lang }: { code: string; lang: string }) {
  const [html, setHtml] = useState('')
  useEffect(() => {
    let alive = true
    highlight(code, lang).then((h) => alive && setHtml(h))
    return () => {
      alive = false
    }
  }, [code, lang])
  return (
    <div className="codeblock">
      <div className="code-head">
        <span>{lang || 'text'}</span>
        <button onClick={() => navigator.clipboard?.writeText(code)}>复制</button>
      </div>
      {html ? <div className="shiki" dangerouslySetInnerHTML={{ __html: html }} /> : <pre><code>{code}</code></pre>}
    </div>
  )
}

const components: Components = {
  code(props) {
    const { className, children } = props
    const text = String(children ?? '').replace(/\n$/, '')
    const m = /language-([\w+-]+)/.exec(className ?? '')
    if (m || text.includes('\n')) return <CodeBlock code={text} lang={m?.[1] ?? 'text'} />
    return <code className="inline-code">{children}</code>
  },
  table(props) {
    return (
      <div className="table-wrap">
        <table {...props} />
      </div>
    )
  },
  a(props) {
    const href = props.href ?? ''
    if (href.startsWith('#')) return <a {...props} />
    return <a {...props} target="_blank" rel="noreferrer" />
  },
}

export default function Markdown({ children }: { children: string }) {
  return (
    <div className="md">
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]} components={components}>
        {children}
      </ReactMarkdown>
    </div>
  )
}
