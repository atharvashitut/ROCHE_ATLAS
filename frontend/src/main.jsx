import React from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'

function App() {
  return (
    <main className="min-h-screen bg-slate-950 p-8 text-slate-100">
      <section className="mx-auto max-w-3xl rounded-xl border border-slate-700 bg-slate-900 p-8 shadow-2xl">
        <p className="text-sm font-semibold uppercase tracking-widest text-cyan-300">ITSM Copilot</p>
        <h1 className="mt-3 text-3xl font-bold">L2 Knowledge & Triage</h1>
        <p className="mt-3 text-slate-300">Upload an incident screenshot to find an approved knowledge document and produce a resolution or escalation draft.</p>
        <div className="mt-8 rounded-lg border border-dashed border-slate-600 p-10 text-center text-slate-400">Screenshot workflow is ready for API integration.</div>
      </section>
    </main>
  )
}

createRoot(document.getElementById('root')).render(<React.StrictMode><App /></React.StrictMode>)
