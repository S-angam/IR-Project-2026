import { METHODS } from '../../api'

const EXAMPLES = [
  [
    'A day on repeat',
    'A reporter keeps waking up on the same day while covering a small-town festival.',
    '142327',
  ],
  [
    'A simulated world',
    'A computer hacker discovers that reality is a simulation controlled by machines.',
  ],
  [
    'An ocean adventure',
    'A clownfish searches the ocean for his missing son with a forgetful fish.',
  ],
]

export default function SearchForm({ search, settings }) {
  const {
    query,
    method,
    expectedIds,
    showQueryTest,
    uncertainClues,
    selection,
    autoRelax,
    busy,
    searching,
    answering,
    validExpected,
    changeQuery,
    setSelection,
    markUncertain,
    removeUncertain,
    changeAutoRelax,
    setMethod,
    setExpectedIds,
    setShowQueryTest,
    chooseExample,
    submitSearch,
  } = search
  const { info, topK, setTopK, allReady, saving } = settings
  const submissionDisabled = busy || saving || !query.trim()

  function selectDescription(event) {
    const { value, selectionStart, selectionEnd } = event.currentTarget
    setSelection(value.slice(selectionStart, selectionEnd).trim())
  }

  return (
    <>
      <form className="search-form" onSubmit={submitSearch}>
        <label htmlFor="query">Your movie description</label>
        <textarea
          id="query"
          value={query}
          onChange={event => changeQuery(event.target.value)}
          onSelect={selectDescription}
          placeholder="A reporter keeps waking up on the same day in a small town…"
          rows={3}
          maxLength={20000}
          required
          disabled={busy}
        />

        <div className="clue-controls">
          <small>Select a phrase in your description, then mark it uncertain.</small>
          <button
            type="button"
            disabled={!selection || uncertainClues.length >= 5 || busy}
            onClick={markUncertain}
          >
            Mark selection uncertain
          </button>
          <div className="clue-chips">
            {uncertainClues.map(clue => (
              <button
                key={clue}
                type="button"
                disabled={busy}
                aria-label={`Remove uncertain clue: ${clue}`}
                onClick={() => removeUncertain(clue)}
              >
                {clue} ×
              </button>
            ))}
          </div>
          <label>
            <input
              type="checkbox"
              checked={autoRelax}
              disabled={busy}
              onChange={event => changeAutoRelax(event.target.checked)}
            />
            Also detect “maybe” and “I think” automatically
          </label>
        </div>

        <div className="search-controls">
          <label className="compact">
            Method
            <select
              aria-label="Search method"
              value={method}
              onChange={event => setMethod(event.target.value)}
              disabled={busy}
            >
              {Object.entries(METHODS).map(([name, label]) => (
                <option key={name} value={name} disabled={!info?.methods[name]?.available}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="compact">
            Results
            <input
              aria-label="Number of results"
              type="number"
              min="1"
              max="50"
              value={topK}
              required
              onChange={event => setTopK(event.target.value)}
              disabled={busy || saving}
            />
          </label>
          <button
            className="primary"
            type="submit"
            value="search"
            disabled={!info?.methods[method]?.available || submissionDisabled}
          >
            {searching ? 'Searching…' : 'Find movies'}
            <span aria-hidden="true"> →</span>
          </button>
          <button type="submit" value="compare" disabled={!allReady || submissionDisabled}>
            Compare all
          </button>
          <button
            type="submit"
            value="answer"
            formNoValidate
            disabled={!info || submissionDisabled}
          >
            {answering ? 'Generating…' : 'Generate answer'}
          </button>
        </div>

        <details
          className="single-query-controls"
          open={showQueryTest}
          onToggle={event => setShowQueryTest(event.currentTarget.open)}
        >
          <summary>Test against a known movie</summary>
          <label htmlFor="expected-movies">Expected movie ID(s)</label>
          <input
            id="expected-movies"
            value={expectedIds}
            onChange={event => setExpectedIds(event.target.value)}
            placeholder="142327"
            disabled={busy}
          />
          <small>
            Use the Wikipedia ID shown on a result card. Groundhog Day is 142327. Separate multiple
            acceptable IDs with commas (up to 20).
          </small>
          <button
            type="submit"
            value="test"
            disabled={!allReady || !validExpected || submissionDisabled}
          >
            Test description
          </button>
        </details>
      </form>

      <div className="examples">
        <span>Try a description</span>
        {EXAMPLES.map(([label, description, movieId]) => (
          <button
            key={label}
            type="button"
            disabled={busy}
            onClick={() => chooseExample(description, movieId)}
          >
            {label}
          </button>
        ))}
      </div>
    </>
  )
}
