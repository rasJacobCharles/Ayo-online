"""Tests for engine.endings."""

from engine.endings import check_game_over
from engine.state import GameState


def test_no_ending_on_initial_position():
    assert check_game_over(GameState.initial()) is None


def test_score_win_player0():
    state = GameState(board=(2,) * 12, scores=(25, 3), player=1)
    result = check_game_over(state)
    assert result == {"reason": "score", "winner": 0, "scores": (25, 3)}


def test_score_win_player1():
    state = GameState(board=(0,) * 12, scores=(20, 28), player=0)
    result = check_game_over(state)
    assert result == {"reason": "score", "winner": 1, "scores": (20, 28)}


def test_exact_24_each_is_draw():
    state = GameState(board=(0,) * 12, scores=(24, 24), player=0)
    result = check_game_over(state)
    assert result == {"reason": "draw", "winner": None, "scores": (24, 24)}


def test_24_alone_is_not_a_win():
    # 24 captured with seeds still on the board -> game continues.
    state = GameState(board=(4,) * 12, scores=(24, 0), player=0)
    assert check_game_over(state) is None


def test_starvation_collects_own_side_to_score():
    # Player 0 to move; opponent side empty and no feeding move -> starvation.
    # Player 0 collects the 2 seeds left on their side.
    board = (1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    state = GameState(board=board, scores=(10, 20), player=0)
    result = check_game_over(state)
    assert result["reason"] == "starvation"
    assert result["scores"] == (12, 20)  # 10 + 2 own-side seeds, 20 + 0
    assert result["winner"] == 1
    # Seeds fully transfer: no seeds unaccounted for.
    assert sum(result["scores"]) == sum(state.scores) + sum(state.board)


def test_starvation_when_mover_side_empty():
    # Player 0 has nothing to play; remaining seeds sit on player 1's side and
    # are collected by player 1.
    board = (0, 0, 0, 0, 0, 0, 3, 3, 0, 0, 0, 0)
    state = GameState(board=board, scores=(0, 0), player=0)
    result = check_game_over(state)
    assert result == {"reason": "starvation", "winner": 1, "scores": (0, 6)}


def test_repetition_collects_each_side():
    # If the same state (board, player) has been seen before, repetition is triggered,
    # and each side collects its own seeds.
    board = (4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4)
    state = GameState(board=board, scores=(0, 0), player=0)
    history = [state]
    result = check_game_over(state, history)
    assert result == {"reason": "repetition", "winner": None, "scores": (24, 24)}


def test_repetition_uneven_sides_pick_winner():
    board = (5, 5, 5, 5, 5, 5, 1, 1, 1, 1, 1, 1)
    state = GameState(board=board, scores=(0, 0), player=0)
    history = [state]
    result = check_game_over(state, history)
    assert result == {"reason": "repetition", "winner": 0, "scores": (30, 6)}
