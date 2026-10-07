import { useEffect, useState } from 'react'
import { fetchDashboardStats } from '../api'

const reportEnd = '2026-10-06'
const reportStart = '2026-07-01'
const trendColors = ['#38bdf8', '#34d399', '#fbbf24', '#a78bfa', '#fb7185', '#22d3ee']

function ChartTooltip({ tooltip }) {
  if (!tooltip) return null
  return <div className="pointer-events-none fixed z-50 w-56 rounded-xl border border-slate-600 bg-slate-950/95 p-3 text-xs text-slate-200 shadow-2xl backdrop-blur" style={{ left: tooltip.x, top: tooltip.y }}><p className="font-semibold text-slate-50">{tooltip.title}</p><p className="mt-1 text-lg font-semibold text-cyan-200">{tooltip.value} tickets <span className="text-xs font-medium text-slate-400">· {tooltip.share}%</span></p>{tooltip.lines?.map((line) => <p key={line} className="mt-1 text-slate-400">{line}</p>)}</div>
}

function StatCard({ label, value, tone = 'slate', detail, onClick }) {
  const tones = {
    rose: 'border-rose-500/35 bg-rose-950/25 text-rose-200',
    amber: 'border-amber-500/35 bg-amber-950/25 text-amber-200',
    blue: 'border-blue-500/35 bg-blue-950/25 text-blue-200',
    violet: 'border-violet-500/35 bg-violet-950/25 text-violet-200',
    emerald: 'border-emerald-500/35 bg-emerald-950/25 text-emerald-200',
    slate: 'border-slate-700 bg-slate-900/70 text-slate-100',
  }
  const content = <><p className="text-xs font-semibold uppercase tracking-wider opacity-75">{label}</p><p className="mt-3 text-3xl font-semibold tracking-tight">{value}</p>{detail && <p className="mt-2 text-xs opacity-75">{detail}</p>}</>
  return onClick ? <button type="button" onClick={onClick} className={`rounded-2xl border p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:brightness-110 focus:outline-none focus:ring-2 focus:ring-cyan-400/60 ${tones[tone]}`}>{content}</button> : <article className={`rounded-2xl border p-4 shadow-sm ${tones[tone]}`}>{content}</article>
}

function DonutChart({ title, subtitle, segments, onSegmentClick }) {
  const [tooltip, setTooltip] = useState(null)
  const total = segments.reduce((sum, segment) => sum + segment.value, 0)
  const circumference = 2 * Math.PI * 46
  let offset = 0
  return <section className="rounded-2xl border border-slate-700 bg-slate-900/70 p-5">
    <div><h2 className="text-base font-semibold">{title}</h2><p className="mt-1 text-sm text-slate-400">{subtitle}</p></div>
    <div className="mt-5 grid gap-5 sm:grid-cols-[150px_1fr] sm:items-center">
      <div className="relative mx-auto h-36 w-36"><svg viewBox="0 0 120 120" className="h-full w-full -rotate-90" role="img" aria-label={`${title}: ${total} tickets`}><circle cx="60" cy="60" r="46" fill="none" stroke="currentColor" strokeWidth="14" className="text-slate-800" />{total > 0 && segments.map((segment) => { const length = (segment.value / total) * circumference; const node = <circle key={segment.label} cx="60" cy="60" r="46" fill="none" stroke={segment.color} strokeWidth="14" strokeLinecap="butt" strokeDasharray={`${length} ${circumference - length}`} strokeDashoffset={-offset} className="cursor-pointer transition-opacity hover:opacity-75" onClick={() => onSegmentClick?.(segment)} onMouseMove={(event) => setTooltip({ x: event.clientX + 14, y: event.clientY + 14, title: segment.label, value: segment.value, share: Math.round((segment.value / total) * 100), lines: [`${title} status · click to inspect`] })} onMouseLeave={() => setTooltip(null)} />; offset += length; return node })}</svg><div className="absolute inset-0 grid place-items-center text-center"><div><p className="text-3xl font-semibold">{total}</p><p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">tickets</p></div></div></div>
      <ul className="space-y-3">{segments.map((segment) => <li key={segment.label}><button type="button" onClick={() => onSegmentClick?.(segment)} className="flex w-full items-center justify-between gap-3 rounded-md text-left text-sm hover:bg-slate-800/60"><span className="flex items-center gap-2 text-slate-300"><span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: segment.color }} />{segment.label}</span><span className="font-mono text-slate-100">{segment.value}</span></button></li>)}</ul>
    </div>
    <ChartTooltip tooltip={tooltip} />
  </section>
}

