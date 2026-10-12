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
      }])
    } catch (requestError) { setError(requestError.message) }
    finally { setSending(false) }
  }

  return <section className="mx-auto flex h-[calc(100vh-6rem)] min-h-[38rem] max-w-5xl flex-col px-4 py-8 sm:px-6">
    <div><p className="text-sm font-semibold uppercase tracking-[0.2em] text-teal-300">Conversational operations</p><h1 className="mt-2 text-3xl font-bold">ATLAS Co-Pilot</h1><p className="mt-2 text-slate-400">Turn the current incident context into clear operational next steps.</p></div>
    <div className="mt-6 flex flex-wrap gap-3">{quickActions.map((item) => <button key={item.action} type="button" disabled={sending} onClick={(event) => submit(event, item.action, item.prompt)} className="rounded-lg border border-teal-400/50 bg-teal-500/10 px-4 py-2 text-sm font-semibold text-teal-100 hover:bg-teal-500/20 disabled:opacity-50">{item.label}</button>)}</div>
    <div ref={transcriptRef} className="custom-scrollbar mt-6 min-h-0 flex-1 space-y-4 overflow-y-auto rounded-2xl border border-slate-700 bg-slate-900/70 p-5 pr-3" aria-live="polite">{messages.map((item, index) => <div key={`${item.role}-${index}`} className={`max-w-3xl rounded-xl px-4 py-3 text-sm leading-6 ${item.role === 'user' ? 'ml-auto bg-cyan-500 text-slate-950' : 'bg-slate-800 text-slate-200'}`}><MessageText text={item.text} /></div>)}{sending && <p className="text-sm text-slate-400">ATLAS is drafting a response…</p>}</div>
    {error && <p className="mt-3 text-sm text-rose-300" role="alert">Unable to query co-pilot: {error}</p>}
    <form onSubmit={submit} className="mt-5 flex gap-3"><input value={message} onChange={(event) => setMessage(event.target.value)} placeholder="Ask a question about the ITSM queue…" className="min-w-0 flex-1 rounded-xl border border-slate-600 bg-slate-900 px-4 py-3 outline-none placeholder:text-slate-500 focus:border-teal-400" /><button disabled={sending} className="monday-primary rounded-xl px-5 py-3 font-semibold disabled:opacity-60">Send</button></form>
  </section>
}
