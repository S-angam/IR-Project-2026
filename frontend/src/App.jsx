import { useEffect, useState } from 'react'
import './App.css'
import { API, METHODS, request } from './api'
import MetricCharts from './MetricCharts'
import ResultsPage from './ResultsPage'

const examples = [
  ['A day on repeat', 'A reporter keeps waking up on the same day while covering a small-town festival.'],
  ['A simulated world', 'A computer hacker discovers that reality is a simulation controlled by machines.'],
  ['An ocean adventure', 'A clownfish searches the ocean for his missing son with a forgetful fish.'],
]

function Poster({ source, title }) {
  const [failed, setFailed] = useState(false)
  return source && !failed ?
    <img className="poster" src={source} alt={`${title} poster or page image`}
      loading="lazy" onError={() => setFailed(true)} /> :
    <div className="poster placeholder" aria-label="No image available"><span>NO IMAGE</span></div>
}

function IndexProgress({ progress }) {
  if (!progress) return null
  const titles = { reading: 'Preparing plots', building: 'Building lexical indexes',
    embedding: 'Preparing movie embeddings', loading: 'Loading rankers',
    saving: 'Saving settings', ready: 'Index updated', failed: 'Update failed' }
  const counted = ['reading', 'embedding'].includes(progress.phase) && progress.target
  return <div className="index-progress" role="status" aria-live="polite">
    <div className="progress-heading"><strong>{titles[progress.phase]}</strong>
      {counted && <span>{Math.min(100, Math.floor(progress.indexed / progress.target * 100))}%</span>}</div>
    <progress aria-label="Index preparation progress"
      value={progress.phase === 'ready' ? 1 : counted ? progress.indexed : undefined}
      max={progress.phase === 'ready' ? 1 : progress.target || 1} />
    <p><strong>{progress.indexed.toLocaleString()}</strong>
      {counted ? ` / ${progress.target.toLocaleString()}` : ''} movies
      {progress.phase === 'ready' ? ' indexed' : ' prepared'}</p>
    <small>{progress.scanned.toLocaleString()} records scanned. Records without plots are skipped.</small>
    {progress.phase === 'reading' && !progress.target && <small>Processing the full collection; total usable plots is not yet known.</small>}
  </div>
}

function MovieCards({ output, images, showImages, method }) {
  return <ol className="movie-list">{output.results.map(movie => <li key={movie.movie_id}>
    <article className="movie">
      <span className="rank" aria-label={`Rank ${movie.rank}`}>#{movie.rank}</span>
      {showImages && <Poster key={`${movie.movie_id}:${images[movie.movie_id]}`} source={images[movie.movie_id]} title={movie.title} />}
      <div className="movie-content">
        <div className="movie-heading"><h3><a href={movie.wikipedia_url} target="_blank" rel="noreferrer">{movie.title}</a></h3>
          <span className="year">{movie.year ?? 'Year unavailable'}</span></div>
        <div className="score"><span>{output.score_type}</span><strong>{movie.score.toFixed(method.startsWith('hybrid') ? 5 : 3)}</strong></div>
        <details className="plot-details"><summary>Plot match</summary><p>{movie.snippet}</p></details>
        <div className="movie-meta"><span>ID {movie.movie_id}</span>
          <a href={movie.wikipedia_url} target="_blank" rel="noreferrer">Wikipedia ↗</a></div>
      </div>
    </article>
  </li>)}</ol>
}

