import { METHODS } from '../../api'

export default function AnswerPanel({ answer }) {
  const selected = answer.sources.find(source => source.movie_id === answer.movie_id)
  return (
    <section className="answer-panel" aria-labelledby="answer-title">
      <h2 id="answer-title">{answer.status === 'unavailable' ? 'Plot evidence' : 'RAG answer'}</h2>
      <p className="results-context">
        {METHODS[answer.method]} retrieval · {answer.model}
      </p>
      {selected && (
        <h3>
          <a href={selected.wikipedia_url} target="_blank" rel="noreferrer">
            {selected.title}
          </a>
          {selected.year && <span className="year"> ({selected.year})</span>}
        </h3>
      )}
      <p>{answer.explanation}</p>
      {selected && (
        <blockquote>
          “{answer.evidence_quote}”
          <cite>
            <a href={selected.wikipedia_url} target="_blank" rel="noreferrer">
              Wikipedia plot
            </a>
          </cite>
        </blockquote>
      )}
      {answer.sources.length > 0 && (
        <details open={answer.status === 'unavailable' || undefined}>
          <summary>Retrieved excerpts ({answer.sources.length})</summary>
          <ul>
            {answer.sources.map(source => (
              <li key={source.movie_id}>
                <a href={source.wikipedia_url} target="_blank" rel="noreferrer">
                  {source.title}
                </a>
                <p>{source.excerpt}</p>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  )
}
