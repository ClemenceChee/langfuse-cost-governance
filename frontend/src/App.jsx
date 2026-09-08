import { useEffect, useMemo, useState } from 'react'
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, Line, LineChart,
  ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { api } from './api.js'
import Deployments from './Deployments.jsx'
import Metrics from './Metrics.jsx'

const PALETTE = ['#4f8cff', '#38c172', '#f5a623', '#e5534b', '#9b6dff', '#22c1c3', '#ff7eb6']

const fmtUSD = (v) =>
  v == null ? '—' : `$${Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 })}`

const fmtNum = (v) => {
  if (v == null) return '—'
  const n = Number(v)
  if (Math.abs(n) >= 1e9) return `${(n / 1e9).toFixed(2)}B`
  if (Math.abs(n) >= 1e6) return `${(n / 1e6).toFixed(2)}M`
  if (Math.abs(n) >= 1e3) return `${(n / 1e3).toFixed(1)}k`
  return `${n}`
}

const fmtPct = (v) => (v == null ? '—' : `${(Number(v) * 100).toFixed(1)}%`)

const fmtDuration = (ms) => {
  if (ms == null) return '—'
  const s = Math.round(Number(ms) / 1000)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ${s % 60}s`
  const h = Math.floor(m / 60)
  return `${h}h ${m % 60}m`
}

function Kpi({ label, value, sub }) {
  return (
    <div className="card kpi">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {sub ? <div className="kpi-sub">{sub}</div> : null}
    </div>
  )
}

function pivotDaily(rows) {
  const byDay = {}
  const totals = {}
  for (const r of rows) {
    byDay[r.day] = byDay[r.day] || { day: r.day }
    byDay[r.day][r.label] = r.total_cost
    totals[r.label] = (totals[r.label] || 0) + r.total_cost
  }
  const labels = Object.keys(totals)
    .sort((a, b) => totals[b] - totals[a])
    .slice(0, 6)
  const series = Object.values(byDay).sort((a, b) => a.day.localeCompare(b.day))
  return { labels, series }
}

function pivotByModel(rows, metric) {
  const byDay = {}
  const totals = {}
  for (const r of rows) {
    byDay[r.day] = byDay[r.day] || { day: r.day }
    byDay[r.day][r.model] = r[metric]
    totals[r.model] = (totals[r.model] || 0) + (r.total_cost || 0)
  }
  const labels = Object.keys(totals).sort((a, b) => totals[b] - totals[a]).slice(0, 5)
  const series = Object.values(byDay).sort((a, b) => a.day.localeCompare(b.day))
  return { labels, series }
}

function hourlyByHour(rows) {
  const byHour = {}
  for (const r of rows) {
    const h = (r.hour || '').slice(11, 13)
    byHour[h] = (byHour[h] || 0) + (r.total_cost || 0)
  }
  return Array.from({ length: 24 }, (_, i) => {
    const h = String(i).padStart(2, '0')
    return { hour: `${h}:00`, cost: Math.round((byHour[h] || 0) * 100) / 100 }
  })
}

export default function App() {
  const [overview, setOverview] = useState(null)
  const [governance, setGovernance] = useState(null)
  const [behaviour, setBehaviour] = useState(null)
  const [efficiency, setEfficiency] = useState([])
  const [sessions, setSessions] = useState(null)
  const [anomalies, setAnomalies] = useState(null)
  const [quality, setQuality] = useState(null)
  const [burndown, setBurndown] = useState(null)
  const [targets, setTargets] = useState([])
  const [modelDaily, setModelDaily] = useState([])
  const [hourly, setHourly] = useState([])
  const [cohort, setCohort] = useState([])
  const [effMetric, setEffMetric] = useState('cost_per_1k_tokens')
  const [daily, setDaily] = useState([])
  const [top, setTop] = useState([])
  const [dimension, setDimension] = useState('project')
  const [topDim, setTopDim] = useState('user')
  const [view, setView] = useState('dashboard')
  const [error, setError] = useState(null)

  useEffect(() => {
    Promise.all([
      api.overview(), api.governance(), api.efficiency(), api.sessions(),
      api.anomalies(), api.quality(), api.burndown(), api.modelDaily(),
      api.hourly(), api.cohort(), api.targets(), api.behaviour(),
    ])
      .then(([o, g, e, s, a, q, b, md, h, c, t, bh]) => {
        setOverview(o)
        setGovernance(g)
        setEfficiency(e)
        setSessions(s)
        setAnomalies(a)
        setQuality(q)
        setBurndown(b)
        setModelDaily(md)
        setHourly(h)
        setCohort(c)
        setTargets(t)
        setBehaviour(bh)
      })
      .catch((e) => setError(e.message))
  }, [])

  useEffect(() => {
    api.daily(dimension, 30).then(setDaily).catch((e) => setError(e.message))
  }, [dimension])

  useEffect(() => {
    api.top(topDim, 'cost', 30, 10).then(setTop).catch((e) => setError(e.message))
  }, [topDim])

  const trend = useMemo(() => pivotDaily(daily), [daily])
  const effTrend = useMemo(() => pivotByModel(modelDaily, effMetric), [modelDaily, effMetric])
  const hourlyBars = useMemo(() => hourlyByHour(hourly), [hourly])
  const wowDelta = overview?.wow_cost_pct

  const EFF_METRICS = {
    cost_per_1k_tokens: 'Cost / 1k tokens',
    cache_hit_rate: 'Cache hit rate',
    reasoning_share: 'Reasoning share',
    output_input_ratio: 'Out : In ratio',
  }

  return (
    <div className="app">
      <header>
        <h1>AI Cost &amp; Governance Analytics</h1>
        <p>Token telemetry, cost attribution, and efficiency KPIs — powered by Langfuse traces.</p>
        <nav className="tabs">
          <button className={view === 'dashboard' ? 'tab active' : 'tab'} onClick={() => setView('dashboard')}>Dashboard</button>
          <button className={view === 'metrics' ? 'tab active' : 'tab'} onClick={() => setView('metrics')}>Metrics reference</button>
          <button className={view === 'deployments' ? 'tab active' : 'tab'} onClick={() => setView('deployments')}>Deployment</button>
        </nav>
      </header>

      {error ? <div className="error">{error} — is the API up and the warehouse seeded?</div> : null}

      {view === 'deployments' ? (
        <Deployments />
      ) : view === 'metrics' ? (
        <Metrics />
      ) : !overview ? (
        <div className="loading">Loading…</div>
      ) : (
        <>
          <div className="kpi-row">
            <Kpi label="Cost (MTD)" value={fmtUSD(overview.cost_mtd)}
                 sub={wowDelta == null ? null :
                   <span className={wowDelta >= 0 ? 'delta-up' : 'delta-down'}>
                     {wowDelta >= 0 ? '▲' : '▼'} {Math.abs(wowDelta)}% vs prior 7d
                   </span>} />
            <Kpi label="Tokens (MTD)" value={fmtNum(overview.tokens_mtd)}
                 sub={`${fmtNum(overview.input_tokens_mtd)} in / ${fmtNum(overview.output_tokens_mtd)} out`} />
            <Kpi label="Cost / 1k tokens" value={fmtUSD(overview.cost_per_1k_tokens)} />
            <Kpi label="Cache hit rate" value={fmtPct(overview.cache_hit_rate)} sub="prompt-cache reads" />
            <Kpi label="Active users" value={overview.active_users_mtd} sub={`${fmtNum(overview.observations_mtd)} calls`} />
            <Kpi label="Out : In ratio" value={overview.output_input_ratio == null ? '—' : Number(overview.output_input_ratio).toFixed(2)}
                 sub="output ÷ input tokens" />
            <Kpi label="Cost / dev (MTD)" value={fmtUSD(overview.cost_per_active_dev)} />
            <Kpi label="Cost / session (MTD)" value={fmtUSD(overview.avg_cost_per_session)} sub="cost-per-outcome proxy" />
          </div>

          <section className="section">
            <h2>Budget burn-down</h2>
            <div className="card">
              <div className="kpi-row">
                <Kpi label="Cumulative (MTD)" value={fmtUSD(burndown?.cumulative)} sub={`${burndown?.days_elapsed ?? '—'} days elapsed`} />
                <Kpi label="Projected month-end" value={fmtUSD(burndown?.projected_end)}
                     sub={burndown?.over_budget ? <span className="delta-up">over budget</span> : <span className="delta-down">under budget</span>} />
                <Kpi label="Budget" value={fmtUSD(burndown?.budget)} />
              </div>
              <ResponsiveContainer width="100%" height={240} style={{ marginTop: 12 }}>
                <AreaChart data={burndown?.days || []} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
                  <CartesianGrid stroke="#262e3d" strokeDasharray="3 3" />
                  <XAxis dataKey="day" tick={{ fill: '#8a93a6', fontSize: 11 }} minTickGap={28} />
                  <YAxis tick={{ fill: '#8a93a6', fontSize: 11 }} tickFormatter={(v) => `$${v}`} />
                  <Tooltip contentStyle={{ background: '#1d2330', border: '1px solid #262e3d', borderRadius: 8 }} formatter={(v) => fmtUSD(v)} />
                  <ReferenceLine y={burndown?.budget} stroke="#e5534b" strokeDasharray="4 4" label={{ value: 'budget', fill: '#e5534b', fontSize: 11, position: 'insideTopRight' }} />
                  <Area type="monotone" dataKey="cumulative" stroke="#38c172" fill="#38c172" fillOpacity={0.25} name="cumulative" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </section>

          <section className="section">
            <h2>Cost trend — by {dimension}</h2>
            <div className="controls">
              <label>Breakdown</label>
              <select value={dimension} onChange={(e) => setDimension(e.target.value)}>
                <option value="project">Project</option>
                <option value="team">Team</option>
                <option value="user">User</option>
                <option value="model">Model</option>
              </select>
            </div>
            <div className="card">
              <ResponsiveContainer width="100%" height={300}>
                <AreaChart data={trend.series} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
                  <CartesianGrid stroke="#262e3d" strokeDasharray="3 3" />
                  <XAxis dataKey="day" tick={{ fill: '#8a93a6', fontSize: 11 }} minTickGap={28} />
                  <YAxis tick={{ fill: '#8a93a6', fontSize: 11 }} tickFormatter={(v) => `$${v}`} />
                  <Tooltip
                    contentStyle={{ background: '#1d2330', border: '1px solid #262e3d', borderRadius: 8 }}
                    formatter={(v) => fmtUSD(v)}
                  />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  {trend.labels.map((l, i) => (
                    <Area key={l} type="monotone" dataKey={l} stackId="1"
                          stroke={PALETTE[i % PALETTE.length]} fill={PALETTE[i % PALETTE.length]} fillOpacity={0.25} />
                  ))}
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </section>

          <section className="section">
            <h2>Top spend — by {topDim}</h2>
            <div className="controls">
              <label>Group</label>
              <select value={topDim} onChange={(e) => setTopDim(e.target.value)}>
                <option value="user">User</option>
                <option value="team">Team</option>
                <option value="project">Project</option>
                <option value="model">Model</option>
              </select>
            </div>
            <div className="card">
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={top} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
                  <CartesianGrid stroke="#262e3d" strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" tick={{ fill: '#8a93a6', fontSize: 11 }} tickFormatter={(v) => `$${v}`} />
                  <YAxis type="category" dataKey="label" width={120} tick={{ fill: '#8a93a6', fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{ background: '#1d2330', border: '1px solid #262e3d', borderRadius: 8 }}
                    formatter={(v) => fmtUSD(v)}
                  />
                  <Bar dataKey="total_cost" fill="#4f8cff" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </section>

          <section className="section">
            <h2>Model efficiency</h2>
            <div className="card" style={{ overflowX: 'auto' }}>
              <table>
                <thead>
                  <tr>
                    <th>Model</th>
                    <th>Total cost</th>
                    <th>Tokens</th>
                    <th>Cache hit</th>
                    <th>Reasoning share</th>
                    <th>Out/In ratio</th>
                    <th>Cost / 1k</th>
                    <th>Avg latency</th>
                  </tr>
                </thead>
                <tbody>
                  {efficiency.map((m) => (
                    <tr key={m.model}>
                      <td>{m.model}</td>
                      <td className="num">{fmtUSD(m.total_cost)}</td>
                      <td className="num">{fmtNum(m.input_tokens + m.output_tokens)}</td>
                      <td className="num">{fmtPct(m.cache_hit_rate)}</td>
                      <td className="num">{fmtPct(m.reasoning_share)}</td>
                      <td className="num">{m.output_input_ratio ?? '—'}</td>
                      <td className="num">{fmtUSD(m.cost_per_1k_tokens)}</td>
                      <td className="num">{m.avg_latency_ms ? `${Math.round(m.avg_latency_ms)}ms` : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="section">
            <h2>Efficiency trend</h2>
            <div className="controls">
              <label>Metric</label>
              <select value={effMetric} onChange={(e) => setEffMetric(e.target.value)}>
                {Object.entries(EFF_METRICS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </div>
            <div className="card">
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={effTrend.series} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
                  <CartesianGrid stroke="#262e3d" strokeDasharray="3 3" />
                  <XAxis dataKey="day" tick={{ fill: '#8a93a6', fontSize: 11 }} minTickGap={28} />
                  <YAxis tick={{ fill: '#8a93a6', fontSize: 11 }} />
                  <Tooltip contentStyle={{ background: '#1d2330', border: '1px solid #262e3d', borderRadius: 8 }} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  {effTrend.labels.map((l, i) => (
                    <Line key={l} type="monotone" dataKey={l} stroke={PALETTE[i % PALETTE.length]} dot={false} />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </section>

          <section className="section">
            <h2>Hourly usage (last 7d)</h2>
            <div className="card">
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={hourlyBars} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
                  <CartesianGrid stroke="#262e3d" strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="hour" tick={{ fill: '#8a93a6', fontSize: 10 }} interval={2} />
                  <YAxis tick={{ fill: '#8a93a6', fontSize: 11 }} tickFormatter={(v) => `$${v}`} />
                  <Tooltip contentStyle={{ background: '#1d2330', border: '1px solid #262e3d', borderRadius: 8 }} formatter={(v) => fmtUSD(v)} />
                  <Bar dataKey="cost" fill="#4f8cff" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </section>

          <section className="section">
            <h2>Sessions — context &amp; turns</h2>
            <div className="kpi-row">
              <Kpi label="Sessions (30d)" value={sessions?.stats?.sessions ?? '—'} />
              <Kpi label="Avg context / session" value={fmtNum(sessions?.stats?.avg_context_tokens)} sub="input tokens" />
              <Kpi label="Avg turns / session" value={sessions?.stats?.avg_turns} />
              <Kpi label="Avg input / turn" value={fmtNum(sessions?.stats?.avg_input_per_turn)} sub="context growth per turn" />
              <Kpi label="Avg cost / session" value={fmtUSD(sessions?.stats?.avg_cost)} sub="cost-per-outcome proxy" />
            </div>
            <div className="card" style={{ overflowX: 'auto', marginTop: 12 }}>
              <table>
                <thead>
                  <tr>
                    <th>Session</th><th>User</th><th>Project</th><th>Turns</th>
                    <th>Context (in)</th><th>Out</th><th>In/turn</th><th>Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {(sessions?.top || []).map((s) => (
                    <tr key={s.session_id}>
                      <td style={{ fontFamily: 'monospace' }}>{s.session_id}</td>
                      <td>{s.user_id}</td>
                      <td>{s.project_name}</td>
                      <td className="num">{s.turns}</td>
                      <td className="num">{fmtNum(s.input_tokens)}</td>
                      <td className="num">{fmtNum(s.output_tokens)}</td>
                      <td className="num">{fmtNum(s.input_per_turn)}</td>
                      <td className="num">{fmtUSD(s.total_cost)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="section">
            <h2>Cost anomalies</h2>
            <div className="card">
              <div className="kpi-row">
                <Kpi label="Latest day vs 14-day avg"
                     value={anomalies?.latest == null ? '—' : `${(anomalies.latest.pct_change * 100).toFixed(1)}%`}
                     sub={`${anomalies?.latest?.day} — ${fmtUSD(anomalies?.latest?.cost)} vs ${fmtUSD(anomalies?.latest?.baseline)}`} />
                <Kpi label="Anomalies (30d)" value={(anomalies?.anomalies || []).length}
                     sub={`days above ${((anomalies?.threshold ?? 1.5) * 100).toFixed(0)}% of baseline`} />
              </div>
              {(anomalies?.anomalies?.length > 0) ? (
                <table style={{ marginTop: 12 }}>
                  <thead>
                    <tr><th>Day</th><th>Cost</th><th>Baseline (14d)</th><th>Δ</th></tr>
                  </thead>
                  <tbody>
                    {[...anomalies.anomalies].reverse().slice(0, 10).map((a) => (
                      <tr key={a.day}>
                        <td>{a.day}</td>
                        <td className="num">{fmtUSD(a.cost)}</td>
                        <td className="num">{fmtUSD(a.baseline)}</td>
                        <td className="num delta-up">{`+${(a.pct_change * 100).toFixed(1)}%`}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : <p className="muted" style={{ marginTop: 12, fontSize: 13 }}>No anomalous days in the window.</p>}
            </div>
          </section>

          <section className="section">
            <h2>Governance</h2>
            <div className="card">
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                <span className="muted" style={{ fontSize: 13 }}>Monthly budget burn</span>
                <span style={{ fontSize: 13 }}>
                  {fmtUSD(governance.mtd_cost)} / {fmtUSD(governance.monthly_budget)}
                  {' '}({governance.burn_rate == null ? '—' : `${(governance.burn_rate * 100).toFixed(1)}%`})
                </span>
              </div>
              <BurnBar rate={governance.burn_rate} />
              <div style={{ display: 'flex', gap: 24, marginTop: 16, flexWrap: 'wrap' }}>
                <Kpi label="Unattributed spend" value={fmtPct(governance.unattributed_pct)}
                     sub={`${fmtUSD(governance.unattributed_cost)} with no team owner`} />
                <Kpi label="Spend concentration" value={fmtPct(governance.concentration_top5_pct)}
                     sub="top 5 users (30d) share of spend" />
                <Kpi label="Active users" value={governance.active_users} />
              </div>
            </div>
          </section>

          <section className="section">
            <h2>Behaviour governance</h2>
            <div className="card">
              <div className="kpi-row">
                <Kpi label="Ratified policies" value={(behaviour?.policies || []).length}
                     sub="active canon rules" />
                <Kpi label="Time to first policy (TTRP)" value={fmtDuration(behaviour?.metrics?.ttrp_ms)}
                     sub="connect → first ratified policy" />
                <Kpi label="Precision@14" value={fmtPct(behaviour?.metrics?.precision14?.ratio)}
                     sub={`${behaviour?.metrics?.precision14?.numerator ?? '—'} / ${behaviour?.metrics?.precision14?.denominator ?? '—'} ratified within 14d`} />
                <Kpi label="Proposal queue" value={behaviour?.metrics?.proposals?.pending ?? '—'}
                     sub={`${behaviour?.metrics?.proposals?.total ?? '—'} total · ${behaviour?.metrics?.proposals?.ratified ?? '—'} ratified · ${behaviour?.metrics?.proposals?.rejected ?? '—'} rejected`} />
              </div>

              {(behaviour?.policies || []).length > 0 ? (
                <table style={{ marginTop: 12 }}>
                  <thead>
                    <tr><th>Rule key</th><th>Kind</th><th>Confidence</th><th>Evidence</th><th>Operator</th><th>Promoted</th></tr>
                  </thead>
                  <tbody>
                    {behaviour.policies.map((p) => (
                      <tr key={p.rule_key}>
                        <td style={{ fontFamily: 'monospace' }}>{p.rule_key}</td>
                        <td>{p.kind}</td>
                        <td className="num">{fmtPct(p.confidence)}</td>
                        <td className="num">{p.evidence_traces} traces</td>
                        <td>{p.operator}</td>
                        <td>{(p.promoted_at || '').slice(0, 10)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p className="muted" style={{ marginTop: 12, fontSize: 13 }}>
                  No ratified policies yet — run <code className="mono">canon export --format json</code> and the canon-ingest sidecar.
                </p>
              )}

              {(behaviour?.divergence || []).length > 0 ? (
                <table style={{ marginTop: 12 }}>
                  <thead>
                    <tr><th>Model</th><th>Task</th><th>Divergent traces</th><th>Total traces</th><th>Divergence</th></tr>
                  </thead>
                  <tbody>
                    {behaviour.divergence.map((d, i) => (
                      <tr key={i}>
                        <td>{d.model}</td>
                        <td style={{ fontFamily: 'monospace' }}>{d.task_key}</td>
                        <td className="num">{d.divergent_traces}</td>
                        <td className="num">{d.total_traces}</td>
                        <td className="num">{fmtPct(d.total_traces ? d.divergent_traces / d.total_traces : null)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : null}
            </div>
          </section>

          <section className="section">
            <h2>Targets &amp; policy</h2>
            <div className="card">
              <table>
                <thead>
                  <tr><th>Target</th><th>Current</th><th>Threshold</th><th>Status</th></tr>
                </thead>
                <tbody>
                  {targets.map((t) => {
                    const isRatio = ['cache_hit_rate', 'output_input_ratio', 'reasoning_share', 'burn_rate'].includes(t.metric)
                    const cur = isRatio ? fmtPct(t.current) : fmtUSD(t.current)
                    const thr = isRatio ? fmtPct(t.threshold) : fmtUSD(t.threshold)
                    return (
                      <tr key={t.metric}>
                        <td>{t.label}</td>
                        <td className="num">{cur}</td>
                        <td className="num">{t.op === 'gte' ? '≥' : '≤'} {thr}</td>
                        <td className="num">
                          {t.pass == null ? '—' : t.pass
                            ? <span className="delta-down">✓ pass</span>
                            : <span className="delta-up">✗ fail</span>}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </section>

          <section className="section">
            <h2>Quality — cost per successful outcome</h2>
            <div className="card">
              <div className="kpi-row">
                <Kpi label="Pass rate" value={fmtPct(quality?.pass_rate)}
                     sub={`${quality?.passing_traces ?? '—'} of ${quality?.scored_traces ?? '—'} scored traces pass (≥ ${quality?.threshold ?? 0.5})`} />
                <Kpi label="Cost / success" value={fmtUSD(quality?.cost_per_success)}
                     sub="cost of passing traces ÷ passing traces" />
                <Kpi label="Cost / scored trace" value={fmtUSD(quality?.cost_per_scored_trace)} />
                <Kpi label="Passing cost" value={fmtUSD(quality?.passing_cost)}
                     sub={`${fmtUSD(quality?.scored_cost)} total scored`} />
              </div>
            </div>
          </section>

          <section className="section">
            <h2>Cohorts — spend by adoption week</h2>
            <div className="card" style={{ overflowX: 'auto' }}>
              <table>
                <thead>
                  <tr><th>Cohort (first week)</th><th>Week since adoption</th><th>Users</th><th>Cost</th></tr>
                </thead>
                <tbody>
                  {cohort.map((c, i) => (
                    <tr key={i}>
                      <td>{c.cohort}</td>
                      <td className="num">{c.week_offset}</td>
                      <td className="num">{c.users}</td>
                      <td className="num">{fmtUSD(c.cost)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}

      <footer className="footer">
        AI Cost &amp; Governance Analytics — by <a href="https://clemence.io" target="_blank" rel="noreferrer">clemence.io</a>
      </footer>
    </div>
  )
}

function BurnBar({ rate }) {
  const pct = rate == null ? 0 : Math.min(Number(rate) * 100, 100)
  const cls = pct > 90 ? 'crit' : pct > 75 ? 'warn' : ''
  return (
    <div className="burn">
      <div className={`burn-fill ${cls}`} style={{ width: `${pct}%` }} />
    </div>
  )
}
