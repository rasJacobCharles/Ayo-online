"""Game-over detection and end-of-game seed collection for Ayo."""

from __future__ import annotations

from engine.rules import legal_moves
from engine.state import GameState

# A player wins by capturing strictly more than half of the 48 seeds.
WIN_THRESHOLD = 24
def _collect_sides(state: GameState) -> tuple[int, int]:
    """Final scores when each player adds the seeds on their own side."""
    return (
        state.scores[0] + state.side_total(0),
        state.scores[1] + state.side_total(1),
    )


def _winner(scores: tuple[int, int]) -> int | None:
    """Player with the higher score, or None for a tie."""
    if scores[0] > scores[1]:
        return 0
    if scores[1] > scores[0]:
        return 1
    return None


def check_game_over(state: GameState, history: list[GameState] | None = None) -> dict | None:
    """Return a game-over descriptor, or None if play continues.

    The descriptor has keys ``reason`` (one of "score", "draw", "starvation",
    "repetition"), ``winner`` (0, 1, or None for a draw), and ``scores`` (the final
    score tuple, including any end-of-game seed collection).

    Precedence: an outright score win, then a 24-24 draw, then repetition detection,
    then starvation (the side to move has no legal move). The last two collect
    remaining seeds to each side before deciding the winner.
    """
    s0, s1 = state.scores

    if s0 > WIN_THRESHOLD:
        return {"reason": "score", "winner": 0, "scores": (s0, s1)}
    if s1 > WIN_THRESHOLD:
        return {"reason": "score", "winner": 1, "scores": (s0, s1)}
    if s0 == WIN_THRESHOLD and s1 == WIN_THRESHOLD:
        return {"reason": "draw", "winner": None, "scores": (s0, s1)}

    if history:
        for prev in history:
            if prev.board == state.board and prev.player == state.player:
                scores = _collect_sides(state)
                return {"reason": "repetition", "winner": _winner(scores), "scores": scores}

    if not legal_moves(state):
        scores = _collect_sides(state)
        return {"reason": "starvation", "winner": _winner(scores), "scores": scores}

    return None