function BenchmarkQueries({ fingerprint, onPick, disabled }) {
  const [open, setOpen] = useState(false)
  const [catalog, setCatalog] = useState(null)
  const [selectedId, setSelectedId] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {
    if (!open) return
    const controller = new AbortController()
    request('/evaluation/queries', { signal: controller.signal }).then(data => {
      setCatalog(data)
      setError('')
    }).catch(err => { if (err.name !== 'AbortError') setError(err.message) })
    return () => controller.abort()
  }, [open, fingerprint])
  const selected = catalog?.queries.find(item => item.query_id === selectedId) ?? catalog?.queries[0]
  return <details className="benchmark-queries" onToggle={event => setOpen(event.currentTarget.open)}>
    <summary>Browse benchmark queries</summary>
    {error && <p className="message error" role="alert">{error}</p>}
    {!catalog && !error && <p>Loading descriptions…</p>}
    {selected && <>
      <label>Benchmark description ({catalog.count} · {catalog.split.toUpperCase()})
        <select value={selected.query_id} onChange={event => setSelectedId(event.target.value)}>
          {catalog.queries.map(item => <option key={item.query_id} value={item.query_id}>#{item.query_id} · {item.title}</option>)}
        </select></label>
      <p className="query-description">{selected.query}</p>
      <p>Expected: {selected.targets.map(target => `${target.title || 'Movie'} (ID ${target.movie_id}) · ${target.indexed ? 'indexed' : 'not indexed'}`).join('; ')}</p>
      <button type="button" disabled={disabled} onClick={() => onPick(selected)}>Use this description</button>
      <small>The title and description above are the exact search input. Expected IDs are used only to grade the results.</small>
    </>}
  </details>
}

function QueryEvaluation({ evaluation }) {
  return <section className="query-evaluation" aria-labelledby="query-evaluation-title">
    <h2 id="query-evaluation-title">This description’s results</h2>
    <p>Expected: {evaluation.targets.map(target => `${target.title || 'Movie'} (ID ${target.movie_id})`).join('; ')}</p>
    {!evaluation.covered && <p className="message">The expected movie is outside the current index. It cannot be retrieved with these settings.</p>}
    <div className="table-scroll"><table>
      <caption>One query · checked top 10 · latency includes retrieving {evaluation.retrieved_top_k} results</caption>
      <thead><tr><th>Method</th><th>Rank @10</th><th>Success@5</th><th>RR@10</th><th>Time ms</th></tr></thead>
      <tbody>{Object.entries(evaluation.methods).map(([name, values]) => <tr key={name}>
        <th scope="row">{METHODS[name]}</th><td>{values.rank_at_10 ?? 'Not in top 10'}</td>
        <td>{values.success_at_5 ? 'Yes' : 'No'}</td><td>{values.reciprocal_rank_at_10.toFixed(3)}</td>
        <td>{values.elapsed_ms.toFixed(1)}</td>
      </tr>)}</tbody>
    </table></div>
    <small>RR@10 is the reciprocal rank for this query. The overall benchmark averages it as MRR@10. This check does not change the saved benchmark.</small>
  </section>
}

function Evaluation({ fingerprint, ready, onPick, disabled }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [starting, setStarting] = useState(false)
  const [refresh, setRefresh] = useState(0)
  useEffect(() => {
    let cancelled = false
    let timer
    const controller = new AbortController()
    async function load() {
      try {
        const response = await request('/evaluation', { signal: controller.signal })
        if (cancelled) return
        setData(response)
        setError('')
        if (response.running) timer = setTimeout(load, 1000)
      } catch (err) { if (!cancelled) setError(err.message) }
    }
    load()
    return () => { cancelled = true; clearTimeout(timer); controller.abort() }
  }, [fingerprint, refresh])
  async function run() {
    setStarting(true)
    setError('')
    try {
      setData(await request('/evaluation', { method: 'POST' }))
      setRefresh(value => value + 1)
    } catch (err) { setError(err.message) }
    finally { setStarting(false) }
  }
  const report = data?.results
  return <section className="evaluation" aria-labelledby="evaluation-title">
    <div className="results-heading"><h2 id="evaluation-title">Benchmark</h2>
      <button type="button" onClick={run} disabled={!ready || starting || data?.running}>
        {starting || data?.running ? 'Evaluating…' : report ? 'Run again' : 'Run benchmark'}</button></div>
    {(error || data?.error) && <p className="message error" role="alert">{error || data.error}</p>}
    {data?.running && <p role="status">Evaluated {data.completed} / {data.total || '…'} queries</p>}
    {!report && !data?.running && <p className="results-context">{ready ?
      'Run the labelled development queries to measure Success@5, MRR@10 and latency.' :
      'Prepare all rankers to evaluate Success@5, MRR@10 and latency.'}</p>}
    {report && <>
      <p className="results-context">{report.split.toUpperCase()} · {report.query_count} labelled queries · {report.indexed_movies.toLocaleString()} plots<br />
        Target coverage: {report.covered_queries}/{report.query_count}. Missing targets count as misses.</p>
      {data.stale && <p className="message" role="status">These results use an earlier index. Run again to evaluate the current settings.</p>}
      <MetricCharts series={[{ label: 'Original descriptions', methods: report.methods }]} />
      <div className="table-scroll"><table><caption>All labelled queries · higher relevance scores are better</caption>
        <thead><tr><th>Method</th><th>Success@5</th><th>MRR@10</th><th>Mean ms</th><th>P95 ms</th></tr></thead>
        <tbody>{Object.entries(report.methods).map(([name, values]) => <tr key={name}>
          <th scope="row">{METHODS[name]}</th><td>{(values.success_at_5 * 100).toFixed(1)}%</td>
          <td>{values.mrr_at_10.toFixed(3)}</td><td>{values.latency_ms.mean.toFixed(1)}</td><td>{values.latency_ms.p95.toFixed(1)}</td>
        </tr>)}</tbody></table></div>
      <details className="metric-details"><summary>Metric definitions & coverage diagnostics</summary>
        <p>Success@5: a relevant movie appears in the first five results. MRR@10: the mean reciprocal rank of the first relevant movie, or zero if absent from the first ten.</p>
        <p>{report.latency_scope} Saved {new Date(report.created_at).toLocaleString()}.</p>
        <p>For the {report.covered_queries} queries whose target is indexed:</p>
        <ul>{Object.entries(report.methods).map(([name, values]) => <li key={name}>{METHODS[name]}: {values.covered_only ?
          `${(values.covered_only.success_at_5 * 100).toFixed(1)}% Success@5 · ${values.covered_only.mrr_at_10.toFixed(3)} MRR@10` : 'No covered targets'}</li>)}</ul>
      </details>
    </>}
    <BenchmarkQueries fingerprint={fingerprint} onPick={onPick} disabled={disabled} />
  </section>
}

function App() {
  const [query, setQuery] = useState('')
  const [topK, setTopK] = useState(5)
  const [info, setInfo] = useState(null)
  const [draft, setDraft] = useState(null)
  const [result, setResult] = useState(null)
  const [images, setImages] = useState({})
  const [searching, setSearching] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [configError, setConfigError] = useState('')
  const [notice, setNotice] = useState('')
  const [retry, setRetry] = useState(0)
  const [progress, setProgress] = useState(null)
  const [progressError, setProgressError] = useState('')
  const [method, setMethod] = useState('bm25')
  const [preparing, setPreparing] = useState(false)
  const [expectedIds, setExpectedIds] = useState('')
  const [showQueryTest, setShowQueryTest] = useState(false)
  const [page, setPage] = useState(location.hash === '#results' ? 'results' : 'search')
  const [uncertainClues, setUncertainClues] = useState([])
  const [selection, setSelection] = useState('')
  const [autoRelax, setAutoRelax] = useState(false)
  useEffect(() => {
    const changed = () => setPage(location.hash === '#results' ? 'results' : 'search')
    window.addEventListener('hashchange', changed)
    return () => window.removeEventListener('hashchange', changed)
  }, [])
  function changeQuery(text) {
    setQuery(text)
    setUncertainClues([])
    setSelection('')
  }

  useEffect(() => {
    const controller = new AbortController()
    request('/config', { signal: controller.signal }).then(data => {
      setInfo(data)
      setDraft(data.settings)
      setTopK(data.settings.top_k)
      if (data.rebuilding) setPreparing(true)
      setConfigError('')
    }).catch(err => {
      if (err.name !== 'AbortError') setConfigError('Cannot reach the search service. Start the backend and retry.')
    })
    return () => controller.abort()
  }, [retry])

  useEffect(() => {
    const controller = new AbortController()
    const ids = [...new Set(Object.values(result?.methods ?? {}).flatMap(output => output.results.map(movie => movie.movie_id)))]
    if (info?.settings.show_images && ids.length) {
      const batches = []
      for (let i = 0; i < ids.length; i += 50) batches.push(ids.slice(i, i + 50))
      Promise.all(batches.map(batch => request(`/posters?movie_ids=${batch.join(',')}`,
        { signal: controller.signal }).catch(() => ({})))).then(parts => {
        if (!controller.signal.aborted) setImages(Object.assign({}, ...parts))
      })
    }
    return () => controller.abort()
  }, [result, info?.settings.show_images])

  useEffect(() => {
    if (!saving && !preparing) return
    const stream = new EventSource(`${API}/index/progress`)
    stream.onmessage = event => {
      const data = JSON.parse(event.data)
      if (data.rebuilding) setProgress(data.progress)
      else if (preparing) {
        setProgress(data.progress)
        setPreparing(false)
        if (data.progress.phase === 'failed') setConfigError('Embedding preparation failed. Completed batches are saved; retry preparation.')
        request('/config').then(setInfo).catch(err => setConfigError(err.message))
      }
      setProgressError('')
    }
    stream.onerror = () => setProgressError('Reconnecting to indexing progress…')
    return () => stream.close()
  }, [saving, preparing])

  async function prepareDense() {
    setConfigError('')
    try {
      await request('/index/prepare', { method: 'POST' })
      setPreparing(true)
    } catch (err) { setConfigError(err.message) }
  }

  async function search(event) {
    event.preventDefault()
    const action = event.nativeEvent.submitter?.value
    const testing = action === 'test'
    setSearching(true)
    setError('')
    setResult(null)
    setImages({})
    try {
      const data = await request(testing ? '/evaluation/query' : '/search', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: query.trim(), methods: testing || action === 'compare' ? Object.keys(METHODS) : [method], top_k: Number(topK),
          uncertain_clues: uncertainClues, auto_relax: autoRelax,
          ...(testing ? { expected_movie_ids: expectedIds.split(',').map(id => id.trim()).filter(Boolean) } : {}) }),
      })
      setResult(data)
    } catch (err) {
      setError(err.message === 'Failed to fetch' ? 'Cannot reach the backend. Check that it is running and try again.' : err.message)
    } finally {
      setSearching(false)
    }
  }

  async function saveSettings(event) {
    event.preventDefault()
    setSaving(true)
    setConfigError('')
    setNotice('')
    setProgress({ phase: 'reading', indexed: 0, scanned: 0, target: Number(draft.max_movies) || null })
    setProgressError('')
    try {
      const data = await request('/config', {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...draft, max_movies: Number(draft.max_movies),
          top_k: Number(topK), k1: Number(draft.k1), b: Number(draft.b) }),
      })
      setInfo(data)
      setDraft(data.settings)
      setProgress(data.progress)
      setResult(null)
      setNotice('Settings saved. Your next search will use the updated collection.')
    } catch (err) {
      setConfigError(err.message)
      setProgress(null)
    } finally {
      setSaving(false)
    }
  }

  function field(name, value) {
    setDraft(previous => ({ ...previous, [name]: value }))
    setNotice('')
  }

  const comparing = result && Object.keys(result.methods).length > 1
  const allReady = info && Object.keys(METHODS).every(name => info.methods[name]?.available)
  const parsedIds = expectedIds.split(',').map(id => id.trim()).filter(Boolean)
  const validExpected = parsedIds.length > 0 && parsedIds.length <= 20 && parsedIds.every(id => /^\d+$/.test(id))
  function useBenchmarkQuery(item) {
    changeQuery(item.query)
    setExpectedIds(item.expected_movie_ids.join(', '))
    setShowQueryTest(true)
    setResult(null)
    document.getElementById('query')?.focus()
  }
  const navigation = <nav className="page-nav" aria-label="Main navigation"><a href="#search" aria-current={page === 'search' ? 'page' : undefined}>Search</a><a href="#results" aria-current={page === 'results' ? 'page' : undefined}>Results & charts</a></nav>
  if (page === 'results') return <main>{navigation}<ResultsPage /></main>
  return (
    <main>
      {navigation}
      <div className="workspace">
      <div className="search-column">
      <section className="intro">
        <p className="eyebrow">A SCENE. A CHARACTER. A HALF-REMEMBERED STORY.</p>
        <h1>What was that movie?</h1>
        <p>Describe what you remember. We’ll search the plots for a match.</p>
      </section>
      <form className="search-form" onSubmit={search}>
        <label htmlFor="query">Your movie description</label>
        <textarea id="query" value={query} onChange={event => changeQuery(event.target.value)}
          onSelect={event => setSelection(event.currentTarget.value.slice(event.currentTarget.selectionStart, event.currentTarget.selectionEnd).trim())}
          placeholder="A reporter keeps waking up on the same day in a small town…"
          rows={3} maxLength={20000} required disabled={searching} />
        <div className="clue-controls">
          <small>Select a phrase in your description, then mark it uncertain.</small>
          <button type="button" disabled={!selection || uncertainClues.length >= 5 || searching} onClick={() => {
            setUncertainClues(previous => [...new Set([...previous, selection])]); setSelection('')
          }}>Mark selection uncertain</button>
          <div className="clue-chips">{uncertainClues.map(clue => <button key={clue} type="button" aria-label={`Remove uncertain clue: ${clue}`} onClick={() => setUncertainClues(previous => previous.filter(item => item !== clue))}>{clue} ×</button>)}</div>
          <label><input type="checkbox" checked={autoRelax} onChange={event => setAutoRelax(event.target.checked)} />Also detect “maybe” and “I think” automatically</label>
        </div>
        <div className="search-controls">
          <label className="compact">Method<select aria-label="Search method" value={method} onChange={event => setMethod(event.target.value)} disabled={searching}>
            {Object.entries(METHODS).map(([name, label]) => <option key={name} value={name} disabled={!info?.methods[name]?.available}>{label}</option>)}
          </select></label>
          <label className="compact">Results<input aria-label="Number of results" type="number" min="1" max="50"
            value={topK} required onChange={event => setTopK(event.target.value)} disabled={searching || saving} /></label>
          <button className="primary" type="submit" value="search" disabled={!info?.methods[method]?.available || searching || saving || !query.trim()}>
            {searching ? 'Searching…' : 'Find movies'}<span aria-hidden="true"> →</span>
          </button>
          <button type="submit" value="compare" disabled={!allReady || searching || saving || !query.trim()}>Compare all</button>
        </div>
        <details className="single-query-controls" open={showQueryTest} onToggle={event => setShowQueryTest(event.currentTarget.open)}>
          <summary>Test against a known movie</summary>
          <label htmlFor="expected-movies">Expected movie ID(s)</label>
          <input id="expected-movies" value={expectedIds} onChange={event => setExpectedIds(event.target.value)}
            placeholder="142327" disabled={searching} />
          <small>Use the Wikipedia ID shown on a result card. Groundhog Day is 142327. Separate multiple acceptable IDs with commas (up to 20).</small>
          <button type="submit" value="test" disabled={!allReady || searching || saving || !query.trim() || !validExpected}>Test description</button>
        </details>
      </form>
      <div className="examples"><span>Try a description</span>{examples.map(([label, text]) =>
        <button key={label} type="button" disabled={searching} onClick={() => {
          changeQuery(text)
          setExpectedIds(label === 'A day on repeat' ? '142327' : '')
          setShowQueryTest(label === 'A day on repeat')
        }}>{label}</button>)}</div>
      {error && <p className="message error" role="alert">{error}</p>}
      <section className="results" aria-live="polite" aria-busy={searching}>
        {searching && <p className="empty">Searching movie plots…</p>}
        {result && <>
          <div className="results-heading"><h2>{comparing ? 'Compare rankings' : 'Possible matches'}</h2></div>
          <p className="results-context">For “{result.query}” · {result.indexed_movies.toLocaleString()} indexed plots</p>
          {result.evaluation && <QueryEvaluation evaluation={result.evaluation} />}
          <p className="results-context">Scores rank movies within each method; their scales differ. Higher is better. Hybrid combines BM25 and dense ranks.</p>
          <div className={comparing ? 'comparison-grid' : 'single-method'}>{Object.entries(result.methods).map(([name, output]) => <section className="method-results" key={name}>
            <div className="method-heading"><h3>{METHODS[name]}</h3><span>{output.elapsed_ms.toFixed(1)} ms</span></div>
            {output.relaxation && <details className="variant-details"><summary>{output.relaxation.applied ? 'Clue removed in second search' : 'No clue relaxed'}</summary>
              {output.relaxation.uncertain_clues.map(clue => <p key={clue}>Uncertain: {clue}</p>)}
              {output.relaxation.variants.map((text, i) => <p key={i}><strong>{i ? 'Relaxed' : 'Full'}:</strong> {text}</p>)}
            </details>}
            {!output.results.length && <p className="empty">No matching plot terms. Try another detail.</p>}
            <MovieCards output={output} images={images} showImages={info.settings.show_images} method={name} />
          </section>)}</div>
        </>}
        {!result && !searching && !error && <p className="empty">Your next movie discovery starts with a detail.</p>}
      </section>
      {info && <Evaluation fingerprint={info.index_fingerprint} ready={allReady && !saving && !preparing}
        onPick={useBenchmarkQuery} disabled={searching || saving} />}
      </div>
      <aside className="settings-panel">
      {configError && <div className="message error" role="alert">{configError}
        {!info && <button type="button" onClick={() => setRetry(value => value + 1)}>Retry connection</button>}</div>}
      {draft && <section className="settings" aria-labelledby="settings-title">
        <h2 id="settings-title">Search settings</h2>
        <p className="settings-caption">Adjust the collection and ranking.</p>
        {progress && <IndexProgress progress={progress} />}
        {progressError && (saving || preparing) && <p className="message" role="status">{progressError}</p>}
        <form onSubmit={saveSettings}>
          <fieldset disabled={saving || searching || preparing}>
            <div className="settings-grid">
              <label>Movie limit<input type="number" min="0" max="250000" step="1" required
                value={draft.max_movies} onChange={event => field('max_movies', event.target.value)} />
                <small>First usable plots. Set 0 for the full collection.</small></label>
              <label>Term frequency (k1)<input type="number" min="0.01" max="5" step="0.01" required
                value={draft.k1} onChange={event => field('k1', event.target.value)} /></label>
              <label>Length normalization (b)<input type="number" min="0" max="1" step="0.01" required
                value={draft.b} onChange={event => field('b', event.target.value)} /></label>
            </div>
            <div className="checkboxes">
              <label><input type="checkbox" checked={draft.stemming} onChange={event => field('stemming', event.target.checked)} />Match word forms</label>
              <label><input type="checkbox" checked={draft.remove_stopwords} onChange={event => field('remove_stopwords', event.target.checked)} />Ignore common words</label>
              <label><input type="checkbox" checked={draft.show_images} onChange={event => field('show_images', event.target.checked)} />Show images</label>
            </div>
            <div className="settings-bottom"><small>Saved for future sessions. Changing the collection or ranking settings rebuilds the index.</small>
              <button type="submit">{saving ? 'Preparing index…' : 'Save settings'}</button></div>
          </fieldset>
        </form>
        <div className="dense-settings"><strong>Semantic search</strong>
          <p>{preparing ? 'Preparing saved embeddings for the selected collection.' : allReady ? 'All five rankers are ready.' : info.methods.dense.reason}</p>
          <button type="button" disabled={saving || preparing || searching} onClick={prepareDense}>
            {preparing ? 'Preparing embeddings…' : 'Prepare dense index'}</button>
          <small>Prepares new plots and reuses saved embeddings. Searches keep using the active index.</small>
        </div>
      </section>}
      {notice && <p className="message" role="status">{notice}</p>}
      </aside>
      </div>
      <footer><span>TREC ToT 2023 · Wikipedia plots & page images</span>
        <a href={import.meta.env.DEV ? 'http://127.0.0.1:8000/docs' : '/docs'} target="_blank" rel="noreferrer">API docs ↗</a></footer>
    </main>
  )
}

export default App
