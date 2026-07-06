"""Tests for engine.state.GameState."""

from engine.state import GameState


def test_initial_state():
    s = GameState.initial()
    assert s.board == (4,) * 12
    assert s.scores == (0, 0)
    assert s.player == 0
    assert s.ply == 0


def test_side_helpers():
    s = GameState.initial()
    assert list(s.own_pits(0)) == [0, 1, 2, 3, 4, 5]
    assert list(s.opponent_pits(0)) == [6, 7, 8, 9, 10, 11]
    assert s.side_total(0) == 24
    assert s.side_total(1) == 24


def test_ply_excluded_from_identity():
    # Position identity is (board, scores, player); ply must not affect equality
    # or hashing, so GameState can serve as a transposition-table / repetition key.
    a = GameState(board=(4,) * 12, scores=(0, 0), player=0, ply=0)
    b = GameState(board=(4,) * 12, scores=(0, 0), player=0, ply=137)
    assert a == b
    assert hash(a) == hash(b)
    assert len({a, b}) == 1


def test_differing_scores_are_distinct_positions():
    a = GameState(board=(4,) * 12, scores=(4, 0), player=0)
    b = GameState(board=(4,) * 12, scores=(0, 4), player=0)
    assert a != b
