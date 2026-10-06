import { useEffect, useState } from 'react'
import { fetchTicket } from '../api'

const stateStyles = {
  Pending: 'bg-slate-700 text-slate-200', Open: 'bg-cyan-500/15 text-cyan-200', 'In Progress': 'bg-cyan-500/15 text-cyan-200', 'Work in Progress': 'bg-cyan-500/15 text-cyan-200', New: 'bg-slate-700 text-slate-200', Assess: 'bg-indigo-500/15 text-indigo-200', Closed: 'bg-emerald-500/15 text-emerald-200', 'Closed Complete': 'bg-emerald-500/15 text-emerald-200', 'Closed Incomplete': 'bg-slate-700 text-slate-300', 'Closed Skipped': 'bg-slate-700 text-slate-300', Canceled: 'bg-slate-700 text-slate-300',
}

function journalValue(entry) { return typeof entry === 'string' ? entry : entry.value || entry.text }
function journalTime(entry) { return typeof entry === 'string' ? '' : entry.sys_created_on || entry.timestamp }
function newestFirst(entries) { return [...entries].sort((left, right) => journalTime(right).localeCompare(journalTime(left))) }
function isHumanJournalEntry(entry) { if (typeof entry === 'string') return true; const role = entry.role || ''; const author = entry.author || entry.sys_created_by || ''; return role !== 'System' && !author.toLowerCase().includes('system') && !author.toLowerCase().includes('atlas monitoring') }

