import { MARTS, METRIC_CATEGORIES, RAW_OBSERVATION_COLUMNS, RAW_SCORE_COLUMNS } from './metrics.js'

function FieldTable({ rows }) {
  return (
    <table>
      <thead>
        <tr><th>Field</th><th>Meaning / formula</th></tr>
      </thead>
      <tbody>
        {rows.map(([k, v]) => (
          <tr key={k}>
            <td className="mono">{k}</td>
            <td>{v}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default function Metrics() {
  return (
    <div className="metrics">
      <section className="section">
        <h2>Raw telemetry</h2>
        <p className="muted" style={{ fontSize: 13, margin: '0 0 12px' }}>
          One row per Langfuse observation (or score), normalized so every
          harness/provider reports the same shape.
        </p>
        <div className="card"><h3 className="subhead">fact_observation</h3><FieldTable rows={RAW_OBSERVATION_COLUMNS} /></div>
        <div className="card" style={{ marginTop: 12 }}><h3 className="subhead">fact_score (evals)</h3><FieldTable rows={RAW_SCORE_COLUMNS} /></div>
      </section>

      <section className="section">
        <h2>Marts — the calculation layer</h2>
        <p className="muted" style={{ fontSize: 13, margin: '0 0 12px' }}>
          Version-controlled SQL views in <code className="mono">warehouse/sql.py</code>.
        </p>
        {MARTS.map((m) => (
          <div className="card" key={m.name} style={{ marginBottom: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', flexWrap: 'wrap', gap: 8 }}>
              <h3 className="subhead mono">{m.name}</h3>
              <span className="chip">{m.grain}</span>
            </div>
            {m.note ? <p className="muted" style={{ fontSize: 13 }}>{m.note}</p> : null}
            <FieldTable rows={m.fields} />
          </div>
        ))}
      </section>

      <section className="section">
        <h2>KPI catalog</h2>
        {METRIC_CATEGORIES.map((cat) => (
          <div key={cat.title} style={{ marginBottom: 20 }}>
            <h3 className="subhead" style={{ margin: '0 0 8px' }}>{cat.title}</h3>
            <div className="metric-grid">
              {cat.metrics.map((m) => (
                <div className="card metric-card" key={m.name}>
                  <div className="metric-title">{m.name}</div>
                  <div className="chip">{m.endpoint}</div>
                  <code className="mono formula">{m.formula}</code>
                  <p className="muted" style={{ fontSize: 12.5, margin: 0 }}>{m.why}</p>
                </div>
              ))}
            </div>
          </div>
        ))}
      </section>
    </div>
  )
}
