import { useState } from 'react'
import { api } from '../api'
import { ActionButton, Panel, Status } from './Panel'

const sampleChange = {
  change_id: 'CHG-3048', title: 'Vault authentication timeout update', description: 'Increase the Vault integration timeout to reduce production authentication failures.', requested_by: 'platform-ops', ci_ids: ['CI-VAULT'], planned_start: '2026-10-01T09:00:00+00:00', planned_end: '2026-10-01T11:30:00+00:00', requested_type: 'normal', implementation_steps: ['Update Vault timeout configuration'], test_steps: ['Verify authentication health checks'], backout_steps: ['Restore the previous timeout configuration'],
}

export function ChangeRiskDashboard() {
  const [assessment, setAssessment] = useState(null)
  const [error, setError] = useState('')
  async function assess() { try { setError(''); setAssessment(await api.assessChange(sampleChange)) } catch (err) { setError(err.message) } }
  return <Panel eyebrow="Change control" title="Risk & Veeva policy dashboard" action={<ActionButton onClick={assess}>Assess sample CR</ActionButton>}>
    {!assessment && <p className="text-sm text-slate-400">Run the sample Change Request to calculate real-time risk, policy traceability, approvals, and calendar conflict status.</p>}
    {assessment && <div className="grid gap-4 md:grid-cols-3"><div className="rounded-xl bg-slate-950/50 p-4"><p className="text-xs uppercase text-slate-400">Risk score</p><p className="mt-1 text-4xl font-bold text-amber-300">{assessment.risk_assessment.score}</p><Status tone="amber">{assessment.classification}</Status></div><div className="rounded-xl bg-slate-950/50 p-4"><p className="text-xs uppercase text-slate-400">Policy compliance</p><p className="mt-2 text-sm">Veeva Doc {assessment.policy_trace.document_id?.replace('Veeva Doc #', '#')} · page {assessment.policy_trace.page}</p><p className="mt-2 text-sm text-emerald-200">Required: {assessment.required_fields.join(', ')}</p></div><div className="rounded-xl bg-slate-950/50 p-4"><p className="text-xs uppercase text-slate-400">Blackout calendar</p>{assessment.risk_assessment.blackout_conflicts.length ? <p className="mt-2 text-amber-200">⚠ {assessment.risk_assessment.blackout_conflicts.join(', ')}</p> : <p className="mt-2 text-emerald-200">No blackout conflicts</p>}<p className="mt-2 text-sm">Approvers: {assessment.approver_routing.join(' → ')}</p></div></div>}
    {error && <p className="mt-4 text-sm text-rose-200">{error}</p>}
  </Panel>
}
