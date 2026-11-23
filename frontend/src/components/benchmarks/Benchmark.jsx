import { useEffect, useState } from 'react'
import { METHODS, request } from '../../api'
import useBenchmarkJob from '../../hooks/useBenchmarkJob'
import MetricCharts from './MetricCharts'

function BenchmarkQueries({ fingerprint, onPick, disabled }) {
  const [open, setOpen] = useState(false)
  const [catalog, setCatalog] = useState(null)
  const [selectedId, setSelectedId] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {
    if (!open) return
    const controller = new AbortController()
    request('/evaluation/queries', { signal: controller.signal })
      .then(data => {
        setCatalog(data)
        setError('')
      })
      .catch(err => {
        if (err.name !== 'AbortError') setError(err.message)
      })
    return () => controller.abort()
  }, [open, fingerprint])
  const selected =
    catalog?.queries.find(item => item.query_id === selectedId) ?? catalog?.queries[0]
  return (
    <details className="benchmark-queries" onToggle={event => setOpen(event.currentTarget.open)}>
      <summary>Browse benchmark queries</summary>
      {error && (
        <p className="message error" role="alert">
          {error}
        </p>
      )}
      {!catalog && !error && <p>Loading descriptions…</p>}
      {selected && (
        <>
          <label>
            Benchmark description ({catalog.count} · {catalog.split.toUpperCase()})
            <select value={selected.query_id} onChange={event => setSelectedId(event.target.value)}>
              {catalog.queries.map(item => (
                <option key={item.query_id} value={item.query_id}>
                  #{item.query_id} · {item.title}
                </option>
              ))}
            </select>
          </label>
          <p className="query-description">{selected.query}</p>
          <p>
            Expected:{' '}
            {selected.targets
              .map(
                target =>
                  `${target.title || 'Movie'} (ID ${target.movie_id}) · ${target.indexed ? 'indexed' : 'not indexed'}`,
              )
              .join('; ')}
          </p>
          <button type="button" disabled={disabled} onClick={() => onPick(selected)}>
            Use this description
          </button>
          <small>
            The title and description above are the exact search input. Expected IDs are used only
            to grade the results.
          </small>
        </>
      )}
    </details>
  )
}

export default function Benchmark({ fingerprint, ready, onPick, disabled }) {
  const { data, error, starting, run } = useBenchmarkJob('/evaluation', 1000, fingerprint)
  const report = data?.results

  return (
    <section className="evaluation" aria-labelledby="evaluation-title">
      <div className="results-heading">
        <h2 id="evaluation-title">Benchmark</h2>
        <button type="button" onClick={run} disabled={!ready || starting || data?.running}>
          {starting || data?.running ? 'Evaluating…' : report ? 'Run again' : 'Run benchmark'}
        </button>
      </div>
      {(error || data?.error) && (
        <p className="message error" role="alert">
          {error || data.error}
        </p>
      )}
      {data?.running && (
        <p role="status">
          Evaluated {data.completed} / {data.total || '…'} queries
        </p>
      )}
      {!report && !data?.running && (
        <p className="results-context">
          {ready
            ? 'Run the benchmark queries to measure Success@5, MRR@10 and latency.'
            : 'Prepare all rankers to evaluate Success@5, MRR@10 and latency.'}
        </p>
      )}
      {report && (
        <>
          <p className="results-context">
            {report.split.toUpperCase()} · {report.query_count} labelled queries ·{' '}
            {report.indexed_movies.toLocaleString()} plots
            <br />
            Target coverage: {report.covered_queries}/{report.query_count}. Missing targets count as
            misses.
          </p>
          {report.cohort && (
            <p className="results-context">
              Fixed subset selected from {report.cohort.eligible_queries} of{' '}
              {report.cohort.source_queries} development queries whose targets were indexed in the
              baseline collection.
            </p>
          )}
          {data.stale && (
            <p className="message" role="status">
              These results use an earlier index. Run again to evaluate the current settings.
            </p>
          )}
          <MetricCharts series={[{ label: 'Original descriptions', methods: report.methods }]} />
          <div className="table-scroll">
            <table>
              <caption>All benchmark queries · higher relevance scores are better</caption>
              <thead>
                <tr>
                  <th>Method</th>
                  <th>Success@5</th>
                  <th>MRR@10</th>
                  <th>Mean ms</th>
                  <th>P95 ms</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(report.methods).map(([name, values]) => (
                  <tr key={name}>
                    <th scope="row">{METHODS[name]}</th>
                    <td>{(values.success_at_5 * 100).toFixed(1)}%</td>
                    <td>{values.mrr_at_10.toFixed(3)}</td>
                    <td>{values.latency_ms.mean.toFixed(1)}</td>
                    <td>{values.latency_ms.p95.toFixed(1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <details className="metric-details">
            <summary>Metric definitions & coverage diagnostics</summary>
            <p>
              Success@5: a relevant movie appears in the first five results. MRR@10: the mean
              reciprocal rank of the first relevant movie, or zero if absent from the first ten.
            </p>
            <p>
              {report.latency_scope} Saved {new Date(report.created_at).toLocaleString()}.
            </p>
            <p>For the {report.covered_queries} queries whose target is indexed:</p>
            <ul>
              {Object.entries(report.methods).map(([name, values]) => (
                <li key={name}>
                  {METHODS[name]}:{' '}
                  {values.covered_only
                    ? `${(values.covered_only.success_at_5 * 100).toFixed(1)}% Success@5 · ${values.covered_only.mrr_at_10.toFixed(3)} MRR@10`
                    : 'No covered targets'}
                </li>
              ))}
            </ul>
          </details>
        </>
      )}
      <BenchmarkQueries fingerprint={fingerprint} onPick={onPick} disabled={disabled} />
    </section>
  )
}
