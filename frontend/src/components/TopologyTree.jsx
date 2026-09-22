import { useState } from 'react'
import WorkItemActivities from './WorkItemActivities'

const phaseMaps = { CHG: ['New', 'Assess', 'Authorize', 'Schedule', 'Implement', 'Review', 'Closed'], PRB: ['New', 'Assess', 'RCA', 'QA', 'Review', 'Closed'] }
const closedStates = new Set(['Closed', 'Resolved', 'Closed Complete', 'Closed Incomplete', 'Closed Skipped'])
const taskTypes = new Set(['CTASK', 'PTASK', 'SCTASK'])
const ctaskStateStyles = { 'Closed Complete': 'bg-emerald-500/20 text-emerald-200', Open: 'bg-cyan-500/20 text-cyan-200', Pending: 'bg-amber-500/20 text-amber-200' }

function nodeType(node) {
  if (node.type) return node.type
  if (node.number?.startsWith('CTASK')) return 'CTASK'
  if (node.number?.startsWith('PTASK')) return 'PTASK'
  if (node.number?.startsWith('SCTASK')) return 'SCTASK'
  if (node.number?.startsWith('RITM')) return 'RITM'
  return node.number?.slice(0, 3) || 'INC'
}

function PhaseStepper({ node }) {
  const type = nodeType(node)
  const phases = phaseMaps[type]
  if (!phases) return null
  const current = node.chg_phase || node.prb_phase || 'New'
  const currentIndex = Math.max(0, phases.indexOf(current))
  return <div className="mt-5"><p className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">{type} phase</p><div className="flex flex-wrap gap-1">{phases.map((phase, index) => <span key={phase} className={`rounded-full px-2 py-1 text-xs ${index < currentIndex ? 'bg-emerald-500/20 text-emerald-200' : index === currentIndex ? 'bg-cyan-400 font-bold text-slate-950' : 'bg-slate-800 text-slate-500'}`}>{phase}</span>)}</div></div>
}

function InspectorDrawer({ node, onClose }) {
  const type = nodeType(node)
  const showClosure = closedStates.has(node.state) && node.close_notes
  const isTask = taskTypes.has(type)
  return <div className="fixed inset-0 z-40 bg-slate-950/75" role="presentation" onMouseDown={onClose}><aside role="dialog" aria-modal="true" aria-label="Topology node inspector" className="ml-auto h-full w-full max-w-lg overflow-y-auto bg-slate-900 p-6 shadow-2xl" onMouseDown={(event) => event.stopPropagation()}><div className="flex items-start justify-between gap-4"><div><p className="font-mono text-sm text-cyan-300">{node.number} · {type}</p><h3 className="mt-1 text-xl font-semibold">{node.short_description || node.title}</h3><p className="mt-2 text-sm text-slate-400">State: {node.state || 'Not recorded'}</p></div><button type="button" onClick={onClose} className="rounded-lg border border-slate-600 px-3 py-1.5 text-sm hover:bg-slate-800">Close</button></div><PhaseStepper node={node} />{node.latest_note && <section className="mt-5 rounded-xl border border-slate-700 p-4"><h4 className="text-sm font-semibold">Latest Work Note</h4><p className="mt-2 text-sm leading-6 text-slate-300">{node.latest_note}</p></section>}{isTask ? <section className="mt-5 rounded-xl border border-slate-700 p-4"><h4 className="text-sm font-semibold">Additional Comments (Customer Visible)</h4>{node.comments?.length ? <ul className="mt-2 space-y-2 text-sm text-slate-300">{node.comments.map((comment, index) => <li key={`${comment}-${index}`}>• {comment}</li>)}</ul> : <p className="mt-2 text-sm text-slate-500">No customer-visible comments recorded.</p>}</section> : <div className="mt-6"><WorkItemActivities ticket={{ ...node, type }} /></div>}{showClosure && <section className="mt-4 rounded-xl border border-slate-700 p-4"><h4 className="text-sm font-semibold">Closure Notes</h4><p className="mt-2 text-sm leading-6 text-slate-300">{node.close_notes}</p></section>}</aside></div>
}