function RecordTypePipeline({ records = [], onRecordClick }) {
  const [tooltip, setTooltip] = useState(null)
  const maximum = Math.max(1, ...records.map((record) => record.total))
  const total = records.reduce((sum, record) => sum + record.total, 0)
  return <section className="rounded-2xl border border-slate-700 bg-slate-900/70 p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-base font-semibold">ITSM record pipeline</h2><p className="mt-1 text-sm text-slate-400">Incidents, requests, problems, and changes in one operational view. Red markers show SLA-breached records.</p></div><span className="rounded-full border border-rose-500/35 bg-rose-950/30 px-3 py-1 text-xs font-semibold text-rose-200">🚨 SLA visibility</span></div><div className="mt-5 space-y-4">{records.map((record) => <button type="button" key={record.label} onClick={() => onRecordClick?.(record)} className="block w-full rounded-xl border border-slate-700 bg-slate-950/35 p-3 text-left transition hover:border-cyan-400/60 hover:bg-slate-800/60"><div className="flex flex-wrap items-center justify-between gap-3"><div className="flex items-center gap-3"><span className="grid h-9 w-9 place-items-center rounded-lg text-xs font-bold" style={{ backgroundColor: `${record.color}25`, color: record.color }}>{record.label}</span><div><p className="text-sm font-semibold text-slate-100">{record.total} total · {record.active} active</p><p className="mt-0.5 text-xs text-slate-500">{record.closed} resolved / closed · click to inspect</p></div></div><span className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${record.breached ? 'border-rose-500/50 bg-rose-950/50 text-rose-200' : 'border-slate-700 bg-slate-800 text-slate-400'}`}>{record.breached ? `🚨 ${record.breached} breached` : 'No SLA breach'}</span></div><div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-800" onMouseMove={(event) => setTooltip({ x: event.clientX + 14, y: event.clientY + 14, title: `${record.label} pipeline`, value: record.total, share: total ? Math.round((record.total / total) * 100) : 0, lines: [`${record.active} active · ${record.closed} resolved/closed`, `${record.breached} SLA breached`, 'Click to inspect tickets'] })} onMouseLeave={() => setTooltip(null)}><div className="h-full rounded-full" style={{ width: `${(record.total / maximum) * 100}%`, backgroundColor: record.color }} /></div></button>)}</div><ChartTooltip tooltip={tooltip} /></section>
}

function TeamWorkload({ workload = [], onTeamClick }) {
  const [tooltip, setTooltip] = useState(null)
  const maximum = Math.max(1, ...workload.map((team) => team.total))
  const total = workload.reduce((sum, team) => sum + team.total, 0)
  return <section className="rounded-2xl border border-slate-700 bg-slate-900/70 p-5"><div><h2 className="text-base font-semibold">Team workload distribution</h2><p className="mt-1 text-sm text-slate-400">Open workload by selected assignment group, with breaches called out for leadership attention.</p></div><div className="mt-5 space-y-3">{workload.map((team) => <button type="button" key={team.group} onClick={() => onTeamClick?.(team)} className="block w-full rounded-xl border border-slate-700 bg-slate-950/35 p-3 text-left transition hover:border-cyan-400/60 hover:bg-slate-800/60"><div className="flex flex-wrap items-center justify-between gap-3"><p className="text-sm font-medium text-slate-100">{team.group}</p><div className="flex items-center gap-2 text-xs"><span className="rounded-full border border-cyan-500/35 bg-cyan-950/30 px-2 py-1 text-cyan-100">{team.active} active</span>{team.breached > 0 && <span className="rounded-full border border-rose-500/50 bg-rose-950/50 px-2 py-1 font-semibold text-rose-200">🚨 {team.breached} breached</span>}</div></div><div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-800" onMouseMove={(event) => setTooltip({ x: event.clientX + 14, y: event.clientY + 14, title: team.group, value: team.total, share: total ? Math.round((team.total / total) * 100) : 0, lines: [`${team.active} active workload`, `${team.breached} SLA breached`, 'Click to inspect tickets'] })} onMouseLeave={() => setTooltip(null)}><div className="h-full rounded-full bg-cyan-400" style={{ width: `${(team.total / maximum) * 100}%` }} /></div><p className="mt-2 text-xs text-slate-500">{team.total} work items in scope · click to inspect</p></button>)}</div><ChartTooltip tooltip={tooltip} /></section>
}

function TeamSlaOwnership({ teams = [], onTeamStatusClick }) {
  const [tooltip, setTooltip] = useState(null)
  return <section className="rounded-2xl border border-slate-700 bg-slate-900/70 p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="text-base font-semibold">SLA health by assignment group</h2><p className="mt-1 text-sm text-slate-400">Explicit tower-lead accountability for breached and at-risk SLA commitments.</p></div><span className="rounded-full border border-rose-500/35 bg-rose-950/30 px-3 py-1 text-xs font-semibold text-rose-200">Escalation view</span></div><div className="mt-5 space-y-4">{teams.map((team) => { const total = Math.max(1, team.sla_eligible); return <article key={team.group}><div className="mb-2 flex flex-wrap items-center justify-between gap-3"><p className="text-sm font-medium text-slate-100">{team.group}</p><button type="button" onClick={() => onTeamStatusClick?.(team, 'all')} className="text-xs text-slate-400 hover:text-cyan-200">{team.sla_eligible} SLA tracked · inspect</button></div><div className="flex h-3 overflow-hidden rounded-full bg-slate-800"><button type="button" aria-label={`Inspect ${team.group} breached tickets`} className="cursor-pointer bg-rose-500 transition hover:brightness-125" style={{ width: `${(team.breached / total) * 100}%` }} onClick={() => onTeamStatusClick?.(team, 'breached')} onMouseMove={(event) => setTooltip({ x: event.clientX + 14, y: event.clientY + 14, title: `${team.group} · Breached`, value: team.breached, share: Math.round((team.breached / total) * 100), lines: [`${team.at_risk} at risk`, `${team.on_track} on track`, 'Click to inspect tickets'] })} onMouseLeave={() => setTooltip(null)} /><button type="button" aria-label={`Inspect ${team.group} at-risk tickets`} className="cursor-pointer bg-amber-400 transition hover:brightness-125" style={{ width: `${(team.at_risk / total) * 100}%` }} onClick={() => onTeamStatusClick?.(team, 'at_risk')} onMouseMove={(event) => setTooltip({ x: event.clientX + 14, y: event.clientY + 14, title: `${team.group} · At risk`, value: team.at_risk, share: Math.round((team.at_risk / total) * 100), lines: [`${team.breached} breached`, `${team.on_track} on track`, 'Click to inspect tickets'] })} onMouseLeave={() => setTooltip(null)} /><button type="button" aria-label={`Inspect ${team.group} on-track tickets`} className="cursor-pointer bg-emerald-500 transition hover:brightness-125" style={{ width: `${(team.on_track / total) * 100}%` }} onClick={() => onTeamStatusClick?.(team, 'on_track')} onMouseMove={(event) => setTooltip({ x: event.clientX + 14, y: event.clientY + 14, title: `${team.group} · On track`, value: team.on_track, share: Math.round((team.on_track / total) * 100), lines: [`${team.breached} breached`, `${team.at_risk} at risk`, 'Click to inspect tickets'] })} onMouseLeave={() => setTooltip(null)} /></div><div className="mt-2 flex gap-3 text-xs"><button type="button" onClick={() => onTeamStatusClick?.(team, 'breached')} className="text-rose-300 hover:text-rose-100">{team.breached} breached</button><button type="button" onClick={() => onTeamStatusClick?.(team, 'at_risk')} className="text-amber-300 hover:text-amber-100">{team.at_risk} at risk</button><button type="button" onClick={() => onTeamStatusClick?.(team, 'on_track')} className="text-emerald-300 hover:text-emerald-100">{team.on_track} on track</button></div></article>})}</div><ChartTooltip tooltip={tooltip} /></section>
}

function AssigneeCapacityMatrix({ assignees = [], onAssigneeClick }) {
  return <section className="overflow-hidden rounded-2xl border border-slate-700 bg-slate-900/70"><div className="border-b border-slate-700 p-5"><h2 className="text-base font-semibold">Assignee workload &amp; capacity matrix</h2><p className="mt-1 text-sm text-slate-400">Individual active workload, risk exposure, and tower coverage for review calls. Select a row to inspect tickets.</p></div><div className="max-h-[28rem] overflow-auto custom-scrollbar"><table className="min-w-full text-left text-sm"><thead className="sticky top-0 bg-slate-900 text-xs uppercase tracking-wider text-slate-400"><tr><th className="px-4 py-3">Assignee</th><th className="px-4 py-3">Active</th><th className="px-4 py-3">At Risk</th><th className="px-4 py-3">Breached</th><th className="px-4 py-3">Coverage</th></tr></thead><tbody className="divide-y divide-slate-800">{assignees.map((assignee) => <tr key={assignee.assignee} onClick={() => onAssigneeClick?.(assignee)} className="cursor-pointer transition hover:bg-slate-800/50"><td className="px-4 py-3 font-medium text-slate-100">{assignee.assignee}<p className="mt-1 text-xs font-normal text-slate-500">{assignee.total} total work items · inspect</p></td><td className="px-4 py-3 text-cyan-200">{assignee.active}</td><td className="px-4 py-3 text-amber-200">{assignee.at_risk}</td><td className="px-4 py-3"><span className={assignee.breached ? 'font-semibold text-rose-200' : 'text-slate-500'}>{assignee.breached}</span></td><td className="px-4 py-3 text-xs text-slate-300">{assignee.assignment_groups.join(', ')}</td></tr>)}</tbody></table></div></section>
}

function TeamStatusCall({ teams = [], onTeamClick }) {
  return <section className="overflow-hidden rounded-2xl border border-slate-700 bg-slate-900/70"><div className="border-b border-slate-700 p-5"><h2 className="text-base font-semibold">Team status call summary</h2><p className="mt-1 text-sm text-slate-400">Backlog age, resolution velocity, and breach rate to focus leadership intervention. Select a team to inspect tickets.</p></div><div className="max-h-[28rem] overflow-auto custom-scrollbar"><table className="min-w-full text-left text-sm"><thead className="sticky top-0 bg-slate-900 text-xs uppercase tracking-wider text-slate-400"><tr><th className="px-4 py-3">Assignment group</th><th className="px-4 py-3">Open backlog</th><th className="px-4 py-3">Avg. age</th><th className="px-4 py-3">Resolution velocity</th><th className="px-4 py-3">Breach rate</th></tr></thead><tbody className="divide-y divide-slate-800">{teams.map((team) => <tr key={team.group} onClick={() => onTeamClick?.(team)} className="cursor-pointer transition hover:bg-slate-800/50"><td className="px-4 py-3 font-medium text-slate-100">{team.group}</td><td className="px-4 py-3 text-cyan-200">{team.open_backlog}</td><td className="px-4 py-3 text-slate-300">{team.average_backlog_age_days}d</td><td className="px-4 py-3 text-emerald-200">{team.resolution_velocity_pct}%</td><td className="px-4 py-3"><span className={team.breach_rate_pct ? 'font-semibold text-rose-200' : 'text-slate-500'}>{team.breach_rate_pct}%</span><p className="mt-1 text-xs text-slate-500">{team.breached} breached · {team.at_risk} at risk</p></td></tr>)}</tbody></table></div></section>
}

function smoothPath(points) {
  if (!points.length) return ''
  if (points.length === 1) return `M ${points[0].x} ${points[0].y}`
  return points.reduce((path, point, index) => {
    if (index === 0) return `M ${point.x} ${point.y}`
    const previous = points[index - 1]
    const controlX = (previous.x + point.x) / 2
    return `${path} C ${controlX} ${previous.y}, ${controlX} ${point.y}, ${point.x} ${point.y}`
  }, '')
}

function IncidentTrend({ trend, onMonthClick }) {
  const [hoveredIndex, setHoveredIndex] = useState(null)
  const series = trend?.series || []
  const groups = trend?.groups || []
  const width = 760
  const height = 280
  const padding = { top: 22, right: 24, bottom: 42, left: 38 }
  const chartWidth = width - padding.left - padding.right
  const chartHeight = height - padding.top - padding.bottom
  const maxValue = Math.max(1, ...series.flatMap((point) => groups.map((group) => point.groups[group] || 0)))
  const x = (index) => padding.left + (series.length <= 1 ? chartWidth / 2 : index * (chartWidth / (series.length - 1)))
  const y = (value) => padding.top + chartHeight - ((value / maxValue) * chartHeight)
  const hoveredPoint = hoveredIndex === null ? null : series[hoveredIndex]

  return <section className="rounded-2xl border border-slate-700 bg-slate-900/70 p-5"><div className="flex flex-wrap items-start justify-between gap-4"><div><h2 className="text-base font-semibold">Work item volume by assignment group</h2><p className="mt-1 text-sm text-slate-400">All selected INC, RITM, PRB, and CHG records opened during the selected period. Hover a month to inspect each selected group’s count.</p></div><span className="rounded-full border border-cyan-500/35 bg-cyan-950/30 px-3 py-1 text-xs font-semibold text-cyan-200">ServiceNow-style trend</span></div>{series.length && groups.length ? <><div className="mt-5 overflow-x-auto"><svg viewBox={`0 0 ${width} ${height}`} className="min-w-[620px] w-full" role="img" aria-label="Work item trend by assignment group" onMouseLeave={() => setHoveredIndex(null)}>{[0, 0.5, 1].map((step) => <g key={step}><line x1={padding.left} x2={width - padding.right} y1={y(maxValue * step)} y2={y(maxValue * step)} stroke="currentColor" strokeWidth="1" className="text-slate-700" /><text x={padding.left - 9} y={y(maxValue * step) + 4} textAnchor="end" fontSize="11" className="fill-slate-500">{Math.round(maxValue * step)}</text></g>)}{groups.map((group, groupIndex) => { const points = series.map((point, index) => ({ x: x(index), y: y(point.groups[group] || 0) })); return <path key={group} d={smoothPath(points)} fill="none" stroke={trendColors[groupIndex % trendColors.length]} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" /> })}{hoveredPoint && <g pointerEvents="none"><line x1={x(hoveredIndex)} x2={x(hoveredIndex)} y1={padding.top} y2={height - padding.bottom} stroke="currentColor" strokeWidth="1" className="text-slate-500" strokeDasharray="3 4" />{groups.map((group, index) => <circle key={group} cx={x(hoveredIndex)} cy={y(hoveredPoint.groups[group] || 0)} r="4.5" fill={trendColors[index % trendColors.length]} stroke="#0f172a" strokeWidth="2" />)}</g>}{series.map((point, index) => <g key={point.month}><rect x={x(index) - chartWidth / Math.max(2, series.length * 1.8)} y={padding.top} width={chartWidth / Math.max(1, series.length - 1)} height={chartHeight} fill="transparent" className="cursor-pointer" onClick={() => onMonthClick?.(point)} onMouseEnter={() => setHoveredIndex(index)}><title>{`${point.label}: ${groups.map((group) => `${group} ${point.groups[group] || 0}`).join(' · ')} — click to inspect`}</title></rect><text x={x(index)} y={height - 14} textAnchor="middle" fontSize="11" className="fill-slate-500">{point.label}</text></g>)}</svg></div><div className="mt-3 min-h-9 rounded-lg border border-slate-700 bg-slate-950/35 px-3 py-2 text-xs text-slate-300">{hoveredPoint ? <span><span className="font-semibold text-slate-100">{hoveredPoint.label}:</span> {groups.map((group) => `${group} ${hoveredPoint.groups[group] || 0}`).join(' · ')} <span className="text-cyan-200">· click this month to inspect tickets</span></span> : 'Hover over a month to view exact work-item counts; click the month to inspect its tickets.'}</div><div className="mt-3 flex flex-wrap gap-x-5 gap-y-2">{groups.map((group, index) => <span key={group} className="flex items-center gap-2 text-xs text-slate-300"><span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: trendColors[index % trendColors.length] }} />{group}</span>)}</div></> : <p className="mt-6 rounded-lg border border-dashed border-slate-700 p-6 text-center text-sm text-slate-500">No work items match this assignment-group and date range.</p>}</section>
}

export default function Stats({ onDrilldown }) {
  const [stats, setStats] = useState(null)
  // null means “all groups”; it avoids storing an unnecessary duplicate of
  // the backend group catalog before the first response arrives.
  const [selectedGroups, setSelectedGroups] = useState(null)
  const [startDate, setStartDate] = useState(reportStart)
  const [endDate, setEndDate] = useState(reportEnd)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [groupMenuOpen, setGroupMenuOpen] = useState(false)

  useEffect(() => {
    let active = true
    fetchDashboardStats({ assignmentGroups: selectedGroups ? [...selectedGroups] : [], groupFilterActive: selectedGroups !== null, startDate, endDate })
      .then((result) => {
        if (!active) return
        setStats(result)
      })
      .catch((requestError) => active && setError(requestError.message))
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [startDate, endDate, selectedGroups])

  const availableGroups = stats?.available_groups || []
  const effectiveGroups = selectedGroups || new Set(availableGroups)
  const groupList = [...effectiveGroups].sort()
  function toggleGroup(group) { setSelectedGroups((current) => { const next = new Set(current || availableGroups); if (next.has(group)) next.delete(group); else next.add(group); return next }) }
  function selectAllGroups() { setSelectedGroups(new Set(availableGroups)) }
  function deselectAllGroups() { setSelectedGroups(new Set()) }

  const summary = stats?.summary
  const ticketIndex = stats?.ticket_index || []
  const activeStates = new Set(['In Progress', 'Implement', 'Root Cause Analysis', 'Assess', 'Authorize', 'Scheduled', 'Review', 'Fix in Progress', 'Work in Progress'])
  const closedStates = new Set(['Resolved', 'Closed', 'Closed Complete', 'Closed Incomplete', 'Closed Skipped', 'Canceled'])
  function openDrilldown(title, matcher) {
    const matches = ticketIndex.filter(matcher)
    if (!matches.length) return
    onDrilldown?.({
      title,
      ticketIds: matches.map((ticket) => ticket.number),
      assignmentGroups: [...new Set(matches.map((ticket) => ticket.assignment_group).filter(Boolean))],
      assignees: [...new Set(matches.map((ticket) => ticket.assignee).filter(Boolean))],
    })
  }
  const selectionLabel = groupList.length === 0 ? 'No assignment groups selected' : groupList.length === availableGroups.length ? 'All assignment groups' : `${groupList.length} assignment group${groupList.length === 1 ? '' : 's'} selected`
  return <section className="mx-auto max-w-7xl px-4 py-10 sm:px-6">
    <div className="mb-8"><p className="text-sm font-semibold uppercase tracking-[0.2em] text-teal-300">Service operations analytics</p><h1 className="mt-3 text-4xl font-semibold tracking-tight">Service health, at a glance.</h1><p className="mt-3 max-w-3xl text-slate-400">Operational measures are calculated on the backend from the canonical ServiceNow queue and reporting dates—not browser fixture data.</p></div>
    <section className="rounded-2xl border border-slate-700 bg-slate-900/70 p-5"><div className="grid gap-5 lg:grid-cols-[1fr_auto_auto]"><div className="relative"><div className="flex items-center justify-between gap-3"><p className="text-xs font-semibold uppercase tracking-wider text-slate-400">Assignment groups</p><div className="flex gap-3"><button type="button" onClick={selectAllGroups} className="text-xs font-semibold text-cyan-300 hover:text-cyan-100">Select all</button><button type="button" onClick={deselectAllGroups} className="text-xs font-semibold text-slate-400 hover:text-slate-100">Deselect all</button></div></div><button type="button" onClick={() => setGroupMenuOpen((open) => !open)} aria-expanded={groupMenuOpen} className="mt-3 flex w-full items-center justify-between rounded-lg border border-slate-600 bg-slate-950 px-3 py-2.5 text-left text-sm text-slate-100 hover:border-cyan-400/70"><span>{selectionLabel}</span><span className="text-cyan-300">⌄</span></button>{groupMenuOpen && <div className="absolute z-20 mt-2 max-h-64 w-full overflow-y-auto rounded-xl border border-slate-700 bg-slate-900 p-2 shadow-2xl shadow-slate-950/50 custom-scrollbar">{availableGroups.map((group) => <label key={group} className="flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2 text-sm text-slate-200 hover:bg-slate-800"><input type="checkbox" checked={effectiveGroups.has(group)} onChange={() => toggleGroup(group)} className="h-4 w-4 accent-cyan-400" />{group}</label>)}</div>}<div className="mt-3 flex flex-wrap gap-2">{groupList.map((group) => <span key={group} className="rounded-full border border-cyan-500/35 bg-cyan-950/25 px-2.5 py-1 text-xs text-cyan-100">{group}</span>)}{groupList.length === 0 && <span className="text-xs text-amber-200">Select one or more groups to populate the executive view.</span>}</div></div><label className="text-sm text-slate-300">From<input type="date" value={startDate} max={endDate} onChange={(event) => setStartDate(event.target.value)} className="mt-2 block rounded-lg border border-slate-600 bg-slate-950 px-3 py-2 text-slate-100" /></label><label className="text-sm text-slate-300">To<input type="date" value={endDate} min={startDate} onChange={(event) => setEndDate(event.target.value)} className="mt-2 block rounded-lg border border-slate-600 bg-slate-950 px-3 py-2 text-slate-100" /></label></div></section>
    {error && <p className="mt-5 rounded-xl border border-rose-500/40 bg-rose-950/30 p-4 text-rose-200">Unable to load operational statistics: {error}</p>}
    {loading && !stats ? <p className="mt-5 rounded-xl border border-slate-700 p-6 text-slate-400">Loading ServiceNow operational metrics…</p> : stats && <>
      <section className="mt-7">
        <div className="mb-3 flex items-center justify-between"><h2 className="text-sm font-semibold uppercase tracking-wider text-slate-300">Executive status</h2><span className="text-xs text-slate-500">Select any metric to inspect matching tickets</span></div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4 2xl:grid-cols-5">
          <StatCard label="Total scope" value={summary.total_tickets} detail="All ITSM types" onClick={() => openDrilldown('All tickets in the selected Stats scope', () => true)} />
          <StatCard label="SLA breached" value={summary.breached} tone="rose" detail="Leadership attention" onClick={() => openDrilldown('SLA-breached tickets', (ticket) => ticket.is_breached)} />
          <StatCard label="In progress" value={summary.in_progress} tone="emerald" onClick={() => openDrilldown('In-progress tickets', (ticket) => activeStates.has(ticket.state))} />
          <StatCard label="On hold" value={summary.on_hold} tone="amber" onClick={() => openDrilldown('On-hold tickets', (ticket) => ticket.state === 'On Hold')} />
          <StatCard label="Awaiting caller" value={summary.awaiting_caller} tone="amber" onClick={() => openDrilldown('On-hold tickets awaiting caller', (ticket) => ticket.state === 'On Hold' && ticket.hold_reason === 'Awaiting Caller')} />
          <StatCard label="Awaiting change" value={summary.awaiting_change} tone="blue" onClick={() => openDrilldown('On-hold tickets awaiting change', (ticket) => ticket.state === 'On Hold' && ticket.hold_reason === 'Awaiting Change')} />
          <StatCard label="Awaiting child" value={summary.awaiting_child} tone="violet" onClick={() => openDrilldown('On-hold tickets awaiting child', (ticket) => ticket.state === 'On Hold' && ticket.hold_reason === 'Awaiting Child')} />
          <StatCard label="Awaiting vendor" value={summary.awaiting_vendor} tone="rose" onClick={() => openDrilldown('On-hold tickets awaiting vendor', (ticket) => ticket.state === 'On Hold' && ticket.hold_reason === 'Awaiting Vendor')} />
          <StatCard label="Awaiting problem" value={summary.awaiting_problem} tone="blue" onClick={() => openDrilldown('On-hold tickets awaiting problem', (ticket) => ticket.state === 'On Hold' && ticket.hold_reason === 'Awaiting Problem')} />
          <StatCard label="Awaiting parent" value={summary.awaiting_parent} tone="slate" onClick={() => openDrilldown('On-hold tickets awaiting parent', (ticket) => ticket.state === 'On Hold' && ticket.hold_reason === 'Awaiting Parent')} />
        </div>
      </section>
      <div className="mt-6"><RecordTypePipeline records={stats.record_type_pipeline} onRecordClick={(record) => openDrilldown(`${record.label} records`, (ticket) => ticket.type === record.label)} /></div>
      <div className="mt-6 grid gap-6 xl:grid-cols-2">
        <DonutChart title="SLA health" subtitle="Breaches remain visible alongside at-risk and on-track SLA records." segments={stats.sla_health_breakdown} onSegmentClick={(segment) => openDrilldown(`SLA health · ${segment.label}`, (ticket) => (segment.label === 'Breached' ? ticket.is_breached : segment.label === 'At risk' ? !ticket.is_breached && ticket.sla_health === 'YELLOW' : segment.label === 'On track' ? ticket.sla_health === 'GREEN' : ['PRB', 'CHG'].includes(ticket.type)))} />
        <DonutChart title="SLA breaches by record type" subtitle="Shows the record mix behind breached SLA commitments." segments={stats.breach_by_type} onSegmentClick={(segment) => openDrilldown(`Breached ${segment.label} tickets`, (ticket) => ticket.is_breached && ticket.type === segment.label)} />
        <DonutChart title="Workflow pipeline" subtitle="Operational state distribution across all selected ITSM record types." segments={stats.pipeline_state_breakdown} onSegmentClick={(segment) => openDrilldown(`Workflow · ${segment.label}`, (ticket) => segment.label === 'Open / Active' ? activeStates.has(ticket.state) : segment.label === 'On hold' ? ticket.state === 'On Hold' : closedStates.has(ticket.state))} />
        <DonutChart title="Awaiting dependency mix" subtitle="On-hold work, grouped strictly by the ServiceNow hold reason." segments={stats.awaiting_breakdown} onSegmentClick={(segment) => openDrilldown(`On Hold · ${segment.label}`, (ticket) => ticket.state === 'On Hold' && ticket.hold_reason === segment.label)} />
      </div>
      <div className="mt-6 grid gap-6 xl:grid-cols-2">
        <TeamSlaOwnership teams={stats.team_sla_health} onTeamStatusClick={(team, status) => openDrilldown(`${team.group} · ${status.replace('_', ' ')}`, (ticket) => ticket.assignment_group === team.group && (status === 'all' || status === 'breached' && ticket.is_breached || status === 'at_risk' && !ticket.is_breached && ticket.sla_health === 'YELLOW' || status === 'on_track' && ticket.sla_health === 'GREEN'))} />
        <TeamWorkload workload={stats.team_workload} onTeamClick={(team) => openDrilldown(`${team.group} workload`, (ticket) => ticket.assignment_group === team.group)} />
      </div>
      <div className="mt-6"><IncidentTrend trend={stats.work_item_trend} onMonthClick={(point) => openDrilldown(`Work items opened in ${point.label}`, (ticket) => ticket.opened_on?.startsWith(point.month.slice(0, 7)))} /></div>
      <div className="mt-6 grid gap-6 2xl:grid-cols-2">
        <AssigneeCapacityMatrix assignees={stats.assignee_workload} onAssigneeClick={(assignee) => openDrilldown(`${assignee.assignee} workload`, (ticket) => ticket.assignee === assignee.assignee)} />
        <TeamStatusCall teams={stats.team_status_call} onTeamClick={(team) => openDrilldown(`${team.group} status call`, (ticket) => ticket.assignment_group === team.group)} />
      </div>
      <p className="mt-4 text-xs text-slate-500">Reporting window: {stats.filters.start_date} to {stats.filters.end_date}. Every KPI and chart reflects the assignment groups currently selected above.</p>
    </>}</section>
}
