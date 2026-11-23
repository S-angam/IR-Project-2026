from dataclasses import dataclass


@dataclass(frozen=True)
class Movie:
    movie_id: str
    title: str
    plot: str
    plot_section: str
    year: int | None = None
    cast: str | None = None
