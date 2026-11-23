import Benchmark from '../components/benchmarks/Benchmark'
import SearchForm from '../components/search/SearchForm'
import SearchResults from '../components/search/SearchResults'
import SearchSettings from '../components/search/SearchSettings'

export default function SearchPage({ search, settings }) {
  const { info, allReady, saving, preparing } = settings

  async function saveSettings(event) {
    event.preventDefault()
    if (await settings.saveSettings()) search.clearResults()
  }

  return (
    <>
      <div className="workspace">
        <div className="search-column">
          <section className="intro">
            <p className="eyebrow">A SCENE. A CHARACTER. A HALF-REMEMBERED STORY.</p>
            <h1>What was that movie?</h1>
            <p>Describe what you remember. We’ll search the plots for a match.</p>
          </section>
          <SearchForm search={search} settings={settings} />
          <SearchResults search={search} showImages={info?.settings.show_images} />
          {info && (
            <Benchmark
              fingerprint={info.index_fingerprint}
              ready={allReady && !saving && !preparing}
              onPick={search.useBenchmarkQuery}
              disabled={search.busy || saving}
            />
          )}
        </div>

        <SearchSettings settings={settings} busy={search.busy} onSave={saveSettings} />
      </div>

      <footer>
        <span>TREC ToT 2023 · Wikipedia plots & page images</span>
        <a
          href={import.meta.env.DEV ? 'http://127.0.0.1:8000/docs' : '/docs'}
          target="_blank"
          rel="noreferrer"
        >
          API docs ↗
        </a>
      </footer>
    </>
  )
}
