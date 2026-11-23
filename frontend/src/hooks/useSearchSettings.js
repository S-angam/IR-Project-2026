import { useEffect, useState } from 'react'
import { API, METHODS, request, sendJson } from '../api'

export default function useSearchSettings() {
  const [info, setInfo] = useState(null)
  const [draft, setDraft] = useState(null)
  const [topK, setTopK] = useState(5)
  const [saving, setSaving] = useState(false)
  const [preparing, setPreparing] = useState(false)
  const [configError, setConfigError] = useState('')
  const [notice, setNotice] = useState('')
  const [retry, setRetry] = useState(0)
  const [progress, setProgress] = useState(null)
  const [progressError, setProgressError] = useState('')

  const allReady = info && Object.keys(METHODS).every(name => info.methods[name]?.available)

  useEffect(() => {
    const controller = new AbortController()

    request('/config', { signal: controller.signal })
      .then(data => {
        setInfo(data)
        setDraft(data.settings)
        setTopK(data.settings.top_k)
        if (data.rebuilding) setPreparing(true)
        setConfigError('')
      })
      .catch(error => {
        if (error.name !== 'AbortError') {
          setConfigError('Cannot reach the search service. Start the backend and retry.')
        }
      })

    return () => controller.abort()
  }, [retry])

  useEffect(() => {
    if (!saving && !preparing) return

    const stream = new EventSource(`${API}/index/progress`)
    stream.onmessage = event => {
      const data = JSON.parse(event.data)
      if (data.rebuilding) {
        setProgress(data.progress)
      } else if (preparing) {
        setProgress(data.progress)
        setPreparing(false)
        if (data.progress.phase === 'failed') {
          setConfigError(
            'Embedding preparation failed. Completed batches are saved; retry preparation.',
          )
        }
        request('/config')
          .then(setInfo)
          .catch(error => setConfigError(error.message))
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
    } catch (error) {
      setConfigError(error.message)
    }
  }

  async function saveSettings() {
    setSaving(true)
    setConfigError('')
    setNotice('')
    setProgress({
      phase: 'reading',
      indexed: 0,
      scanned: 0,
      target: Number(draft.max_movies) || null,
    })
    setProgressError('')

    try {
      const data = await sendJson('/config', 'PUT', {
        ...draft,
        max_movies: Number(draft.max_movies),
        top_k: Number(topK),
        k1: Number(draft.k1),
        b: Number(draft.b),
      })
      setInfo(data)
      setDraft(data.settings)
      setProgress(data.progress)
      setNotice('Settings saved. Your next search will use the updated collection.')
      return true
    } catch (error) {
      setConfigError(error.message)
      setProgress(null)
      return false
    } finally {
      setSaving(false)
    }
  }

  function changeSetting(name, value) {
    setDraft(previous => ({ ...previous, [name]: value }))
    setNotice('')
  }

  return {
    info,
    draft,
    topK,
    setTopK,
    allReady,
    saving,
    preparing,
    configError,
    notice,
    progress,
    progressError,
    prepareDense,
    saveSettings,
    changeSetting,
    retryConnection: () => setRetry(value => value + 1),
  }
}