function TopologyNode({ label, node, onSelectTicket, tone = 'slate' }) {
  const colors = { cyan: 'border-cyan-500/50 bg-cyan-500/10 text-cyan-100', indigo: 'border-indigo-500/50 bg-indigo-500/10 text-indigo-100', amber: 'border-amber-500/50 bg-amber-500/10 text-amber-100', emerald: 'border-emerald-500/50 bg-emerald-500/10 text-emerald-100', slate: 'border-slate-600 bg-slate-800 text-slate-100' }
  const isCTask = nodeType(node) === 'CTASK'
  return <button type="button" onClick={() => onSelectTicket(node.number, node)} className={`max-w-56 rounded-lg border px-3 py-2 text-left text-xs shadow-sm transition hover:brightness-125 ${colors[tone]}`}><span className="block font-mono text-[10px] opacity-80">{label} · {node.number}</span><span className="mt-1 block font-semibold">{node.short_description || node.title}</span>{isCTask ? <span className={`mt-2 inline-flex rounded-full px-2 py-0.5 text-[10px] font-bold ${ctaskStateStyles[node.state] || 'bg-slate-700 text-slate-200'}`}>{node.state}</span> : node.state && <span className="mt-1 block text-[10px] opacity-70">{node.state}</span>}</button>
}

function EmptyNode({ children }) { return <span className="rounded-lg border border-dashed border-slate-700 px-3 py-2 text-xs text-slate-500">{children}</span> }
function GraphColumn({ children }) { return <div className="grid gap-2">{children}</div> }

function CurrentNode({ ticket, onSelectTicket }) {
  const current = { number: ticket.number || ticket.id, title: ticket.title, short_description: ticket.short_description, state: ticket.state, type: ticket.type, close_notes: ticket.close_notes, chg_phase: ticket.chg_phase, prb_phase: ticket.prb_phase, comments: ticket.comments, child_incidents: ticket.child_incidents, ctasks: ticket.ctasks, ptasks: ticket.ptasks, sctasks: ticket.sctasks, latest_note: ticket.work_notes?.at(-1) }
  return <TopologyNode label="Current Record" node={current} onSelectTicket={onSelectTicket} tone="indigo" />
}

function ChangeTaskBranch({ change, onSelectTicket, label = 'Linked Fix Change' }) {
  if (!change) return null
  return <div className="flex items-center gap-3"><TopologyNode label={label} node={change} onSelectTicket={onSelectTicket} tone="emerald" /><span className="shrink-0 font-mono text-slate-400">──&gt;</span><GraphColumn>{change.ctasks?.length ? change.ctasks.map((task) => <TopologyNode key={task.sys_id || task.number} label="CTask" node={task} onSelectTicket={onSelectTicket} tone="emerald" />) : <EmptyNode>No CTasks</EmptyNode>}</GraphColumn></div>
}

function IncidentGraph({ ticket, onSelectTicket }) {
  const children = ticket.child_incidents || []
  return <><GraphColumn>{ticket.parent_incident ? <TopologyNode label="Parent Incident" node={ticket.parent_incident} onSelectTicket={onSelectTicket} tone="cyan" /> : <EmptyNode>No Parent INC</EmptyNode>}</GraphColumn><span className="text-slate-500">→</span><CurrentNode ticket={ticket} onSelectTicket={onSelectTicket} /><span className="text-slate-500">→</span><div className="grid gap-3"><GraphColumn>{children.map((child) => <TopologyNode key={child.number} label="Child Incident" node={child} onSelectTicket={onSelectTicket} tone="cyan" />)}{ticket.linked_prb && <TopologyNode label="Linked PRB" node={ticket.linked_prb} onSelectTicket={onSelectTicket} tone="amber" />}{!children.length && !ticket.linked_prb && !ticket.linked_chg && <EmptyNode>No downstream records</EmptyNode>}</GraphColumn><ChangeTaskBranch change={ticket.linked_chg} onSelectTicket={onSelectTicket} label="Linked CHG" /></div></>
}

