import { useState } from 'react'
import { api, asBase64 } from '../api'
import { ActionButton, Panel, Status } from './Panel'

export function TriageWorkspace() {
  const [file, setFile] = useState(null)
  const [result, setResult] = useState(null)
  const [history, setHistory] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function runVisualSearch() {
    if (!file) return
    setLoading(true); setError('')
    try { setResult(await api.triageVision(await asBase64(file))) } catch (err) { setError(err.message) } finally { setLoading(false) }
  }

  async function loadHistory() {
    setError('')
    try { setHistory(await api.incidentRelationships('parent-1')) } catch (err) { setError(err.message) }
  }

  return <div className="grid gap-5 xl:grid-cols-2">
    <Panel eyebrow="L2 Workspace" title="Visual triage" action={<ActionButton onClick={runVisualSearch} disabled={!file || loading}>{loading ? 'Analyzing…' : 'Search knowledge'}</ActionButton>}>
      <label className="flex min-h-44 cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed border-cyan-400/50 bg-slate-950/40 p-6 text-center hover:bg-slate-800">
        <span className="text-lg">Drop an incident screenshot</span><span className="mt-1 text-sm text-slate-400">PNG/JPEG encoded locally before it is sent to the triage API</span>
        <input className="sr-only" type="file" accept="image/*" onChange={(event) => setFile(event.target.files?.[0] || null)} />
        {file && <Status tone="green">{file.name}</Status>}
      </label>
      {result && <div className="mt-4 rounded-xl border border-slate-700 bg-slate-950/50 p-4"><div className="flex justify-between gap-3"><div><p className="font-semibold">{result.document_title}</p><p className="text-sm text-cyan-300">{result.document_reference}</p></div><Status tone={result.confidence >= 0.75 ? 'green' : 'amber'}>{Math.round(result.confidence * 100)}% match</Status></div><p className="mt-3 text-sm text-slate-300">{result.analysis}</p><div className="mt-3 border-l-2 border-cyan-400 pl-3 text-sm"><b>{result.draft_type === 'customer_resolution' ? 'Resolution draft' : 'L3 escalation'}</b><p className="mt-1 whitespace-pre-line text-slate-300">{result.draft}</p></div></div>}
    </Panel>
    <Panel eyebrow="ServiceNow" title="Incident relationship traversal" action={<ActionButton onClick={loadHistory}>Load sample history</ActionButton>}>
      {!history && <p className="text-sm text-slate-400">Load linked parent/child incidents and the associated Problem Record from the mock ServiceNow adapter.</p>}
      {history && <div className="space-y-3 text-sm"><div className="rounded-lg bg-slate-800 p-3"><b>{history.ticket.number}</b> · {history.ticket.short_description}<p className="text-slate-400">{history.ticket.state}</p></div>{history.children.map((item) => <div key={item.sys_id} className="ml-5 border-l border-cyan-600 pl-3"><b>{item.number}</b> · {item.short_description}</div>)}{history.problem && <Status tone="amber">Linked {history.problem.number}: {history.problem.short_description}</Status>}</div>}
    </Panel>
    {error && <p className="xl:col-span-2 rounded-lg border border-rose-500/50 bg-rose-500/10 p-3 text-sm text-rose-100">{error}</p>}
  </div>
}
