import { useEffect, useState } from 'react'
import useMovieSearch from './hooks/useMovieSearch'
import useSearchSettings from './hooks/useSearchSettings'
import ResultsPage from './pages/ResultsPage'
import SearchPage from './pages/SearchPage'
import './styles/app.css'

function activePage() {
  return location.hash === '#results' ? 'results' : 'search'
}

export default function App() {
  const [page, setPage] = useState(activePage)
  const settings = useSearchSettings()
  const search = useMovieSearch({
    topK: settings.topK,
    showImages: settings.info?.settings.show_images,
  })

  useEffect(() => {
    const updatePage = () => setPage(activePage())
    window.addEventListener('hashchange', updatePage)
    return () => window.removeEventListener('hashchange', updatePage)
  }, [])

  return (
    <main>
      <nav className="page-nav" aria-label="Main navigation">
        <a href="#search" aria-current={page === 'search' ? 'page' : undefined}>
          Search
        </a>
        <a href="#results" aria-current={page === 'results' ? 'page' : undefined}>
          Results & charts
        </a>
      </nav>
      {page === 'results' ? <ResultsPage /> : <SearchPage search={search} settings={settings} />}
    </main>
  )
}
