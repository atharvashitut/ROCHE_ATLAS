import { useState } from 'react'
import { api } from '../api'
import { ActionButton, Panel, Status } from './Panel'

const samplePlaybook = {
  change_id: 'CHG-3048', system: 'Veeva Vault', environment: 'production', owner: 'platform-ops', planned_start: '2026-10-01T09:00:00+00:00', planned_end: '2026-10-01T11:30:00+00:00', implementation_steps: ['Apply {system} timeout configuration in {environment}'], validation_steps: ['Validate authentication and audit event delivery'], backout_steps: ['Restore the previous configuration release'],
}

export function AuditPlaybookViewer() {
  const [logs, setLogs] = useState([])
  const [playbook, setPlaybook] = useState(null)
  const [completed, setCompleted] = useState(new Set())
  const [showMarkers, setShowMarkers] = useState(true)
  const [error, setError] = useState('')
  const loadLogs = async () => { try { setError(''); setLogs(await api.listAudit()) } catch (err) { setError(err.message) } }
  const addAudit = async () => { try { await api.recordAudit({ action: 'playbook.generated', actor: 'l2.engineer', resource: 'CHG-3048', details: { patient_reference: 'never retained', policy: 'Veeva Doc #501' }, occurred_at: '2026-10-01T08:30:00+00:00' }); await loadLogs() } catch (err) { setError(err.message) } }
  const generate = async () => { try { setError(''); setPlaybook(await api.generatePlaybook(samplePlaybook)); setCompleted(new Set()) } catch (err) { setError(err.message) } }
  return <div className="grid gap-5 xl:grid-cols-2">
    <Panel eyebrow="Compliance trail" title="Live audit stream" action={<div className="flex gap-2"><ActionButton className="bg-slate-700 text-white hover:bg-slate-600" onClick={loadLogs}>Refresh</ActionButton><ActionButton onClick={addAudit}>Add audit event</ActionButton></div>}>
      <label className="mb-3 flex items-center gap-2 text-sm text-slate-300"><input type="checkbox" checked={showMarkers} onChange={(event) => setShowMarkers(event.target.checked)} /> Show PII/PHI redaction markers</label>
      {!logs.length && <p className="text-sm text-slate-400">The mock Google Drive/Docs audit adapter is empty. Add an event to stream a redacted immutable entry.</p>}
      <div className="max-h-72 space-y-2 overflow-auto">{logs.map((log) => <article key={log.entry_id} className="rounded-lg border border-slate-700 bg-slate-950/50 p-3 text-sm"><div className="flex justify-between gap-2"><b>{log.payload.action}</b><span className="text-slate-400">{log.recorded_at}</span></div><p className="mt-1 text-slate-300">{log.payload.actor} → {log.payload.resource}</p>{showMarkers && <pre className="mt-2 overflow-auto text-xs text-cyan-200">{JSON.stringify(log.payload.details, null, 2)}</pre>}<Status tone="green">immutable {log.entry_id.slice(0, 10)}…</Status></article>)}</div>
    </Panel>
    <Panel eyebrow="Handoff automation" title="Interactive implementation playbook" action={<ActionButton onClick={generate}>Generate playbook</ActionButton>}>
      {!playbook && <p className="text-sm text-slate-400">Create an ordered, parameterized checklist from a client handoff package.</p>}
      {playbook && <ol className="space-y-2">{playbook.items.map((item) => <li key={item.order} className="flex items-start gap-3 rounded-lg bg-slate-950/50 p-3 text-sm"><input className="mt-1" type="checkbox" checked={completed.has(item.order)} onChange={() => setCompleted((prior) => { const next = new Set(prior); next.has(item.order) ? next.delete(item.order) : next.add(item.order); return next })} /><div><Status tone={item.phase === 'backout' ? 'amber' : 'slate'}>{item.order}. {item.phase}</Status><p className="mt-1 text-slate-200">{item.instruction}</p></div></li>)}</ol>}
    </Panel>
    {error && <p className="xl:col-span-2 text-sm text-rose-200">{error}</p>}
  </div>
}
