import { useEffect, useState } from 'react'
import { METHODS, request, sendJson } from '../api'

const POSTER_BATCH_SIZE = 50

export default function useMovieSearch({ topK, showImages }) {
  const [query, setQuery] = useState('')
  const [method, setMethod] = useState('bm25')
  const [expectedIds, setExpectedIds] = useState('')
  const [showQueryTest, setShowQueryTest] = useState(false)
  const [uncertainClues, setUncertainClues] = useState([])
  const [selection, setSelection] = useState('')
  const [autoRelax, setAutoRelax] = useState(false)

  const [result, setResult] = useState(null)
  const [answer, setAnswer] = useState(null)
  const [images, setImages] = useState({})
  const [searching, setSearching] = useState(false)
  const [answering, setAnswering] = useState(false)
  const [error, setError] = useState('')
  const [answerError, setAnswerError] = useState('')

  const busy = searching || answering
  const movieIds = expectedIds
    .split(',')
    .map(id => id.trim())
    .filter(Boolean)
  const validExpected =
    movieIds.length > 0 && movieIds.length <= 20 && movieIds.every(id => /^\d+$/.test(id))

  useEffect(() => {
    const controller = new AbortController()
    const ids = [
      ...new Set(
        Object.values(result?.methods ?? {}).flatMap(output =>
          output.results.map(movie => movie.movie_id),
        ),
      ),
    ]

    if (showImages && ids.length) {
      const batches = []
      for (let start = 0; start < ids.length; start += POSTER_BATCH_SIZE) {
        batches.push(ids.slice(start, start + POSTER_BATCH_SIZE))
      }
      Promise.all(
        batches.map(batch =>
          request(`/posters?movie_ids=${batch.join(',')}`, {
            signal: controller.signal,
          }).catch(() => ({})),
        ),
      ).then(parts => {
        if (!controller.signal.aborted) setImages(Object.assign({}, ...parts))
      })
    }

    return () => controller.abort()
  }, [result, showImages])

  function changeQuery(text) {
    setQuery(text)
    setUncertainClues([])
    setSelection('')
    setAnswer(null)
    setAnswerError('')
  }

  function markUncertain() {
    setUncertainClues(previous => [...new Set([...previous, selection])])
    setSelection('')
    setAnswer(null)
  }

  function removeUncertain(clue) {
    setUncertainClues(previous => previous.filter(item => item !== clue))
    setAnswer(null)
  }

  function changeAutoRelax(value) {
    setAutoRelax(value)
    setAnswer(null)
  }

  function chooseExample(description, expectedMovieId = '') {
    changeQuery(description)
    setExpectedIds(expectedMovieId)
    setShowQueryTest(Boolean(expectedMovieId))
  }

  function useBenchmarkQuery(item) {
    changeQuery(item.query)
    setExpectedIds(item.expected_movie_ids.join(', '))
    setShowQueryTest(true)
    setResult(null)
    document.getElementById('query')?.focus()
  }

  async function generateAnswer(description) {
    setAnswering(true)
    setAnswer(null)
    setAnswerError('')
    try {
      setAnswer(await sendJson('/answer', 'POST', description))
    } catch (error) {
      setAnswerError(error.message)
    } finally {
      setAnswering(false)
    }
  }

  async function submitSearch(event) {
    event.preventDefault()
    const action = event.nativeEvent.submitter?.value
    const description = {
      query: query.trim(),
      uncertain_clues: uncertainClues,
      auto_relax: autoRelax,
    }
    setError('')

    if (action === 'answer') {
      await generateAnswer(description)
      return
    }

    const testing = action === 'test'
    setSearching(true)
    setResult(null)
    setImages({})

    try {
      const data = await sendJson(testing ? '/evaluation/query' : '/search', 'POST', {
        ...description,
        methods: testing || action === 'compare' ? Object.keys(METHODS) : [method],
        top_k: Number(topK),
        ...(testing ? { expected_movie_ids: movieIds } : {}),
      })
      setResult(data)
    } catch (error) {
      setError(
        error.message === 'Failed to fetch'
          ? 'Cannot reach the backend. Check that it is running and try again.'
          : error.message,
      )
    } finally {
      setSearching(false)
    }
  }

  function clearResults() {
    setResult(null)
    setAnswer(null)
  }

  return {
    query,
    method,
    expectedIds,
    showQueryTest,
    uncertainClues,
    selection,
    autoRelax,
    result,
    answer,
    images,
    searching,
    answering,
    busy,
    error,
    answerError,
    validExpected,
    setMethod,
    setExpectedIds,
    setShowQueryTest,
    setSelection,
    changeQuery,
    markUncertain,
    removeUncertain,
    changeAutoRelax,
    chooseExample,
    useBenchmarkQuery,
    submitSearch,
    clearResults,
  }
}
