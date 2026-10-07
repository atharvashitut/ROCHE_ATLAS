import { useEffect, useState } from 'react'
import Chat from './components/Chat'
import Dashboard from './components/Dashboard'
import Stats from './components/Stats'

const tabs = [{ id: 'stats', label: 'Stats' }, { id: 'dashboard', label: 'Dashboard' }, { id: 'chat', label: 'Chat' }]

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard')
  const [dashboardDrilldown, setDashboardDrilldown] = useState(null)
  const [theme, setTheme] = useState(() => window.localStorage.getItem('roche-atlas-theme') || 'light')

  useEffect(() => {
    window.localStorage.setItem('roche-atlas-theme', theme)
  }, [theme])

  const lightTheme = theme === 'light'
  return <div className={`${lightTheme ? 'monday-theme apple-shell bg-[#f3f2ee]' : 'dark-theme bg-slate-950'} min-h-screen`}>
    <header className={`${lightTheme ? 'apple-nav border-[#d8d8d2] bg-[#faf9f6]' : 'dark-nav border-slate-800 bg-slate-950/90'} sticky top-0 z-10 border-b shadow-sm`}>
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6">
        <div className="flex items-center gap-3"><span className={`${lightTheme ? 'apple-mark bg-[#2563a8] rounded-xl text-white shadow-sm' : 'rounded-lg bg-blue-600 text-white'} grid h-9 w-9 place-items-center font-bold`}>R</span><div><p className={`text-sm font-semibold ${lightTheme ? 'text-[#30323a]' : 'text-white'}`}>Roche ATLAS</p><p className={`text-xs ${lightTheme ? 'text-[#6b6f7a]' : 'text-slate-500'}`}>ITSM Co-Pilot</p></div></div>
        <div className="flex items-center gap-3"><div className="appearance-switch" role="group" aria-label="Appearance"><button type="button" onClick={() => setTheme('light')} aria-pressed={lightTheme} className={lightTheme ? 'is-active' : ''}>Light</button><button type="button" onClick={() => setTheme('dark')} aria-pressed={!lightTheme} className={!lightTheme ? 'is-active' : ''}>Dark</button></div><nav aria-label="Primary"><div className={`${lightTheme ? 'apple-nav-tabs rounded-xl border-[#d6d9e0] bg-[#eff0f2]' : 'rounded-lg border-slate-700'} flex border p-1`}>{tabs.map((tab) => <button key={tab.id} type="button" onClick={() => setActiveTab(tab.id)} aria-current={activeTab === tab.id ? 'page' : undefined} className={`rounded-md px-4 py-2 text-sm font-semibold transition ${activeTab === tab.id ? (lightTheme ? 'monday-primary' : 'bg-blue-600 text-white') : (lightTheme ? 'text-[#6b6f7a] hover:bg-[#faf9f6] hover:text-[#30323a]' : 'text-slate-300 hover:text-white')}`}>{tab.label}</button>)}</div></nav></div>
      </div>
    </header>
    <main><div className={activeTab === 'stats' ? 'block' : 'hidden'}><Stats onDrilldown={(drilldown) => { setDashboardDrilldown(drilldown); setActiveTab('dashboard') }} /></div><div className={activeTab === 'dashboard' ? 'block' : 'hidden'}><Dashboard drilldown={dashboardDrilldown} onReturnToStats={() => { setDashboardDrilldown(null); setActiveTab('stats') }} onClearDrilldown={() => setDashboardDrilldown(null)} /></div><div className={activeTab === 'chat' ? 'block' : 'hidden'}><Chat /></div></main>
  </div>
}
