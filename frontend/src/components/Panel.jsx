export function Panel({ eyebrow, title, children, action }) {
  return (
    <section className="rounded-2xl border border-slate-700/80 bg-slate-900/80 p-5 shadow-xl shadow-slate-950/20">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-cyan-300">{eyebrow}</p>
          <h2 className="mt-1 text-xl font-semibold text-white">{title}</h2>
        </div>
        {action}
      </div>
      <div className="mt-5">{children}</div>
    </section>
  )
}

export function Status({ children, tone = 'slate' }) {
  const tones = {
    slate: 'border-slate-600 bg-slate-800 text-slate-200',
    green: 'border-emerald-500/50 bg-emerald-500/10 text-emerald-200',
    amber: 'border-amber-500/50 bg-amber-500/10 text-amber-100',
    red: 'border-rose-500/50 bg-rose-500/10 text-rose-100',
  }
  return <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${tones[tone]}`}>{children}</span>
}

export function ActionButton({ children, className = '', ...props }) {
  return <button className={`rounded-lg bg-cyan-400 px-3 py-2 text-sm font-bold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-50 ${className}`} {...props}>{children}</button>
}
