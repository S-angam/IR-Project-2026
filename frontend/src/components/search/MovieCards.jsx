import { useState } from 'react'

function Poster({ source, title }) {
  const [failed, setFailed] = useState(false)
  return source && !failed ? (
    <img
      className="poster"
      src={source}
      alt={`${title} poster or page image`}
      loading="lazy"
      onError={() => setFailed(true)}
    />
  ) : (
    <div className="poster placeholder" aria-label="No image available">
      <span>NO IMAGE</span>
    </div>
  )
}

export default function MovieCards({ output, images, showImages, method }) {
  return (
    <ol className="movie-list">
      {output.results.map(movie => (
        <li key={movie.movie_id}>
          <article className="movie">
            <span className="rank" aria-label={`Rank ${movie.rank}`}>
              #{movie.rank}
            </span>
            {showImages && (
              <Poster
                key={`${movie.movie_id}:${images[movie.movie_id]}`}
                source={images[movie.movie_id]}
                title={movie.title}
              />
            )}
            <div className="movie-content">
              <div className="movie-heading">
                <h3>
                  <a href={movie.wikipedia_url} target="_blank" rel="noreferrer">
                    {movie.title}
                  </a>
                </h3>
                <span className="year">{movie.year ?? 'Year unavailable'}</span>
              </div>
              <div className="score">
                <span>{output.score_type}</span>
                <strong>{movie.score.toFixed(method.startsWith('hybrid') ? 5 : 3)}</strong>
              </div>
              <details className="plot-details">
                <summary>Plot match</summary>
                <p>{movie.snippet}</p>
              </details>
              <div className="movie-meta">
                <span>ID {movie.movie_id}</span>
                <a href={movie.wikipedia_url} target="_blank" rel="noreferrer">
                  Wikipedia ↗
                </a>
              </div>
            </div>
          </article>
        </li>
      ))}
    </ol>
  )
}
