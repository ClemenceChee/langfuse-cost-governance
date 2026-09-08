import { DECISION_TREE, TOPOLOGIES, WIRING_KEYS } from './deployments.js'

export default function Deployments() {
  return (
    <div className="metrics">
      <section className="section">
        <h2>Deployment topologies</h2>
        <p className="muted" style={{ fontSize: 13, margin: '0 0 12px' }}>
          Every topology is a combination of where Langfuse lives, how you read
          it, and which warehouse you write to. Never point <code className="mono">DATABASE_URL</code>
          at Langfuse&apos;s own database.
        </p>
        <div className="card">
          <h3 className="subhead">Wiring keys</h3>
          <table>
            <thead><tr><th>Env var</th><th>Wires</th></tr></thead>
            <tbody>
              {WIRING_KEYS.map(([k, v]) => (
                <tr key={k}><td className="mono">{k}</td><td>{v}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="section">
        <h2>Choose a topology</h2>
        {TOPOLOGIES.map((t) => (
          <div className="card" key={t.name} style={{ marginBottom: 16 }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
              <h3 className="subhead" style={{ margin: 0 }}>{t.name}</h3>
              <span className="chip">{t.tag}</span>
            </div>
            <p className="muted" style={{ fontSize: 13, margin: '6px 0 10px' }}><strong>When:</strong> {t.when}</p>
            <pre className="diagram">{t.diagram}</pre>
            {t.env ? (
              <>
                <div className="subhead" style={{ marginTop: 8 }}>.env</div>
                <pre className="codeblock">{t.env}</pre>
              </>
            ) : null}
            {t.commands ? (
              <>
                <div className="subhead" style={{ marginTop: 8 }}>Run</div>
                <pre className="codeblock">{t.commands}</pre>
              </>
            ) : null}
            {t.notes?.length ? (
              <ul className="notes">
                {t.notes.map((n, i) => <li key={i}>{n}</li>)}
              </ul>
            ) : null}
          </div>
        ))}

        <div className="card">
          <h3 className="subhead">How to choose</h3>
          <pre className="diagram">{DECISION_TREE}</pre>
        </div>
      </section>
    </div>
  )
}
