import { METHODS } from '../../api'

export default function QueryEvaluation({ evaluation }) {
  return (
    <section className="query-evaluation" aria-labelledby="query-evaluation-title">
      <h2 id="query-evaluation-title">This description’s results</h2>
      <p>
        Expected:{' '}
        {evaluation.targets
          .map(target => `${target.title || 'Movie'} (ID ${target.movie_id})`)
          .join('; ')}
      </p>
      {!evaluation.covered && (
        <p className="message">
          The expected movie is outside the current index. It cannot be retrieved with these
          settings.
        </p>
      )}
      <div className="table-scroll">
        <table>
          <caption>
            One query · checked top 10 · latency includes retrieving {evaluation.retrieved_top_k}{' '}
            results
          </caption>
          <thead>
            <tr>
              <th>Method</th>
              <th>Rank @10</th>
              <th>Success@5</th>
              <th>RR@10</th>
              <th>Time ms</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(evaluation.methods).map(([name, values]) => (
              <tr key={name}>
                <th scope="row">{METHODS[name]}</th>
                <td>{values.rank_at_10 ?? 'Not in top 10'}</td>
                <td>{values.success_at_5 ? 'Yes' : 'No'}</td>
                <td>{values.reciprocal_rank_at_10.toFixed(3)}</td>
                <td>{values.elapsed_ms.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <small>
        RR@10 is the reciprocal rank for this query. The overall benchmark averages it as MRR@10.
        This check does not change the saved benchmark.
      </small>
    </section>
  )
}
