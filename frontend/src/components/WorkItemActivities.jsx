const stateStyles = {
  Pending: 'bg-amber-500/15 text-amber-200', Open: 'bg-cyan-500/15 text-cyan-200', 'In Progress': 'bg-cyan-500/15 text-cyan-200', 'Work in Progress': 'bg-cyan-500/15 text-cyan-200', New: 'bg-slate-700 text-slate-200', Assess: 'bg-indigo-500/15 text-indigo-200', Closed: 'bg-emerald-500/15 text-emerald-200', 'Closed Complete': 'bg-emerald-500/15 text-emerald-200', 'Closed Incomplete': 'bg-rose-500/15 text-rose-200', 'Closed Skipped': 'bg-slate-700 text-slate-300', Canceled: 'bg-slate-700 text-slate-300',
}

function journalValue(entry) { return typeof entry === 'string' ? entry : entry.value }
function journalTime(entry) { return typeof entry === 'string' ? '' : entry.sys_created_on }
function latest(entries) { return [...entries].sort((left, right) => (left.sys_created_on || '').localeCompare(right.sys_created_on || '')).at(-1) }

function TaskList({ title, tasks }) {
  return <section className="rounded-xl border border-slate-700 p-4"><h3 className="text-sm font-semibold">{title}</h3>{tasks?.length ? <ul className="mt-3 space-y-2">{tasks.map((task) => <li key={task.sys_id || task.number} className="rounded-lg bg-slate-950/60 px-3 py-2 text-sm"><div className="flex items-center justify-between gap-3"><div><p className="font-mono text-xs text-cyan-300">{task.number}</p><p className="mt-1 text-slate-300">{task.short_description}</p></div><span className={`shrink-0 rounded-full px-2 py-1 text-xs font-semibold ${stateStyles[task.state] || stateStyles.Pending}`}>{task.state}</span></div>{task.close_notes && <p className="mt-2 border-t border-slate-800 pt-2 text-xs leading-5 text-slate-400"><span className="font-semibold text-slate-300">Closure Notes:</span> {task.close_notes}</p>}</li>)}</ul> : <p className="mt-2 text-sm text-slate-500">No tasks recorded.</p>}</section>
}

function LatestCommunicationActivity({ ticket, comments }) {
  if (!['INC', 'RITM'].includes(ticket.type)) return null
  const customerUpdate = latest(comments.filter((entry) => entry.is_customer))
  const supportUpdate = latest(comments.filter((entry) => !entry.is_customer))
  const sentiment = ticket.customer_sentiment || { status: 'Neutral', score_pct: 0, explanation: 'No customer sentiment score is available.' }
  const faces = { Frustrated: '😠', Impatient: '😟', Satisfied: '😊', Neutral: '😐' }
  return <section className="rounded-xl border-2 border-cyan-400/40 bg-cyan-950/20 p-4"><h3 className="text-sm font-bold text-cyan-100">💬 Latest Communication Activity</h3><div className="mt-3 grid gap-3 lg:grid-cols-2"><article className="rounded-lg border border-slate-700 bg-slate-950/60 p-3"><div className="flex items-start justify-between gap-3"><div><p className="text-sm font-semibold text-slate-100">👤 Requester · {ticket.caller_id}</p><p className="mt-1 text-xs text-slate-500">{journalTime(customerUpdate)}</p></div><span title={sentiment.explanation} className="shrink-0 rounded-full bg-rose-500/15 px-2 py-1 text-xs font-bold text-rose-100">{faces[sentiment.status]} {sentiment.status} - {sentiment.score_pct}% Urgency Score</span></div><p className="mt-3 text-sm leading-6 text-slate-300">{customerUpdate ? journalValue(customerUpdate) : 'No caller-authored additional comments recorded.'}</p></article><article className="rounded-lg border border-slate-700 bg-slate-950/60 p-3"><p className="text-sm font-semibold text-slate-100">🎧 L2 Support · {ticket.assigned_to}</p><p className="mt-1 text-xs text-slate-500">{journalTime(supportUpdate)}</p><p className="mt-3 text-sm leading-6 text-slate-300">{supportUpdate ? journalValue(supportUpdate) : 'No L2 support response recorded.'}</p></article></div></section>
}

function Comments({ ticket, showCommunicationSummary = false }) {
  const comments = ticket.comments || []
  return <>{showCommunicationSummary && <LatestCommunicationActivity ticket={ticket} comments={comments} />}<section className="rounded-xl border border-slate-700 p-4"><h3 className="text-sm font-semibold">Additional Comments Stream</h3>{comments.length ? <ul className="mt-3 space-y-3 text-sm leading-6 text-slate-400">{comments.map((comment, index) => <li key={comment.sys_id || `${journalValue(comment)}-${index}`} className="border-l-2 border-slate-700 pl-3"><div className="flex flex-wrap items-center gap-x-2 text-xs text-slate-500"><span>{typeof comment === 'string' ? 'ServiceNow journal' : comment.sys_created_by}</span><span>{journalTime(comment)}</span>{typeof comment !== 'string' && <span className={`rounded-full px-2 py-0.5 ${comment.is_customer ? 'bg-cyan-500/15 text-cyan-200' : 'bg-indigo-500/15 text-indigo-200'}`}>{comment.is_customer ? 'Caller' : 'L2 Support'}</span>}</div><p className="mt-1">{journalValue(comment)}</p></li>)}</ul> : <p className="mt-2 text-sm text-slate-500">No customer-visible comments recorded.</p>}</section></>
}

function ChildIncidents({ incidents }) {
  return <section className="rounded-xl border border-slate-700 p-4"><h3 className="text-sm font-semibold">Child Incidents</h3>{incidents?.length ? <ul className="mt-3 space-y-3">{incidents.map((incident) => <li key={incident.sys_id || incident.number} className="rounded-lg bg-slate-950/60 p-3"><div className="flex items-center justify-between gap-3"><div><p className="font-mono text-xs text-cyan-300">{incident.number}</p><p className="mt-1 text-sm text-slate-300">{incident.short_description}</p></div><span className={`shrink-0 rounded-full px-2 py-1 text-xs font-semibold ${stateStyles[incident.state] || stateStyles.Pending}`}>{incident.state}</span></div>{incident.comments?.length ? <div className="mt-3 border-t border-slate-800 pt-2"><p className="text-xs font-semibold text-slate-400">Additional Comments Stream</p>{incident.comments.map((comment, index) => <p key={comment.sys_id || `${journalValue(comment)}-${index}`} className="mt-1 text-xs leading-5 text-slate-400">• {journalValue(comment)}</p>)}</div> : null}{incident.close_notes && <p className="mt-2 border-t border-slate-800 pt-2 text-xs leading-5 text-slate-400"><span className="font-semibold text-slate-300">Closure Notes:</span> {incident.close_notes}</p>}</li>)}</ul> : <p className="mt-2 text-sm text-slate-500">No child incidents recorded.</p>}</section>
}

export default function WorkItemActivities({ ticket, showCommunicationSummary = false }) {
  const comments = <Comments ticket={ticket} showCommunicationSummary={showCommunicationSummary} />
  if (ticket.type === 'INC') return <>{comments}<ChildIncidents incidents={ticket.child_incidents} /></>
  if (ticket.type === 'RITM') return <>{comments}<TaskList title="Catalog Tasks (SCTasks)" tasks={ticket.sctasks} /></>
  if (ticket.type === 'CHG') return <>{comments}<TaskList title="Change Tasks (CTasks)" tasks={ticket.ctasks} /></>
  return <>{comments}<TaskList title="Problem Tasks (PTasks)" tasks={ticket.ptasks} /></>
}
