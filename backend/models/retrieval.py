from dataclasses import dataclass


@dataclass(frozen=True)
class Hit:
    position: int
    score: float


@dataclass(frozen=True)
class RetrievalQuery:
    text: str
    uncertain_clues: tuple[str, ...] = ()
    auto_relax: bool = False
