import { useState } from 'react'
import { AuditPlaybookViewer } from './components/AuditPlaybookViewer'
import { ChangeRiskDashboard } from './components/ChangeRiskDashboard'
import { PredictiveRcaPanel } from './components/PredictiveRcaPanel'
import { TriageWorkspace } from './components/TriageWorkspace'

const tabs = [
  ['triage', 'Triage workspace'], ['changes', 'Change risk'], ['audit', 'Audit & playbook'], ['predictive', 'Predictive RCA'],
]

export default function App() {
  const [activeTab, setActiveTab] = useState('triage')
  const content = { triage: <TriageWorkspace />, changes: <ChangeRiskDashboard />, audit: <AuditPlaybookViewer />, predictive: <PredictiveRcaPanel /> }
  return <main className="min-h-screen bg-slate-950 text-slate-100"><header className="border-b border-slate-800 bg-slate-950/80 px-5 py-5 backdrop-blur"><div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4"><div><p className="text-xs font-bold uppercase tracking-[0.24em] text-cyan-300">Roche Atlas · ITSM Copilot</p><h1 className="mt-1 text-2xl font-bold">Operations intelligence workspace</h1></div><span className="rounded-full border border-emerald-500/50 bg-emerald-500/10 px-3 py-1 text-sm text-emerald-200">API-integrated prototype</span></div></header><div className="mx-auto max-w-7xl px-5 py-6"><nav className="mb-6 flex flex-wrap gap-2">{tabs.map(([key, label]) => <button key={key} onClick={() => setActiveTab(key)} className={`rounded-lg px-3 py-2 text-sm font-semibold transition ${activeTab === key ? 'bg-cyan-400 text-slate-950' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'}`}>{label}</button>)}</nav>{content[activeTab]}</div></main>
}
