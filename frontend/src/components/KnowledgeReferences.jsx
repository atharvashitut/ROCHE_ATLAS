import { useState } from 'react'

const sourceLabels = { 'ServiceNow KBA': 'ServiceNow KBA', 'Veeva Vault SOP': 'Veeva Vault QMS', 'HP ALM Defect': 'HP ALM Quality Center', 'Google Drive KT/SUD Hub': 'Google Drive KT Hub' }

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
  const sourceUrl = (reference) => reference.path_or_url.startsWith('http') ? reference.path_or_url : `https://www.google.com/search?q=${encodeURIComponent(reference.path_or_url)}`
  async function copy(reference) { try { await navigator.clipboard.writeText(reference.path_or_url); setMessage(`${reference.source_type} path copied`) } catch { setMessage('Clipboard access is unavailable') } }
  return <footer className="apple-knowledge rounded-xl border border-slate-700 bg-slate-950/40 p-4"><h3 className="apple-panel-title text-sm font-semibold">📚 Multi-Source Knowledge References</h3><p className="apple-panel-subtitle mt-1 text-xs text-slate-500">Grounding sources for the current investigation.</p><div className="mt-3 space-y-4">{Object.entries(grouped).map(([source, items]) => <div key={source}><p className="text-xs font-semibold uppercase tracking-wider text-cyan-300">{sourceLabels[source] || source}</p><div className="mt-2 space-y-2">{items.map((reference) => <div key={`${source}-${reference.path_or_url}`} className="apple-knowledge-item rounded-lg bg-slate-900/70 p-3"><div className="flex items-start justify-between gap-3"><p className="text-sm font-medium text-slate-100">{referenceIcon(reference)} {reference.title}</p><div className="flex shrink-0 gap-2"><a href={sourceUrl(reference)} target="_blank" rel="noreferrer" className="rounded border border-cyan-500/40 px-2 py-1 text-xs text-cyan-100 hover:bg-cyan-500/10">Open Source ↗</a><button type="button" onClick={() => copy(reference)} className="rounded border border-slate-600 px-2 py-1 text-xs text-cyan-200 hover:bg-slate-800">Copy</button></div></div><p className="mt-1 text-xs leading-5 text-slate-400">{reference.summary}</p></div>)}</div></div>)}</div>{message && <p className="mt-3 text-xs text-emerald-300" role="status">{message}</p>}</footer>
}
