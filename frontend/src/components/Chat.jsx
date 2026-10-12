import { useEffect, useRef, useState } from 'react'
import { queryCopilot } from '../api'

const quickActions = [
  { label: 'Generate CR', action: 'generate_cr', prompt: 'Generate a change request draft.' },
  { label: 'Generate RCA', action: 'generate_rca', prompt: 'Generate a root cause analysis draft.' },
]

function cleanAssistantText(value) {
  return String(value || '')
    .replace(/\s*\[source:[^\]]+\]/gi, '')
    .replace(/\*\*/g, '')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

function MessageText({ text }) {
  const lines = String(text || '').split('\n')
  return <div className="space-y-1.5 whitespace-pre-wrap">
    {lines.map((line, index) => {
      const trimmed = line.trim()
      const isHeading = trimmed && !/^\d+\.\s|^[•-]\s/.test(trimmed) && !/[.:]$/.test(trimmed) && trimmed.length < 64
      return isHeading
        ? <p key={`${line}-${index}`} className="pt-2 text-xs font-bold uppercase tracking-[0.12em] text-sky-300 first:pt-0">{trimmed}</p>
        : <p key={`${line}-${index}`} className="min-h-4">{line || ' '}</p>
    })}
  </div>
}

function InlineStatsVisual({ chartData }) {
  if (!chartData) return null
  const metrics = Array.isArray(chartData.metrics) ? chartData.metrics : []
  const charts = Array.isArray(chartData.charts) ? chartData.charts : []

  return <section className="mt-4 border-t border-slate-700/80 pt-4" aria-label={chartData.title || 'Live dashboard metrics'}>
    <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-sky-300">{chartData.title}</p>
    {metrics.length > 0 && <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      {metrics.map((metric) => <div key={metric.label} className="rounded-lg border border-slate-700 bg-slate-950/35 px-3 py-2.5">
        <p className="text-[11px] font-medium text-slate-400">{metric.label}</p>
        <p className="mt-1 text-xl font-semibold" style={{ color: metric.color || '#e2e8f0' }}>{metric.value}</p>
      </div>)}
    </div>}
    <div className="mt-4 grid gap-4 sm:grid-cols-2">
      {charts.map((chart) => {
        const data = Array.isArray(chart.data) ? chart.data : []
        const total = data.reduce((sum, item) => sum + Number(item.value || 0), 0)
        const maximum = Math.max(1, ...data.map((item) => Number(item.value || 0)))
        return <div key={chart.title} className="rounded-lg border border-slate-700 bg-slate-950/25 p-3">
          <p className="mb-3 text-xs font-semibold text-slate-200">{chart.title}</p>
          <div className="space-y-2.5">
            {data.map((item) => {
              const value = Number(item.value || 0)
              const share = total ? Math.round((value / total) * 100) : 0
              return <div key={item.label} className="group relative">
                <div className="mb-1 flex items-center justify-between gap-3 text-[11px] text-slate-400"><span className="truncate">{item.label}</span><span className="font-mono text-slate-200">{value}</span></div>
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

export default function Chat() {
  const [messages, setMessages] = useState([{ role: 'assistant', text: 'I am ATLAS Co-Pilot. Ask about the current ITSM workload or generate a CR/RCA draft.' }])
  const [message, setMessage] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const transcriptRef = useRef(null)

  useEffect(() => {
    const transcript = transcriptRef.current
    if (transcript) transcript.scrollTop = transcript.scrollHeight
  }, [messages, sending])

  async function submit(event, action = 'chat', preset) {
    event?.preventDefault()
    const text = preset || message.trim()
    if (!text || sending) return
    setMessages((current) => [...current, { role: 'user', text }])
    setMessage(''); setError(''); setSending(true)
    try {
      const history = [...messages, { role: 'user', text }]
        .slice(-10)
        .map((item) => ({ role: item.role, text: item.text }))
      const result = await queryCopilot({ message: text, action, history })
      setMessages((current) => [...current, {
        role: 'assistant',
        text: cleanAssistantText(result.response),
        chartData: result.chart_data || null,
      }])
    } catch (requestError) { setError(requestError.message) }
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
    <div className="mt-6 flex flex-wrap gap-3">{quickActions.map((item) => <button key={item.action} type="button" disabled={sending} onClick={(event) => submit(event, item.action, item.prompt)} className="rounded-lg border border-teal-400/50 bg-teal-500/10 px-4 py-2 text-sm font-semibold text-teal-100 hover:bg-teal-500/20 disabled:opacity-50">{item.label}</button>)}</div>
    <div ref={transcriptRef} className="custom-scrollbar mt-6 min-h-0 flex-1 space-y-4 overflow-y-auto rounded-2xl border border-slate-700 bg-slate-900/70 p-6 pr-4" aria-live="polite">{messages.map((item, index) => <div key={`${item.role}-${index}`} className={`max-w-5xl rounded-xl px-5 py-4 text-sm leading-6 ${item.role === 'user' ? 'ml-auto bg-cyan-500 text-slate-950' : 'bg-slate-800 text-slate-200'}`}><MessageText text={item.text} />{item.role === 'assistant' && <InlineStatsVisual chartData={item.chartData} />}</div>)}{sending && <p className="text-sm text-slate-400">ATLAS is drafting a response…</p>}</div>
    {error && <p className="mt-3 text-sm text-rose-300" role="alert">Unable to query co-pilot: {error}</p>}
    <form onSubmit={submit} className="mt-5 flex items-end gap-3"><textarea rows="2" value={message} onKeyDown={handleComposerKeyDown} onChange={(event) => setMessage(event.target.value)} placeholder="Ask a question about the ITSM queue…" className="min-h-[3.25rem] min-w-0 flex-1 resize-y rounded-xl border border-slate-600 bg-slate-900 px-4 py-3 outline-none placeholder:text-slate-500 focus:border-teal-400" /><button disabled={sending} className="monday-primary rounded-xl px-5 py-3 font-semibold disabled:opacity-60">Send</button></form>
  </section>
}
