import { useState } from 'react'
import { METHODS } from '../api'
import MetricCharts from '../components/benchmarks/MetricCharts'
import useBenchmarkJob from '../hooks/useBenchmarkJob'

export default function ResultsPage() {
  const { data, error, starting, run } = useBenchmarkJob('/experiments', 1500)
  const [condition, setCondition] = useState('wrong_detail')
  const [covered, setCovered] = useState(false)

  function startExperiment(event) {
    event.preventDefault()
    run()
  }

  const report = data?.results
  const original =
    report?.conditions[
      condition === 'wrong_detail_manual' ? 'original_manual_paired' : 'original_paired'
    ]
  const changed = report?.conditions[condition]
  return (
    <section className="results-page">
      <h1>Retrieval experiments</h1>
      <p className="results-context">
        Compare the same descriptions with and without one synthetic wrong release decade. Compare
        ranking quality and retrieval time.
      </p>
      <form className="experiment-controls" onSubmit={startExperiment}>
        <button disabled={starting || data?.running}>
          {starting || data?.running ? 'Running experiment…' : 'Run experiment'}
        </button>
      </form>
      {(error || data?.error) && (
        <p className="message error" role="alert">
          {error || data.error}
        </p>
      )}
      {data?.running && (
        <p className="message" role="status">
          {data.phase}: {data.completed} / {data.total || '…'}
        </p>
      )}
      {report && (
        <>
          <p className="results-context">
            {report.split.toUpperCase()} · {report.conditions.original?.query_count ?? '…'}{' '}
            benchmark queries · {report.indexed_movies.toLocaleString()} indexed plots · saved{' '}
            {new Date(report.created_at).toLocaleString()} · {report.status}
          </p>
          {data.stale && (
            <p className="message">
              These results use an earlier index. Run again for current settings.
            </p>
          )}
          {original && (
            <>
              <div className="results-heading">
                <h2>Effect of an uncertain wrong detail</h2>
                <select
                  aria-label="Relaxation experiment"
                  value={condition}
                  onChange={e => setCondition(e.target.value)}
                >
                  <option value="wrong_detail">Automatic clue detection</option>
                  <option value="wrong_detail_manual">Manually marked injected clue</option>
                </select>
              </div>
              <p className="results-context">
                {original.query_count} paired queries · {original.covered_queries} targets indexed.{' '}
                {report.skipped_mutations.length} queries excluded from pairs because a release year
                could not be verified.{' '}
                {condition === 'wrong_detail_manual'
                  ? 'No original clue is manually marked: relaxed Hybrid equals Hybrid and reuses its measurement.'
                  : 'Original queries use automatic uncertainty detection.'}
              </p>
              <label className="coverage-toggle">
                <input
                  type="checkbox"
                  checked={covered}
                  onChange={e => setCovered(e.target.checked)}
                />
                Show covered-only relevance (diagnostic)
              </label>
              {covered && (
                <p className="results-context">
                  Relevance charts use only indexed targets. Latency and the exact-values table
                  below still include all paired queries.
                </p>
              )}
              <MetricCharts
                coveredOnly={covered}
                series={[
                  { label: 'Original · paired subset', methods: original.methods },
                  {
                    label:
                      condition === 'wrong_detail'
                        ? 'Wrong decade · automatic'
                        : 'Wrong decade · manual',
                    methods: changed?.methods ?? {},
                  },
                ]}
              />
              <details className="metric-details">
                <summary>Exact retrieval values</summary>
                <div className="table-scroll">
                  <table>
                    <caption>All paired queries · missing targets count as misses</caption>
                    <thead>
                      <tr>
                        <th>Condition / method</th>
                        <th>Success@5</th>
                        <th>MRR@10</th>
                        <th>Mean ms</th>
                        <th>P95 ms</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[
                        ['Original', original],
                        ['Wrong detail', changed],
                      ].flatMap(([label, group]) =>
                        Object.entries(group?.methods ?? {}).map(([name, m]) => (
                          <tr key={`${label}:${name}`}>
                            <th>
                              {label} / {METHODS[name]}
                            </th>
                            <td>{(m.success_at_5 * 100).toFixed(2)}%</td>
                            <td>{m.mrr_at_10.toFixed(4)}</td>
                            <td>{m.latency_ms.mean.toFixed(1)}</td>
                            <td>{m.latency_ms.p95.toFixed(1)}</td>
                          </tr>
                        )),
                      )}
                    </tbody>
                  </table>
                </div>
              </details>
            </>
          )}
          <details className="metric-details">
            <summary>Experiment notes</summary>
            <ul>
              {report.notes.map(note => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </details>
        </>
      )}
    </section>
  )
}
