const stateStyles = {
  Pending: 'bg-amber-500/15 text-amber-200',
  Open: 'bg-cyan-500/15 text-cyan-200',
  Closed: 'bg-emerald-500/15 text-emerald-200',
  'Closed Skipped': 'bg-slate-700 text-slate-300',
}

function TaskList({ title, tasks }) {
  return <section className="rounded-xl border border-slate-700 p-4"><h3 className="text-sm font-semibold">{title}</h3>{tasks?.length ? <ul className="mt-3 space-y-2">{tasks.map((task) => <li key={task.id} className="flex items-center justify-between gap-3 rounded-lg bg-slate-950/60 px-3 py-2 text-sm"><div><p className="font-mono text-xs text-cyan-300">{task.id}</p><p className="mt-1 text-slate-300">{task.title}</p></div><span className={`shrink-0 rounded-full px-2 py-1 text-xs font-semibold ${stateStyles[task.state] || stateStyles.Pending}`}>{task.state}</span></li>)}</ul> : <p className="mt-2 text-sm text-slate-500">No active tasks recorded.</p>}</section>
}

export default function WorkItemActivities({ ticket }) {
  if (ticket.type === 'INC' || ticket.type === 'RITM') return <section className="rounded-xl border border-slate-700 p-4"><h3 className="text-sm font-semibold">Additional Comments</h3><ul className="mt-2 space-y-2 text-sm leading-6 text-slate-400">{(ticket.additional_comments || []).map((comment, index) => <li key={`${comment}-${index}`}>• {comment}</li>)}</ul>{!ticket.additional_comments?.length && <p className="mt-2 text-sm text-slate-500">No additional comments recorded.</p>}</section>
  return <TaskList title={ticket.type === 'CHG' ? 'Change Tasks (CTasks)' : 'Problem Tasks (PTasks)'} tasks={ticket.type === 'CHG' ? ticket.ctasks : ticket.ptasks} />
}
