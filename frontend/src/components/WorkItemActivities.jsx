const stateStyles = {
  Pending: 'bg-amber-500/15 text-amber-200',
  Open: 'bg-cyan-500/15 text-cyan-200',
  'In Progress': 'bg-cyan-500/15 text-cyan-200',
  'Work in Progress': 'bg-cyan-500/15 text-cyan-200',
  New: 'bg-slate-700 text-slate-200',
  Assess: 'bg-indigo-500/15 text-indigo-200',
  Closed: 'bg-emerald-500/15 text-emerald-200',
  'Closed Complete': 'bg-emerald-500/15 text-emerald-200',
  'Closed Incomplete': 'bg-rose-500/15 text-rose-200',
  'Closed Skipped': 'bg-slate-700 text-slate-300',
  Canceled: 'bg-slate-700 text-slate-300',
}

function TaskList({ title, tasks }) {
  return <section className="rounded-xl border border-slate-700 p-4"><h3 className="text-sm font-semibold">{title}</h3>{tasks?.length ? <ul className="mt-3 space-y-2">{tasks.map((task) => <li key={task.sys_id || task.number} className="rounded-lg bg-slate-950/60 px-3 py-2 text-sm"><div className="flex items-center justify-between gap-3"><div><p className="font-mono text-xs text-cyan-300">{task.number}</p><p className="mt-1 text-slate-300">{task.short_description}</p></div><span className={`shrink-0 rounded-full px-2 py-1 text-xs font-semibold ${stateStyles[task.state] || stateStyles.Pending}`}>{task.state}</span></div>{task.close_notes && <p className="mt-2 border-t border-slate-800 pt-2 text-xs leading-5 text-slate-400"><span className="font-semibold text-slate-300">Closure Notes:</span> {task.close_notes}</p>}</li>)}</ul> : <p className="mt-2 text-sm text-slate-500">No tasks recorded.</p>}</section>
}

function Comments({ comments }) {
  return <section className="rounded-xl border border-slate-700 p-4"><h3 className="text-sm font-semibold">Additional Comments (Customer Visible)</h3>{comments?.length ? <ul className="mt-2 space-y-2 text-sm leading-6 text-slate-400">{comments.map((comment, index) => <li key={`${comment}-${index}`}>• {comment}</li>)}</ul> : <p className="mt-2 text-sm text-slate-500">No customer-visible comments recorded.</p>}</section>
}

function ChildIncidents({ incidents }) {
  return <section className="rounded-xl border border-slate-700 p-4"><h3 className="text-sm font-semibold">Child Incidents</h3>{incidents?.length ? <ul className="mt-3 space-y-3">{incidents.map((incident) => <li key={incident.sys_id || incident.number} className="rounded-lg bg-slate-950/60 p-3"><div className="flex items-center justify-between gap-3"><div><p className="font-mono text-xs text-cyan-300">{incident.number}</p><p className="mt-1 text-sm text-slate-300">{incident.short_description}</p></div><span className={`shrink-0 rounded-full px-2 py-1 text-xs font-semibold ${stateStyles[incident.state] || stateStyles.Pending}`}>{incident.state}</span></div>{incident.comments?.length ? <div className="mt-3 border-t border-slate-800 pt-2"><p className="text-xs font-semibold text-slate-400">Additional Comments (Customer Visible)</p>{incident.comments.map((comment, index) => <p key={`${comment}-${index}`} className="mt-1 text-xs leading-5 text-slate-400">• {comment}</p>)}</div> : null}{incident.close_notes && <p className="mt-2 border-t border-slate-800 pt-2 text-xs leading-5 text-slate-400"><span className="font-semibold text-slate-300">Closure Notes:</span> {incident.close_notes}</p>}</li>)}</ul> : <p className="mt-2 text-sm text-slate-500">No child incidents recorded.</p>}</section>
}

export default function WorkItemActivities({ ticket }) {
  if (ticket.type === 'INC') return <><Comments comments={ticket.comments} /><ChildIncidents incidents={ticket.child_incidents} /></>
  if (ticket.type === 'RITM') return <><Comments comments={ticket.comments} /><TaskList title="Catalog Tasks (SCTasks)" tasks={ticket.sctasks} /></>
  if (ticket.type === 'CHG') return <TaskList title="Change Tasks (CTasks)" tasks={ticket.ctasks} />
  return <TaskList title="Problem Tasks (PTasks)" tasks={ticket.ptasks} />
}
