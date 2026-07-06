"""Alpha-beta search for the Ayo AI.

`choose_move` runs an iterative-deepening negamax search with alpha-beta
pruning and a transposition table, bounded by a wall-clock budget (or, for
deterministic tests, a fixed `max_depth`).
"""

from __future__ import annotations

import time
from typing import NamedTuple

from ai.heuristic import DEFAULT_WEIGHTS, TERMINAL_SCORE, Weights, evaluate
from engine.endings import check_game_over
from engine.rules import apply_move, legal_moves, resolve_capture, sow
from engine.state import GameState

INF = float("inf")

# Transposition-table entry bound flags.
EXACT = 0  # `value` is the true score
LOWER = 1  # `value` is a lower bound (search failed high / beta cutoff)
UPPER = 2  # `value` is an upper bound (search failed low)

# Safety ceiling on iterative deepening when no wall-clock limit bites (e.g. a
# tiny game tree searched with a generous budget).
MAX_DEPTH = 64

# Check the clock every this many nodes (a power of two for a cheap mask).
_CLOCK_INTERVAL = 1024


class _TTEntry(NamedTuple):
    depth: int
    flag: int
    value: float
    move: int


class _Timeout(Exception):
    """Raised internally to abort a search iteration past the deadline."""


def _captures(state: GameState, pit: int) -> bool:
    """True if playing `pit` from `state` captures at least one seed."""
    sown, last = sow(state.board, pit)
    _, captured, _ = resolve_capture(sown, last, state.player)
    return captured > 0


def _ordered_moves(state: GameState, tt_move: int | None) -> list[int]:
    """Legal moves ordered for good pruning: TT best move, captures, then rest.

    Ties within a group keep ascending pit order (stable sort).
    """
    moves = legal_moves(state)

    def rank(pit: int) -> int:
        if pit == tt_move:
            return 0
        return 1 if _captures(state, pit) else 2

    return sorted(moves, key=rank)


def _negamax(
    state: GameState,
    depth: int,
    alpha: float,
    beta: float,
    tt: dict,
    weights: Weights,
    deadline: float,
    counters: list,
) -> float:
    counters[0] += 1
    if counters[0] % _CLOCK_INTERVAL == 0 and time.monotonic() > deadline:
        raise _Timeout

    if depth == 0 or check_game_over(state) is not None:
        return evaluate(state, state.player, weights)

    alpha_orig = alpha
    entry = tt.get(state)
    tt_move = entry.move if entry is not None else None
    if entry is not None and entry.depth >= depth:
        if entry.flag == EXACT:
            return entry.value
        if entry.flag == LOWER:
            alpha = max(alpha, entry.value)
        elif entry.flag == UPPER:
            beta = min(beta, entry.value)
        if alpha >= beta:
            return entry.value

    best_value = -INF
    best_move = None
    for pit in _ordered_moves(state, tt_move):
        child, _ = apply_move(state, pit)
        value = -_negamax(child, depth - 1, -beta, -alpha, tt, weights, deadline, counters)
        if value > best_value:
            best_value, best_move = value, pit
        alpha = max(alpha, value)
        if alpha >= beta:
            break

    if best_value <= alpha_orig:
        flag = UPPER
    elif best_value >= beta:
        flag = LOWER
    else:
        flag = EXACT
    tt[state] = _TTEntry(depth, flag, best_value, best_move)
    return best_value


def _search_root(
    state: GameState,
    depth: int,
    tt: dict,
    weights: Weights,
    deadline: float,
    counters: list,
) -> tuple[float, int]:
    """One full-width search of the root to `depth`; returns (value, best_move)."""
    entry = tt.get(state)
    tt_move = entry.move if entry is not None else None

    alpha = -INF
    best_value = -INF
    best_move = None
    for pit in _ordered_moves(state, tt_move):
        child, _ = apply_move(state, pit)
        value = -_negamax(child, depth - 1, -INF, -alpha, tt, weights, deadline, counters)
        if value > best_value:
            best_value, best_move = value, pit
        alpha = max(alpha, value)

    tt[state] = _TTEntry(depth, EXACT, best_value, best_move)
    return best_value, best_move


def choose_move(
    state: GameState,
    time_limit_ms: int = 1500,
    weights: Weights = DEFAULT_WEIGHTS,
    max_depth: int | None = None,
) -> tuple[int | None, dict]:
    """Choose a move for the player to move in `state`.

    Runs iterative-deepening negamax until the time budget expires or `max_depth`
    is reached, keeping the best move from the deepest fully completed iteration.
    Passing `max_depth` (with a generous `time_limit_ms`) makes the search
    deterministic, which the tests rely on.

    Returns `(pit, info)` where `info` has `depth` (deepest completed), `nodes`
    (positions searched), and `value` (root score). If the position is terminal
    `pit` is None.
    """
    moves = legal_moves(state)
    if not moves:
        return None, {"depth": 0, "nodes": 0, "value": None}

    deadline = time.monotonic() + max(0, time_limit_ms) / 1000.0
    depth_ceiling = MAX_DEPTH if max_depth is None else max_depth
    tt: dict = {}
    counters = [0]

    best_move = moves[0]  # legal fallback if even depth 1 is cut off
    best_value: float | None = None
    depth_reached = 0

    depth = 1
    while depth <= depth_ceiling:
        try:
            value, move = _search_root(state, depth, tt, weights, deadline, counters)
        except _Timeout:
            break
        best_move, best_value, depth_reached = move, value, depth
        # A decided line won't change with deeper search; stop early.
        if abs(value) >= TERMINAL_SCORE:
            break
        depth += 1

    return best_move, {"depth": depth_reached, "nodes": counters[0], "value": best_value}
