import { useState } from 'react'
import Chat from './components/Chat'
import Dashboard from './components/Dashboard'

const tabs = [{ id: 'dashboard', label: 'Dashboard' }, { id: 'chat', label: 'Chat' }]

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard')

  return <div className="min-h-screen bg-slate-950">
    <header className="sticky top-0 z-10 border-b border-slate-800 bg-slate-950/90 backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6">
        <div className="flex items-center gap-3"><span className="grid h-9 w-9 place-items-center rounded-lg bg-cyan-400 font-bold text-slate-950">R</span><div><p className="text-sm font-semibold text-white">Roche ATLAS</p><p className="text-xs text-slate-500">ITSM Co-Pilot</p></div></div>
        <nav aria-label="Primary"><div className="flex rounded-lg border border-slate-700 p-1">{tabs.map((tab) => <button key={tab.id} type="button" onClick={() => setActiveTab(tab.id)} aria-current={activeTab === tab.id ? 'page' : undefined} className={`rounded-md px-4 py-2 text-sm font-semibold transition ${activeTab === tab.id ? 'bg-cyan-400 text-slate-950' : 'text-slate-300 hover:text-white'}`}>{tab.label}</button>)}</div></nav>
      </div>
    </header>
    <main>{activeTab === 'dashboard' ? <Dashboard /> : <Chat />}</main>
  </div>
}
