import { useState } from 'react'

const sourceLabels = { 'ServiceNow KBA': 'ServiceNow KBA', 'Veeva Vault SOP': 'Veeva Vault QMS', 'Google Drive KT/SUD Hub': 'Google Drive KT Hub' }

function referenceIcon(reference) {
  const text = `${reference.title} ${reference.path_or_url}`.toLowerCase()
  if (text.includes('ppt')) return '📊'
  if (text.includes('video')) return '▶️'
  if (text.includes('pdf') || text.includes('sud')) return '📄'
  return '📘'
}

export default function KnowledgeReferences({ references = [] }) {
  const [message, setMessage] = useState('')
  const grouped = references.reduce((groups, reference) => ({ ...groups, [reference.source_type]: [...(groups[reference.source_type] || []), reference] }), {})
  async function copy(reference) { try { await navigator.clipboard.writeText(reference.path_or_url); setMessage(`${reference.source_type} path copied`) } catch { setMessage('Clipboard access is unavailable') } }
  return <section className="rounded-xl border border-slate-700 p-4"><h3 className="text-sm font-semibold">Multi-Source Knowledge References</h3><div className="mt-3 space-y-4">{Object.entries(grouped).map(([source, items]) => <div key={source}><p className="text-xs font-semibold uppercase tracking-wider text-cyan-300">{sourceLabels[source] || source}</p><div className="mt-2 space-y-2">{items.map((reference) => <div key={`${source}-${reference.path_or_url}`} className="rounded-lg bg-slate-950/60 p-3"><div className="flex items-start justify-between gap-3"><p className="text-sm font-medium text-slate-100">{referenceIcon(reference)} {reference.title}</p><button type="button" onClick={() => copy(reference)} className="shrink-0 rounded border border-slate-600 px-2 py-1 text-xs text-cyan-200 hover:bg-slate-800">Copy Path/Link</button></div><p className="mt-1 text-xs leading-5 text-slate-400">{reference.summary}</p><p className="mt-2 break-all font-mono text-[10px] text-slate-500">{reference.path_or_url}</p></div>)}</div></div>)}</div>{message && <p className="mt-3 text-xs text-emerald-300" role="status">{message}</p>}</section>
}
