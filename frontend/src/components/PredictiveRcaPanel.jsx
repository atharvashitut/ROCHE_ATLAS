import { useState } from 'react'
import { api } from '../api'
import { ActionButton, Panel, Status } from './Panel'

const rcaPayload = { logs: [{ trace_id: 'trace-42', content: 'Gateway timeout while authenticating Vault user; upstream latency 30 seconds.' }], tickets: [{ number: 'INC0010042', summary: 'Vault login timeout seen in production', impact: 'high' }] }
const driftPayload = { ci_id: 'CI-VAULT', snapshot: { validation_state: 'draft', timeout_seconds: 60, debug_mode: true }, baseline: { validation_state: 'approved', timeout_seconds: 30 } }
const problemPayload = { service: 'Veeva Vault', summary: 'Recurring authentication timeouts', incident_numbers: ['INC0010042', 'INC0010043', 'INC0010044'], recurrence_count: 3, high_impact_outage: false }

export function PredictiveRcaPanel() {
  const [rca, setRca] = useState(null)
  const [drift, setDrift] = useState(null)
  const [problem, setProblem] = useState(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [error, setError] = useState('')
  const run = async (operation, setter) => { try { setError(''); setter(await operation()) } catch (err) { setError(err.message) } }
  return <div className="grid gap-5 xl:grid-cols-2">
    <Panel eyebrow="Predictive intelligence" title="Root cause analysis" action={<ActionButton onClick={() => run(() => api.rca(rcaPayload), setRca)}>Analyze evidence</ActionButton>}>
      {!rca && <p className="text-sm text-slate-400">Correlate trace signatures and ServiceNow history through the LLM context adapter.</p>}
      {rca && <div className="space-y-3">{rca.probable_causes.map((cause) => <article key={cause.cause} className="rounded-xl bg-slate-950/50 p-4"><div className="flex justify-between gap-3"><b>{cause.cause}</b><Status tone="green">{Math.round(cause.confidence * 100)}% confidence</Status></div><p className="mt-2 text-sm text-slate-300">{cause.rationale}</p></article>)}<p className="text-xs text-slate-400">Evidence: {rca.evidence_links.map((link) => link.label).join(' · ')}</p></div>}
    </Panel>
    <Panel eyebrow="Validated configuration" title="Veeva CMDB drift" action={<ActionButton onClick={() => run(() => api.detectDrift(driftPayload), setDrift)}>Check baseline</ActionButton>}>
      {!drift && <p className="text-sm text-slate-400">Compare a CMDB snapshot with its target Veeva validation baseline.</p>}
      {drift && <div><div className="flex items-center justify-between"><Status tone={drift.compliant ? 'green' : 'amber'}>{drift.compliant ? 'Compliant' : 'Drift detected'}</Status><b>{drift.drift_score}/100</b></div><div className="mt-3 h-3 overflow-hidden rounded-full bg-slate-800"><div className="h-full bg-amber-400" style={{ width: `${drift.drift_score}%` }} /></div><div className="mt-4 space-y-2">{drift.findings.map((finding) => <div key={finding.field} className="grid grid-cols-[1fr_auto] gap-3 rounded-lg bg-slate-950/50 p-3 text-sm"><span><b>{finding.field}</b><br /><span className="text-slate-400">Expected {String(finding.expected)} · observed {String(finding.observed)}</span></span><Status tone={finding.severity === 'high' ? 'red' : 'amber'}>{finding.severity}</Status></div>)}</div></div>}
    </Panel>
    <Panel eyebrow="ServiceNow automation" title="Problem Record drawer" action={<ActionButton onClick={() => run(async () => { const response = await api.createProblem(problemPayload); setDrawerOpen(true); return response }, setProblem)}>Create PRB</ActionButton>}>
      <p className="text-sm text-slate-400">A Problem Record is generated only after recurring incidents reach the configured threshold or a high-impact outage is declared.</p>
      {drawerOpen && problem && <aside className="mt-4 rounded-xl border border-cyan-400/50 bg-cyan-400/10 p-4"><div className="flex justify-between"><b>{problem.should_create ? 'Generated Problem Record' : 'No Problem Record'}</b><button className="text-sm text-cyan-200" onClick={() => setDrawerOpen(false)}>Close</button></div>{problem.record ? <div className="mt-2 text-sm"><p className="text-xl font-bold">{problem.record.number}</p><p>{problem.record.short_description}</p><p className="mt-2 text-slate-300">{problem.record.priority} · {problem.record.assignment_group} · {problem.record.incident_references.join(', ')}</p></div> : <p className="mt-2 text-sm">{problem.reason}</p>}</aside>}
    </Panel>
    {error && <p className="xl:col-span-2 text-sm text-rose-200">{error}</p>}
  </div>
}