export function PinnedAttachments({ attachments = [] }) {
  if (!attachments.length) return null
  return <section className="apple-attachments mb-4 rounded-lg border border-cyan-500/30 bg-cyan-950/20 p-3"><h3 className="apple-panel-title text-xs font-bold uppercase tracking-wider text-cyan-100">📎 Pinned Evidence &amp; Attachments</h3><div className="mt-3 flex flex-wrap gap-2">{attachments.map((attachment) => { const isPdf = attachment.content_type === 'application/pdf' || attachment.filename?.toLowerCase().endsWith('.pdf'); return <a key={`${attachment.filename}-${attachment.url}`} href={attachment.url} target="_blank" rel="noreferrer" className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold transition hover:bg-slate-800 ${isPdf ? 'border-rose-500/40 bg-rose-950/30 text-rose-100' : 'border-sky-500/40 bg-sky-950/30 text-sky-100'}`}><span aria-hidden="true">{isPdf ? '📄' : '🖼️'}</span><span>{attachment.filename}</span><span className="text-slate-400">{attachment.size}</span><span>{isPdf ? '📄 View PDF ↗' : '🖼️ View Image ↗'}</span></a> })}</div></section>
}

export function Journal({ comments = [] }) {
  const stream = newestFirst(comments.filter(isHumanJournalEntry))
  return <section className="apple-journal rounded-xl border border-indigo-400/40 bg-slate-950/50 p-4"><h3 className="apple-panel-title text-sm font-bold text-indigo-100">💬 Customer &amp; Support Journal <span className="apple-count">{stream.length}</span></h3><div className="apple-journal-stream max-h-64 overflow-y-auto pr-2 space-y-3 custom-scrollbar scrollbar-thin scrollbar-thumb-slate-700 scrollbar-track-transparent border border-slate-800/80 rounded-lg p-3 bg-slate-900/40 mt-4">{stream.length ? stream.map((comment, index) => { const customer = typeof comment !== 'string' && (comment.is_customer || comment.role === 'Requester'); const author = typeof comment === 'string' ? 'ServiceNow journal' : comment.author || comment.sys_created_by; return <article key={comment.id || comment.sys_id || `${journalValue(comment)}-${index}`} className="apple-journal-entry rounded-lg border border-slate-700 bg-slate-900/60 p-3"><div className="flex flex-wrap items-center justify-between gap-2"><span className={`rounded-full border px-2 py-1 text-xs font-semibold ${customer ? 'border-cyan-400/40 bg-cyan-500/10 text-cyan-100' : 'border-indigo-400/40 bg-indigo-500/10 text-indigo-100'}`}>{customer ? '👤 Requester' : '🎧 L2 Support'} · {author}</span><span className="text-xs text-slate-500">{journalTime(comment)}</span></div><p className="mt-3 text-sm leading-6 text-slate-300">{journalValue(comment)}</p></article> }) : <p className="text-sm text-slate-500">No human journal updates recorded.</p>}</div></section>
}

function ChildTicket({ incident }) {
  const [record, setRecord] = useState(null)
  const [loadError, setLoadError] = useState('')

  useEffect(() => {
    let active = true
    fetchTicket(incident.number)
      .then((result) => active && setRecord(result.ticket))
      .catch(() => active && setLoadError('Unable to load the current child journal.'))
    return () => { active = false }
  }, [incident.number])

  // Do not render comments copied into the parent payload. The child record
  // endpoint is the authoritative central-ticket lookup for this journal.
  const child = record || incident
  const comments = newestFirst((record?.comments || []).filter(isHumanJournalEntry))
  return <li className="apple-child-ticket rounded-lg bg-slate-950/60 p-3"><div className="flex items-center justify-between gap-3"><div><p className="font-mono text-xs text-cyan-300">{child.number}</p><p className="mt-1 text-sm text-slate-300">{child.short_description}</p></div><span className={`shrink-0 rounded-full px-2 py-1 text-xs font-semibold ${stateStyles[child.state] || stateStyles.Pending}`}>{child.state}</span></div>{!record && !loadError && <p className="mt-3 border-t border-slate-800 pt-3 text-xs text-slate-500">Loading current child journal…</p>}{loadError && <p className="mt-3 border-t border-slate-800 pt-3 text-xs text-rose-300">{loadError}</p>}{comments.length ? <div className="apple-child-stream mt-3 max-h-48 space-y-2 overflow-y-auto border-t border-slate-800 pr-2 pt-3 custom-scrollbar scrollbar-thin scrollbar-thumb-slate-700 scrollbar-track-transparent">{comments.map((comment, index) => { const role = comment.role || (comment.is_customer ? 'Requester' : 'L2 Support'); const author = comment.author || comment.sys_created_by || 'ServiceNow journal'; return <article key={comment.id || comment.sys_id || `${journalValue(comment)}-${index}`} className="apple-child-comment rounded-md border border-slate-700 bg-slate-900/70 p-2.5"><div className="flex flex-wrap items-center justify-between gap-2"><span className="rounded-full border border-indigo-400/40 bg-indigo-500/10 px-2 py-1 text-xs font-semibold text-indigo-100">Child update</span><span className="text-[11px] text-slate-500">{journalTime(comment)}</span></div><p className="mt-2 text-xs font-semibold text-cyan-100">{role === 'Requester' ? '👤' : '🎧'} {role} · {author}</p><p className="mt-1 text-xs leading-5 text-slate-300">{journalValue(comment)}</p></article> })}</div> : null}{child.close_notes && <p className="mt-2 border-t border-slate-800 pt-2 text-xs leading-5 text-slate-400"><span className="font-semibold text-slate-300">Closure Notes:</span> {child.close_notes}</p>}</li>
}

export function ChildIncidents({ incidents = [] }) {
  return <section className="apple-children rounded-xl border border-slate-700 bg-slate-950/40 p-4"><div className="flex items-center justify-between gap-3"><h3 className="apple-panel-title text-sm font-semibold">Child Tickets</h3><span className="apple-count">{incidents.length}</span></div><p className="apple-panel-subtitle mt-1 text-xs">Linked incident activity</p>{incidents.length ? <ul className="apple-child-list mt-3 max-h-64 space-y-3 overflow-y-auto pr-2 custom-scrollbar scrollbar-thin scrollbar-thumb-slate-700 scrollbar-track-transparent">{incidents.map((incident) => <ChildTicket key={incident.sys_id || incident.number} incident={incident} />)}</ul> : <p className="mt-3 text-sm text-slate-500">No child incidents linked to this record.</p>}</section>
}

function isClosedTask(task) {
  return task.state === 'Closed' || task.state?.startsWith('Closed')
}

function latestTaskComment(task) {
  return newestFirst((task.comments || []).filter(isHumanJournalEntry))[0]
}

export function TaskActivities({ ticket }) {
  const isChange = ticket.type === 'CHG'
  const tasks = isChange ? ticket.ctasks || [] : ticket.ptasks || []
  const taskName = isChange ? 'Change Tasks' : 'Problem Tasks'

  return <section className="apple-task-activity rounded-xl border border-slate-700 bg-slate-950/40 p-4">
    <div className="flex items-center justify-between gap-3">
      <div><h3 className="apple-panel-title text-sm font-semibold">{taskName}</h3><p className="apple-panel-subtitle mt-1 text-xs">Current implementation and investigation work</p></div>
      <span className="apple-count">{tasks.length}</span>
    </div>
    {tasks.length ? <ul className="mt-4 space-y-3">
      {tasks.map((task) => {
        const closed = isClosedTask(task)
        const latestComment = latestTaskComment(task)
        return <li key={task.sys_id || task.number} className="rounded-lg border border-slate-700 bg-slate-900/60 p-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div><p className="font-mono text-xs text-cyan-300">{task.number}</p><p className="mt-1 text-sm font-medium text-slate-200">{task.short_description || task.title}</p></div>
            <span className={`rounded-full px-2 py-1 text-xs font-semibold ${stateStyles[task.state] || stateStyles.Pending}`}>{task.state}</span>
          </div>
          {closed ? <div className="mt-3 border-t border-slate-800 pt-3"><p className="text-xs font-semibold uppercase tracking-wider text-emerald-300">Closure note</p><p className="mt-1 text-sm leading-6 text-slate-300">{task.close_notes || 'Task closure is recorded; no closure narrative is available.'}</p></div> : <div className="mt-3 border-t border-slate-800 pt-3"><p className="text-xs font-semibold uppercase tracking-wider text-slate-400">Latest task update</p>{latestComment ? <><p className="mt-1 text-xs text-slate-500">{journalTime(latestComment)}</p><p className="mt-1 text-sm leading-6 text-slate-300">{journalValue(latestComment)}</p></> : <p className="mt-1 text-sm text-slate-500">No task comment has been recorded yet.</p>}</div>}
        </li>
      })}
    </ul> : <p className="mt-4 text-sm text-slate-500">No {taskName.toLowerCase()} are attached to this record.</p>}
  </section>
}

export default function WorkItemActivities({ ticket }) {
  // Problem and change records use internal tasks as their working surface.
  // Customer journals and incident-child views are intentionally reserved for
  // incidents and service requests.
  if (ticket.type === 'CHG' || ticket.type === 'PRB') return <TaskActivities ticket={ticket} />

  // child_tickets is the hydrated canonical relationship field. Retain the
  // former child_incidents field only as a compatibility fallback.
  const childTickets = ticket.child_tickets?.length ? ticket.child_tickets : (ticket.child_incidents || [])
  return <><PinnedAttachments attachments={ticket.attachments} /><Journal comments={ticket.comments} /><ChildIncidents incidents={ticket.type === 'INC' ? childTickets : []} /></>
}
