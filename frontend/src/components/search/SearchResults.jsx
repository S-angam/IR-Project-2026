import { METHODS } from '../../api'
import QueryEvaluation from '../benchmarks/QueryEvaluation'
import AnswerPanel from './AnswerPanel'
import MovieCards from './MovieCards'

export default function SearchResults({ search, showImages }) {
  const { answer, answerError, answering, busy, error, images, result, searching } = search
  const comparing = result && Object.keys(result.methods).length > 1

  return (
    <>
      {error && (
        <p className="message error" role="alert">
          {error}
        </p>
      )}
      <div aria-live="polite" aria-busy={answering}>
        {answering && (
          <p className="message" role="status">
            Retrieving evidence and asking Gemini…
          </p>
        )}
        {answerError && (
          <p className="message error" role="alert">
            {answerError}
          </p>
        )}
        {answer && <AnswerPanel answer={answer} />}
      </div>
      <section className="results" aria-live="polite" aria-busy={searching}>
        {searching && <p className="empty">Searching movie plots…</p>}
        {result && (
          <>
            <div className="results-heading">
              <h2>{comparing ? 'Compare rankings' : 'Possible matches'}</h2>
            </div>
            <p className="results-context">
              For “{result.query}” · {result.indexed_movies.toLocaleString()} indexed plots
            </p>
            {result.evaluation && <QueryEvaluation evaluation={result.evaluation} />}
            <p className="results-context">
              Scores rank movies within each method; their scales differ. Higher is better. Hybrid
              combines BM25 and dense ranks.
            </p>
            <div className={comparing ? 'comparison-grid' : 'single-method'}>
              {Object.entries(result.methods).map(([name, output]) => (
                <section className="method-results" key={name}>
                  <div className="method-heading">
                    <h3>{METHODS[name]}</h3>
                    <span>{output.elapsed_ms.toFixed(1)} ms</span>
                  </div>
                  {output.relaxation && (
                    <details className="variant-details">
                      <summary>
                        {output.relaxation.applied
                          ? 'Clue removed in second search'
                          : 'No clue relaxed'}
                      </summary>
                      {output.relaxation.uncertain_clues.map(clue => (
                        <p key={clue}>Uncertain: {clue}</p>
                      ))}
                      {output.relaxation.variants.map((text, i) => (
                        <p key={i}>
                          <strong>{i ? 'Relaxed' : 'Full'}:</strong> {text}
                        </p>
                      ))}
                    </details>
                  )}
                  {!output.results.length && (
                    <p className="empty">No matching plot terms. Try another detail.</p>
                  )}
                  <MovieCards
                    output={output}
                    images={images}
                    showImages={showImages}
                    method={name}
                  />
                </section>
              ))}
            </div>
          </>
        )}
        {!result && !busy && !answer && !answerError && !error && (
          <p className="empty">Your next movie discovery starts with a detail.</p>
        )}
      </section>
    </>
  )
}
