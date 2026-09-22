import { useState } from 'react'

const phaseMaps = {
  CHG: ['New', 'Assess', 'Authorize', 'Schedule', 'Implement', 'Review', 'Closed'],
  PRB: ['New', 'Assess', 'RCA', 'QA', 'Review', 'Closed'],
}

function nodeType(node) {
  if (node.type) return node.type
  if (node.number?.startsWith('RITM')) return 'RITM'
  return node.number?.slice(0, 3) || 'INC'
}

function PhaseStepper({ node }) {
  const type = nodeType(node)
  const phases = phaseMaps[type]
  if (!phases) return null
  const current = node.chg_phase || node.prb_phase || 'New'
  const currentIndex = Math.max(0, phases.indexOf(current))
  return <div className="mt-5"><p className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">{type} phase</p><div className="flex flex-wrap gap-1">{phases.map((phase, index) => <span key={phase} className={`rounded-full px-2 py-1 text-xs ${index < currentIndex ? 'bg-emerald-500/20 text-emerald-200' : index === currentIndex ? 'bg-cyan-400 text-slate-950 font-bold' : 'bg-slate-800 text-slate-500'}`}>{phase}</span>)}</div></div>
}

function InspectorDrawer({ node, onClose }) {
  const notes = node.work_notes || (node.latest_note ? [node.latest_note] : ['No work notes recorded.'])
  return <div className="fixed inset-0 z-40 bg-slate-950/75" role="presentation" onMouseDown={onClose}><aside role="dialog" aria-modal="true" aria-label="Topology node inspector" className="ml-auto h-full w-full max-w-lg overflow-y-auto bg-slate-900 p-6 shadow-2xl" onMouseDown={(event) => event.stopPropagation()}><div className="flex items-start justify-between gap-4"><div><p className="font-mono text-sm text-cyan-300">{node.number} · {nodeType(node)}</p><h3 className="mt-1 text-xl font-semibold">{node.title}</h3></div><button type="button" onClick={onClose} className="rounded-lg border border-slate-600 px-3 py-1.5 text-sm hover:bg-slate-800">Close</button></div><PhaseStepper node={node} /><section className="mt-6 rounded-xl border border-slate-700 p-4"><h4 className="text-sm font-semibold">Work notes</h4><ul className="mt-3 space-y-2 text-sm leading-6 text-slate-300">{notes.map((note, index) => <li key={`${note}-${index}`}>• {note}</li>)}</ul></section><section className="mt-4 rounded-xl border border-slate-700 p-4"><h4 className="text-sm font-semibold">Closure notes</h4><p className="mt-2 text-sm leading-6 text-slate-300">{node.close_notes || 'No closure notes recorded.'}</p></section></aside></div>
}

function TopologyNode({ label, node, onSelect, tone = 'slate' }) {
  if (!node) return <span className="rounded-lg border border-dashed border-slate-700 px-3 py-2 text-xs text-slate-500">No {label}</span>
  const colors = { cyan: 'border-cyan-500/50 bg-cyan-500/10 text-cyan-100', indigo: 'border-indigo-500/50 bg-indigo-500/10 text-indigo-100', amber: 'border-amber-500/50 bg-amber-500/10 text-amber-100', emerald: 'border-emerald-500/50 bg-emerald-500/10 text-emerald-100', slate: 'border-slate-600 bg-slate-800 text-slate-100' }
  return <button type="button" onClick={() => onSelect(node)} className={`max-w-52 rounded-lg border px-3 py-2 text-left text-xs shadow-sm transition hover:brightness-125 ${colors[tone]}`}><span className="block font-mono text-[10px] opacity-80">{label} · {node.number}</span><span className="mt-1 block font-semibold">{node.title}</span></button>
}

export default function TopologyTree({ ticket }) {
  const [inspectedNode, setInspectedNode] = useState(null)
  const current = { number: ticket.number || ticket.id, title: ticket.title, type: ticket.type, work_notes: ticket.work_notes, close_notes: ticket.close_notes, chg_phase: ticket.chg_phase, prb_phase: ticket.prb_phase }
  return <section className="rounded-xl border border-slate-700 bg-slate-950/60 p-4"><p className="mb-4 text-xs font-semibold uppercase tracking-wider text-cyan-300">Relational topology tree</p><div className="overflow-x-auto"><div className="flex min-w-max items-center gap-3"><TopologyNode label="Parent INC" node={ticket.parent_inc} onSelect={setInspectedNode} tone="cyan" /><span className="text-slate-500">→</span><TopologyNode label="Current Ticket" node={current} onSelect={setInspectedNode} tone="indigo" /><span className="text-slate-500">→</span><div className="grid gap-2"><TopologyNode label="Child INC" node={ticket.child_incs?.[0]} onSelect={setInspectedNode} tone="cyan" />{ticket.child_incs?.slice(1).map((child) => <TopologyNode key={child.number} label="Child INC" node={child} onSelect={setInspectedNode} tone="cyan" />)}</div><div className="grid gap-2"><TopologyNode label="Linked PRB" node={ticket.linked_prb} onSelect={setInspectedNode} tone="amber" /><TopologyNode label="Linked CHG" node={ticket.linked_chg} onSelect={setInspectedNode} tone="emerald" /></div></div></div><p className="mt-3 text-xs text-slate-500">Select any record to inspect its notes, closure information, and applicable phase.</p>{inspectedNode && <InspectorDrawer node={inspectedNode} onClose={() => setInspectedNode(null)} />}</section>
}
