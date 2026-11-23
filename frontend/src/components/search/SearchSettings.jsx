function IndexProgress({ progress }) {
  if (!progress) return null
  const titles = {
    reading: 'Preparing plots',
    building: 'Building lexical indexes',
    embedding: 'Preparing movie embeddings',
    loading: 'Loading rankers',
    saving: 'Saving settings',
    ready: 'Index updated',
    failed: 'Update failed',
  }
  const counted = ['reading', 'embedding'].includes(progress.phase) && progress.target
  return (
    <div className="index-progress" role="status" aria-live="polite">
      <div className="progress-heading">
        <strong>{titles[progress.phase]}</strong>
        {counted && (
          <span>{Math.min(100, Math.floor((progress.indexed / progress.target) * 100))}%</span>
        )}
      </div>
      <progress
        aria-label="Index preparation progress"
        value={progress.phase === 'ready' ? 1 : counted ? progress.indexed : undefined}
        max={progress.phase === 'ready' ? 1 : progress.target || 1}
      />
      <p>
        <strong>{progress.indexed.toLocaleString()}</strong>
        {counted ? ` / ${progress.target.toLocaleString()}` : ''} movies
        {progress.phase === 'ready' ? ' indexed' : ' prepared'}
      </p>
      <small>
        {progress.scanned.toLocaleString()} records scanned. Records without plots are skipped.
      </small>
      {progress.phase === 'reading' && !progress.target && (
        <small>Processing the full collection; total usable plots is not yet known.</small>
      )}
    </div>
  )
}

export default function SearchSettings({ settings, busy, onSave }) {
  const {
    info,
    draft,
    saving,
    preparing,
    allReady,
    configError,
    progress,
    progressError,
    notice,
    retryConnection,
    changeSetting,
    prepareDense,
  } = settings

  return (
    <aside className="settings-panel">
      {configError && (
        <div className="message error" role="alert">
          {configError}
          {!info && (
            <button type="button" onClick={retryConnection}>
              Retry connection
            </button>
          )}
        </div>
      )}
      {draft && (
        <section className="settings" aria-labelledby="settings-title">
          <h2 id="settings-title">Search settings</h2>
          <p className="settings-caption">Adjust the collection and ranking.</p>
          {progress && <IndexProgress progress={progress} />}
          {progressError && (saving || preparing) && (
            <p className="message" role="status">
              {progressError}
            </p>
          )}
          <form onSubmit={onSave}>
            <fieldset disabled={saving || busy || preparing}>
              <div className="settings-grid">
                <label>
                  Movie limit
                  <input
                    type="number"
                    min="0"
                    max="250000"
                    step="1"
                    required
                    value={draft.max_movies}
                    onChange={event => changeSetting('max_movies', event.target.value)}
                  />
                  <small>First usable plots. Set 0 for the full collection.</small>
                </label>
                <label>
                  Term frequency (k1)
                  <input
                    type="number"
                    min="0.01"
                    max="5"
                    step="0.01"
                    required
                    value={draft.k1}
                    onChange={event => changeSetting('k1', event.target.value)}
                  />
                </label>
                <label>
                  Length normalization (b)
                  <input
                    type="number"
                    min="0"
                    max="1"
                    step="0.01"
                    required
                    value={draft.b}
                    onChange={event => changeSetting('b', event.target.value)}
                  />
                </label>
              </div>
              <div className="checkboxes">
                <label>
                  <input
                    type="checkbox"
                    checked={draft.stemming}
                    onChange={event => changeSetting('stemming', event.target.checked)}
                  />
                  Match word forms
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={draft.remove_stopwords}
                    onChange={event => changeSetting('remove_stopwords', event.target.checked)}
                  />
                  Ignore common words
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={draft.show_images}
                    onChange={event => changeSetting('show_images', event.target.checked)}
                  />
                  Show images
                </label>
              </div>
              <div className="settings-bottom">
                <small>
                  Saved for future sessions. Changing the collection or ranking settings rebuilds
                  the index.
                </small>
                <button type="submit">{saving ? 'Preparing index…' : 'Save settings'}</button>
              </div>
            </fieldset>
          </form>
          <div className="dense-settings">
            <strong>Semantic search</strong>
            <p>
              {info.dense_index.engine} · {info.dense_index.stored_vectors.toLocaleString()} stored
              vectors
            </p>
            <p>
              {preparing
                ? 'Preparing saved embeddings for the selected collection.'
                : allReady
                  ? 'All five rankers are ready.'
                  : info.methods.dense.reason}
            </p>
            <button type="button" disabled={saving || preparing || busy} onClick={prepareDense}>
              {preparing ? 'Preparing embeddings…' : 'Prepare dense index'}
            </button>
            <small>
              Prepares new plots and reuses saved embeddings. Searches keep using the active index.
            </small>
          </div>
        </section>
      )}
      {notice && (
        <p className="message" role="status">
          {notice}
        </p>
      )}
    </aside>
  )
}
