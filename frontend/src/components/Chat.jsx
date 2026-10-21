import { useEffect, useRef, useState } from 'react'
import { streamCopilot } from '../api'

const quickActions = [
  { label: 'SLA health', prompt: 'Show SLA health for ' },
  { label: 'At risk', prompt: 'Show at-risk tickets for ' },
]

function cleanAssistantText(value) {
  return String(value || '')
    .replace(/\s*\[source:[^\]]+\]/gi, '')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

function InlineMarkdown({ value }) {
  const parts = String(value || '').split(/(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^\s)]+\))/g)
  return parts.map((part, index) => {
    if (/^\*\*[^*]+\*\*$/.test(part)) return <strong key={index} className="font-semibold text-inherit">{part.slice(2, -2)}</strong>
    if (/^`[^`]+`$/.test(part)) return <code key={index} className="rounded bg-slate-950/40 px-1 py-0.5 font-mono text-[0.9em]">{part.slice(1, -1)}</code>
    const link = part.match(/^\[([^\]]+)\]\(([^\s)]+)\)$/)
    if (link) return <a key={index} href={link[2]} target="_blank" rel="noreferrer" className="text-sky-300 underline underline-offset-2 hover:text-sky-200">{link[1]}</a>
    return <span key={index}>{part}</span>
  })
}

function MessageText({ text }) {
  const lines = String(text || '').split('\n')
  return <div className="space-y-1.5 whitespace-pre-wrap">
    {lines.map((line, index) => {
      const trimmed = line.trim()
      const markdownHeading = trimmed.match(/^#{1,3}\s+(.+)/)
      const isHeading = markdownHeading || (trimmed && !/^\d+\.\s|^[•-]\s/.test(trimmed) && !/[.:]$/.test(trimmed) && trimmed.length < 64)
      return isHeading
        ? <p key={`${line}-${index}`} className="pt-2 text-xs font-bold uppercase tracking-[0.12em] text-sky-300 first:pt-0"><InlineMarkdown value={markdownHeading?.[1] || trimmed} /></p>
        : <p key={`${line}-${index}`} className="min-h-4"><InlineMarkdown value={line || ' '} /></p>
    })}
  </div>
}

function InlineStatsVisual({ chartData }) {
  if (!chartData || typeof chartData !== 'object') return null
  const metrics = Array.isArray(chartData.metrics) ? chartData.metrics : []
  const charts = Array.isArray(chartData.charts) ? chartData.charts : []

  return <section className="mt-4 border-t border-slate-700/80 pt-4" aria-label={chartData.title || 'Live dashboard metrics'}>
    <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-sky-300">{chartData.title}</p>
    {metrics.length > 0 && <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      {metrics.filter((metric) => metric && typeof metric === 'object').map((metric, index) => <div key={metric.label || index} className="rounded-lg border border-slate-700 bg-slate-950/35 px-3 py-2.5">
        <p className="text-[11px] font-medium text-slate-400">{metric.label ?? 'Metric'}</p>
        <p className="mt-1 text-xl font-semibold" style={{ color: metric.color || '#e2e8f0' }}>{metric.value ?? 0}</p>
      </div>)}
    </div>}
    <div className="mt-4 grid gap-4 sm:grid-cols-2">
      {charts.filter((chart) => chart && typeof chart === 'object').map((chart, chartIndex) => {
        const data = Array.isArray(chart.data) ? chart.data : []
        const points = data.filter((item) => item && typeof item === 'object')
        const total = points.reduce((sum, item) => sum + Number(item.value || 0), 0)
        const maximum = Math.max(1, ...points.map((item) => Number(item.value || 0)))
        return <div key={chart.title || chartIndex} className="rounded-lg border border-slate-700 bg-slate-950/25 p-3">
          <p className="mb-3 text-xs font-semibold text-slate-200">{chart.title || 'Live metric'}</p>
          <div className="space-y-2.5">
            {points.map((item, index) => {
              const value = Number(item.value || 0)
              const share = total ? Math.round((value / total) * 100) : 0
              return <div key={item.label || index} className="group relative">
                <div className="mb-1 flex items-center justify-between gap-3 text-[11px] text-slate-400"><span className="truncate">{item.label || 'Unlabelled'}</span><span className="font-mono text-slate-200">{value}</span></div>
                <div className="h-2 overflow-hidden rounded-full bg-slate-800"><div className="h-full rounded-full transition-all duration-500" style={{ width: `${(value / maximum) * 100}%`, backgroundColor: item.color || '#38bdf8' }} /></div>
                <span className="pointer-events-none absolute right-0 top-full z-10 mt-1 rounded bg-slate-950 px-2 py-1 text-[10px] text-slate-100 opacity-0 shadow-lg transition-opacity group-hover:opacity-100">{value} ticket{value === 1 ? '' : 's'} · {share}%</span>
              </div>
            })}
          </div>
        </div>
      })}
    </div>
  </section>
}

function WebResearchSources({ metadata }) {
  const sources = Array.isArray(metadata?.sources) ? metadata.sources : []
  const webSources = sources.filter((source) => source?.source_type === 'DuckDuckGo Web' && source?.url)
  if (!webSources.length) return null
  return <section className="mt-4 border-t border-slate-700/80 pt-3" aria-label="Web research sources"><p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-sky-300">Web research sources</p><ul className="mt-2 space-y-1.5">{webSources.map((source, index) => <li key={`${source.id || index}-${source.url}`} className="text-xs leading-5"><a href={source.url} target="_blank" rel="noreferrer" className="text-cyan-300 underline underline-offset-2 hover:text-cyan-200">{source.title || source.url} ↗</a></li>)}</ul></section>
}

export default function Chat() {
  const [messages, setMessages] = useState([{ role: 'assistant', text: 'I am ATLAS Co-Pilot. Ask about the current ITSM workload, SLA health, or operational guidance.' }])
  const [message, setMessage] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const transcriptRef = useRef(null)
  const composerRef = useRef(null)
  const pendingTokensRef = useRef({})
  const tokenFrameRef = useRef(null)
  const shouldAutoScrollRef = useRef(true)

  useEffect(() => {
    const transcript = transcriptRef.current
    if (transcript && shouldAutoScrollRef.current) transcript.scrollTop = transcript.scrollHeight
  }, [messages, sending])

  useEffect(() => () => {
    if (tokenFrameRef.current !== null) cancelAnimationFrame(tokenFrameRef.current)
  }, [])

  function flushPendingTokens() {
    if (tokenFrameRef.current !== null) {
      cancelAnimationFrame(tokenFrameRef.current)
      tokenFrameRef.current = null
    }
    const pending = pendingTokensRef.current
    pendingTokensRef.current = {}
    if (!Object.keys(pending).length) return
    setMessages((current) => current.map((item) => pending[item.id]
      ? { ...item, text: `${item.text || ''}${pending[item.id]}` }
      : item))
  }

  function appendStreamToken(assistantId, content) {
    if (!content) return
    pendingTokensRef.current[assistantId] = `${pendingTokensRef.current[assistantId] || ''}${content}`
    if (tokenFrameRef.current !== null) return
    tokenFrameRef.current = requestAnimationFrame(() => flushPendingTokens())
  }

  function prefillPrompt(prompt) {
    setMessage(prompt)
    requestAnimationFrame(() => composerRef.current?.focus())
  }

  function handleTranscriptScroll(event) {
    const { scrollTop, scrollHeight, clientHeight } = event.currentTarget
    // Continue following streamed tokens only while the reader remains at the
    // live edge. Scrolling upward deliberately releases that lock.
    shouldAutoScrollRef.current = scrollHeight - scrollTop - clientHeight < 56
  }

  async function submit(event, action = 'chat', preset) {
    event?.preventDefault()
    const text = preset || message.trim()
    if (!text || sending) return
    const assistantId = `stream-${Date.now()}-${Math.random().toString(36).slice(2)}`
    shouldAutoScrollRef.current = true
    setMessages((current) => [...current, { role: 'user', text }, { id: assistantId, role: 'assistant', text: '', streaming: true }])
    setMessage(''); setError(''); setSending(true)
    try {
      const history = [...(Array.isArray(messages) ? messages : []), { role: 'user', text }]
        .slice(-6)
        .filter((item) => item && typeof item === 'object')
        .map((item) => ({ role: item.role || 'user', text: item.text || '' }))
      await streamCopilot({ message: text, action, history, onEvent: ({ event: eventName, payload }) => {
        if (eventName === 'metadata') {
          setMessages((current) => current.map((item) => item.id === assistantId ? {
            ...item,
            metadata: payload,
            chartData: payload?.chart_data ?? null,
            streamStatus: 'Grounded context ready. Generating the response…',
          } : item))
        } else if (eventName === 'token') {
          appendStreamToken(assistantId, payload?.content || '')
        } else if (eventName === 'error') {
          setError(payload?.message || 'ATLAS encountered a generation problem; grounded fallback guidance is being used.')
        } else if (eventName === 'done') {
          flushPendingTokens()
          setMessages((current) => current.map((item) => item.id === assistantId ? {
            ...item,
            text: cleanAssistantText(item.text) || 'ATLAS could not find a usable response for that request.',
            streaming: false,
            streamStatus: null,
            modelUsed: payload?.model_used || null,
          } : item))
        }
      } })
    } catch (requestError) {
      flushPendingTokens()
      const messageText = requestError?.message || 'The co-pilot request could not be completed.'
      setError(messageText)
      setMessages((current) => current.map((item) => item.id === assistantId ? {
        ...item,
        text: item.text || 'ATLAS could not complete this response. Please try again.',
        streaming: false,
      } : item))
    }
    finally { setSending(false) }
  }

  function handleComposerKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submit(event)
    }
  }

  return <section className="mx-auto flex h-[calc(100vh-5rem)] min-h-[680px] max-w-7xl flex-col px-4 py-8 sm:px-6">
    <div><p className="text-sm font-semibold uppercase tracking-[0.2em] text-teal-300">Conversational operations</p><h1 className="mt-2 text-3xl font-bold">ATLAS Co-Pilot</h1><p className="mt-2 text-slate-400">Turn the current incident context into clear operational next steps.</p></div>
    <div className="mt-6 flex flex-wrap gap-3">{quickActions.map((item) => <button key={item.label} type="button" disabled={sending} onClick={() => prefillPrompt(item.prompt)} className="rounded-lg border border-teal-400/50 bg-teal-500/10 px-4 py-2 text-sm font-semibold text-teal-100 hover:bg-teal-500/20 disabled:opacity-50">{item.label}</button>)}</div>
    <div ref={transcriptRef} onScroll={handleTranscriptScroll} className="custom-scrollbar mt-6 min-h-0 flex-1 space-y-4 overflow-y-auto rounded-2xl border border-slate-700 bg-slate-900/70 p-6 pr-4" aria-live="polite">{messages.map((item, index) => <div key={item.id || `${item.role}-${index}`} className={`max-w-5xl rounded-xl px-5 py-4 text-sm leading-6 ${item.role === 'user' ? 'ml-auto bg-cyan-500 text-slate-950' : 'bg-slate-800 text-slate-200'}`}><MessageText text={item.text} />{item.streaming && !item.text && <p className="mt-2 text-xs text-slate-400">{item.streamStatus || 'ATLAS is grounding the request…'}</p>}{item.role === 'assistant' && <InlineStatsVisual chartData={item.chartData} />}{item.role === 'assistant' && <WebResearchSources metadata={item.metadata} />}</div>)}{sending && <p className="text-sm text-slate-400">ATLAS is drafting a response…</p>}</div>
    {error && <p className="mt-3 text-sm text-rose-300" role="alert">Unable to query co-pilot: {error}</p>}
    <form onSubmit={submit} className="mt-5 flex items-end gap-3"><textarea ref={composerRef} rows="2" value={message} onKeyDown={handleComposerKeyDown} onChange={(event) => setMessage(event.target.value)} placeholder="Ask a question about the ITSM queue…" className="min-h-[3.25rem] min-w-0 flex-1 resize-y rounded-xl border border-slate-500 bg-slate-950 px-4 py-3 text-slate-100 caret-cyan-300 outline-none placeholder:text-slate-400 focus:border-teal-400 focus:bg-slate-900" /><button disabled={sending} className="monday-primary rounded-xl px-5 py-3 font-semibold disabled:opacity-60">Send</button></form>
  </section>
}
