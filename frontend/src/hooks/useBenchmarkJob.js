import { useEffect, useState } from 'react'
import { request } from '../api'

export default function useBenchmarkJob(path, interval, fingerprint) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [starting, setStarting] = useState(false)
  const [refresh, setRefresh] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    let timer

    async function load() {
      try {
        const response = await request(path, { signal: controller.signal })
        if (controller.signal.aborted) return

        setData(response)
        setError('')
        if (response.running) timer = setTimeout(load, interval)
      } catch (error) {
        if (!controller.signal.aborted) setError(error.message)
      }
    }

    load()
    return () => {
      controller.abort()
      clearTimeout(timer)
    }
  }, [fingerprint, interval, path, refresh])

  async function run() {
    setStarting(true)
    setError('')

    try {
      setData(await request(path, { method: 'POST' }))
      setRefresh(value => value + 1)
    } catch (error) {
      setError(error.message)
    } finally {
      setStarting(false)
    }
  }

  return { data, error, starting, run }
}
