import { useState } from 'react'
import { queryCopilot } from '../api'
import KnowledgeReferences from './KnowledgeReferences'
import TopologyTree from './TopologyTree'

export default function TicketCard({ ticket, onClose }) {
  const [question, setQuestion] = useState('')
  const [reply, setReply] = useState('')
  const [chatError, setChatError] = useState('')
  const [isSending, setIsSending] = useState(false)

  async function sendInlineChat(event) {
    event.preventDefault()
    if (!question.trim()) return
    setIsSending(true); setChatError('')
    try { const result = await queryCopilot({ message: question, ticketId: ticket.number || ticket.id }); setReply(result.response); setQuestion('') }
    catch (error) { setChatError(error.message) } finally { setIsSending(false) }
  }

  return <article className="h-full overflow-y-auto bg-slate-900 p-6 text-slate-100"><div className="mb-6 flex items-start justify-between gap-4"><div><p className="font-mono text-sm text-cyan-300">{ticket.number || ticket.id} · {ticket.type}</p><h2 className="mt-1 text-xl font-semibold">{ticket.title}</h2><p className="mt-2 text-sm text-slate-400">{ticket.description}</p></div>{onClose && <button type="button" onClick={onClose} className="rounded-lg border border-slate-600 px-3 py-1.5 text-sm hover:bg-slate-800">Close</button>}</div><div className="space-y-4"><section className="rounded-xl border border-cyan-500/30 bg-cyan-950/20 p-4"><h3 className="text-sm font-semibold text-cyan-100">AI Solution / Resolution Breakdown</h3><p className="mt-2 text-sm leading-6 text-slate-300">{ticket.ai_resolution_guide}</p></section><TopologyTree ticket={ticket} /><section className="rounded-xl border border-slate-700 p-4"><h3 className="text-sm font-semibold">Work notes</h3><ul className="mt-2 space-y-2 text-sm leading-6 text-slate-400">{(ticket.work_notes || [ticket.latest_work_notes]).map((note, index) => <li key={`${note}-${index}`}>• {note}</li>)}</ul></section><section className="rounded-xl border border-slate-700 p-4"><h3 className="text-sm font-semibold">Closure notes</h3><p className="mt-2 text-sm leading-6 text-slate-400">{ticket.close_notes || ticket.closure_notes || 'No closure notes recorded.'}</p></section><KnowledgeReferences references={ticket.knowledge_refs} /><section className="rounded-xl border border-cyan-500/30 bg-cyan-950/20 p-4"><h3 className="text-sm font-semibold text-cyan-100">Ask about this ticket</h3><form onSubmit={sendInlineChat} className="mt-3 flex gap-2"><input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask for the current status…" className="min-w-0 flex-1 rounded-lg border border-slate-600 bg-slate-950 px-3 py-2 text-sm outline-none placeholder:text-slate-500 focus:border-cyan-400" /><button disabled={isSending} className="rounded-lg bg-cyan-500 px-3 py-2 text-sm font-semibold text-slate-950 disabled:opacity-60">{isSending ? 'Asking…' : 'Ask'}</button></form>{chatError && <p className="mt-2 text-xs text-rose-300">{chatError}</p>}{reply && <p className="mt-3 rounded-lg bg-slate-950/70 p-3 text-sm leading-6 text-slate-300">{reply}</p>}</section></div></article>
}
