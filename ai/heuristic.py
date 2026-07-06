"""Static position evaluation for the Ayo AI.

`evaluate(state, player)` scores a position from `player`'s point of view:
positive is good for `player`, negative is good for the opponent. The search
(Task 4.2) calls this at leaf nodes.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.endings import check_game_over
from engine.rules import sow
from engine.state import PITS_PER_SIDE, GameState

# Magnitude returned for a decided game, before the score-margin adjustment.
# Far larger than any heuristic term so a forced win always outranks a
# heuristically "nice" but non-terminal position.
TERMINAL_SCORE = 1000.0


@dataclass(frozen=True)
class Weights:
    """Linear weights for the evaluation terms."""

    score: float = 1.0  # captured-seed difference
    material: float = 0.08  # own-side seed difference
    threat: float = 0.3  # opponent pits I can capture next move
    vulnerability: float = 0.3  # my pits the opponent can capture next move


DEFAULT_WEIGHTS = Weights()


def _capture_threat_pits(board: tuple[int, ...], mover: int, target: range) -> set[int]:
    """Pits in `target` that `mover` can capture on their next move.

    For each of `mover`'s non-empty pits, we sow (pseudo-legally — ignoring the
    feeding-rule turn filter, so this is well-defined whoever is to move) and
    check whether the final seed lands on a `target` pit that thereby holds
    exactly 4. Such a pit is an immediate capture opportunity. Returns the set
    of threatened pit indices (deduplicated across moves).
    """
    threatened: set[int] = set()
    start = mover * PITS_PER_SIDE
    for pit in range(start, start + PITS_PER_SIDE):
        if board[pit] == 0:
            continue
        sown, last = sow(board, pit)
        if last in target and sown[last] == 4:
            threatened.add(last)
    return threatened


def evaluate(state: GameState, player: int, weights: Weights = DEFAULT_WEIGHTS) -> float:
    """Score `state` from `player`'s perspective (higher is better for player).

    Terminal positions return ±`TERMINAL_SCORE` adjusted by the final score
    margin (so a bigger win scores higher, a draw scores 0). Otherwise the
    score is a weighted sum of captured-seed lead, own-side material lead,
    immediate capture threats, and immediate vulnerabilities.
    """
    opponent = 1 - player

    over = check_game_over(state)
    if over is not None:
        margin = over["scores"][player] - over["scores"][opponent]
        if margin > 0:
            return TERMINAL_SCORE + margin
        if margin < 0:
            return -TERMINAL_SCORE + margin
        return 0.0

    board = state.board
    score_diff = state.scores[player] - state.scores[opponent]
    material = state.side_total(player) - state.side_total(opponent)
    threats = len(_capture_threat_pits(board, player, state.opponent_pits(player)))
    vulnerability = len(_capture_threat_pits(board, opponent, state.own_pits(player)))

    return (
        weights.score * score_diff
        + weights.material * material
        + weights.threat * threats
        - weights.vulnerability * vulnerability
    )