function OriginatingTickets({ tickets = [], onSelectTicket }) {
  if (!tickets.length) return <GraphColumn><EmptyNode>No originating tickets</EmptyNode></GraphColumn>
  const plural = tickets.length > 1
  return <GraphColumn>{plural && <p className="px-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">Originating Tickets ({tickets.length})</p>}{tickets.map((ticket) => <TopologyNode key={`${ticket.sys_id}-${ticket.number}`} label="Originating Ticket" node={ticket} onSelectTicket={onSelectTicket} tone="cyan" />)}</GraphColumn>
}

function ChangeGraph({ ticket, onSelectTicket }) {
  return <><OriginatingTickets tickets={ticket.originating_tickets} onSelectTicket={onSelectTicket} /><span className="text-slate-500">→</span><CurrentNode ticket={ticket} onSelectTicket={onSelectTicket} /><span className="text-slate-500">→</span><GraphColumn>{ticket.ctasks?.length ? ticket.ctasks.map((task) => <TopologyNode key={task.sys_id || task.number} label="CTask" node={task} onSelectTicket={onSelectTicket} tone="emerald" />) : <EmptyNode>No CTasks</EmptyNode>}</GraphColumn></>
}

function ProblemGraph({ ticket, onSelectTicket }) {
  return <><OriginatingTickets tickets={ticket.originating_tickets} onSelectTicket={onSelectTicket} /><span className="text-slate-500">→</span><CurrentNode ticket={ticket} onSelectTicket={onSelectTicket} /><span className="text-slate-500">→</span><div className="grid gap-3"><GraphColumn>{ticket.ptasks?.length ? ticket.ptasks.map((task) => <TopologyNode key={task.sys_id || task.number} label="PTask" node={task} onSelectTicket={onSelectTicket} tone="amber" />) : <EmptyNode>No PTasks</EmptyNode>}</GraphColumn><ChangeTaskBranch change={ticket.linked_chg} onSelectTicket={onSelectTicket} /></div></>
}

function GenericGraph({ ticket, onSelectTicket }) { return <><EmptyNode>No upstream record</EmptyNode><span className="text-slate-500">→</span><CurrentNode ticket={ticket} onSelectTicket={onSelectTicket} /><span className="text-slate-500">→</span><EmptyNode>No downstream record</EmptyNode></> }

export default function TopologyTree({ ticket, onSelectTicket }) {
  const [inspectedNode, setInspectedNode] = useState(null)
  const type = nodeType(ticket)
  const selectNode = (number, node) => {
    if (/^(INC|RITM|PRB|CHG)/.test(number || '') && onSelectTicket) onSelectTicket(number)
    else setInspectedNode(node)
  }
  const graph = type === 'INC' ? <IncidentGraph ticket={ticket} onSelectTicket={selectNode} /> : type === 'CHG' ? <ChangeGraph ticket={ticket} onSelectTicket={selectNode} /> : type === 'PRB' ? <ProblemGraph ticket={ticket} onSelectTicket={selectNode} /> : <GenericGraph ticket={ticket} onSelectTicket={selectNode} />
  return <section className="rounded-xl border border-slate-700 bg-slate-950/60 p-4"><p className="mb-1 text-xs font-semibold uppercase tracking-wider text-cyan-300">Relational topology tree</p><p className="mb-4 text-xs text-slate-500">{type} relationship view</p><div className="overflow-x-auto"><div className="flex min-w-max items-center gap-3">{graph}</div></div><p className="mt-3 text-xs text-slate-500">Select a ticket node to load its complete ServiceNow record; task nodes open their local task details.</p>{inspectedNode && <InspectorDrawer node={inspectedNode} onClose={() => setInspectedNode(null)} />}</section>
}
