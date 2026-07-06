"""Tests for engine.rules."""

import pytest

from engine.rules import IllegalMove, apply_move, legal_moves, resolve_capture, sow
from engine.state import NUM_PITS, GameState


def test_sow_simple_four_seeds():
    # 4 seeds from pit 4 land in 5, 6, 7, 8; last seed in pit 8.
    board = tuple([4] * NUM_PITS)
    new_board, last = sow(board, 4)
    assert last == 8
    assert new_board[4] == 0
    for i in (5, 6, 7, 8):
        assert new_board[i] == 5
    # untouched pits unchanged
    for i in (0, 1, 2, 3, 9, 10, 11):
        assert new_board[i] == 4


def test_sow_skips_origin_at_exactly_twelve():
    # 12 seeds from pit 0: one into each of 1..11, skip 0, second into pit 1.
    board = [0] * NUM_PITS
    board[0] = 12
    new_board, last = sow(tuple(board), 0)
    assert last == 1
    assert new_board[0] == 0  # origin skipped, stays empty
    assert new_board[1] == 2  # got two seeds
    for i in range(2, 12):
        assert new_board[i] == 1  # exactly one each


def test_sow_twenty_three_seeds_double_lap_plus_one():
    # 23 seeds from pit 0: two full laps of the 11 other pits (22) + 1 extra
    # into the first pit after origin. Last seed in pit 1.
    board = [0] * NUM_PITS
    board[0] = 23
    new_board, last = sow(tuple(board), 0)
    assert last == 1
    assert new_board[0] == 0
    assert new_board[1] == 3  # two laps + the single extra
    for i in range(2, 12):
        assert new_board[i] == 2
    assert sum(new_board) == 23  # seed conservation


def test_sow_wraps_across_board_boundary():
    # Sow from pit 10 with 4 seeds -> 11, 0, 1, 2 (wraps past 11->0).
    board = tuple([4] * NUM_PITS)
    new_board, last = sow(board, 10)
    assert last == 2
    assert new_board[10] == 0
    for i in (11, 0, 1, 2):
        assert new_board[i] == 5


def test_sow_leaves_origin_empty_various():
    # Origin pit is always 0 after sowing, for a range of seed counts.
    for seeds in (1, 5, 11, 12, 13, 23, 30):
        board = [1] * NUM_PITS
        board[3] = seeds
        new_board, _ = sow(tuple(board), 3)
        assert new_board[3] == 0
        # Seed conservation across the whole sowing.
        assert sum(new_board) == sum(board)


# --- resolve_capture (player 0 is the mover; opponent pits are 6..11) ---


def test_capture_single_pit():
    # Final seed in opponent pit 7 with exactly 4; pit 6 has 3 so no chain.
    board = (4, 4, 4, 4, 4, 4, 3, 4, 2, 2, 2, 2)
    new_board, count, events = resolve_capture(board, last_index=7, player=0)
    assert count == 4
    assert new_board[7] == 0
    assert board[:7] == new_board[:7]  # nothing else changed before 7
    assert new_board[8:] == board[8:]
    assert events == [{"type": "capture", "pit": 7, "seeds": 4}]


def test_capture_three_pit_backward_chain():
    # Final seed at pit 9; pits 9,8,7 all hold 4; pit 6 holds 3 -> stop.
    board = (4, 4, 4, 4, 4, 4, 3, 4, 4, 4, 2, 2)
    new_board, count, events = resolve_capture(board, last_index=9, player=0)
    assert count == 12
    assert new_board[9] == new_board[8] == new_board[7] == 0
    assert new_board[6] == 3  # chain stopped here
    assert [e["pit"] for e in events] == [9, 8, 7]


def test_capture_chain_stops_at_five_and_at_three():
    # Chain stops when the preceding pit holds 5 (too many)...
    board = (4, 4, 4, 4, 4, 4, 2, 2, 5, 4, 2, 2)
    new_board, count, _ = resolve_capture(board, last_index=9, player=0)
    assert count == 4
    assert new_board[9] == 0 and new_board[8] == 5

    # ...and when it holds 3 (too few).
    board = (4, 4, 4, 4, 4, 4, 2, 2, 3, 4, 2, 2)
    new_board, count, _ = resolve_capture(board, last_index=9, player=0)
    assert count == 4
    assert new_board[9] == 0 and new_board[8] == 3


def test_capture_chain_stops_at_side_boundary():
    # Final seed at the first opponent pit (6); pit 5 is the mover's own side and
    # must never be captured even though it also holds 4.
    board = (4, 4, 4, 4, 4, 4, 4, 2, 2, 2, 2, 2)
    new_board, count, events = resolve_capture(board, last_index=6, player=0)
    assert count == 4
    assert new_board[6] == 0
    assert new_board[5] == 4  # own pit untouched
    assert [e["pit"] for e in events] == [6]


def test_grand_slam_annulled():
    # Opponent's only seeds sit in pits 10 and 11 (4 each); capturing both would
    # empty their side entirely -> whole capture annulled, board unchanged.
    board = (4, 4, 4, 4, 4, 4, 0, 0, 0, 0, 4, 4)
    new_board, count, events = resolve_capture(board, last_index=11, player=0)
    assert count == 0
    assert new_board == board  # seeds restored / left in place
    assert events == [{"type": "annulled_capture", "pits": [11, 10]}]


def test_no_capture_when_final_seed_on_own_side():
    board = (4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4)
    new_board, count, events = resolve_capture(board, last_index=3, player=0)
    assert count == 0 and new_board == board and events == []


def test_player_one_capture_and_boundary():
    # Player 1's opponent pits are 0..5. Final seed at pit 0 with 4; pit 11 is
    # player 1's own side -> chain must stop at the boundary.
    board = (4, 4, 2, 2, 2, 2, 2, 2, 2, 2, 2, 4)
    new_board, count, events = resolve_capture(board, last_index=0, player=1)
    assert count == 4
    assert new_board[0] == 0
    assert new_board[11] == 4  # own pit untouched
    assert [e["pit"] for e in events] == [0]


# --- legal_moves ---


def test_legal_moves_initial_all_own_nonempty():
    assert legal_moves(GameState.initial()) == [0, 1, 2, 3, 4, 5]


def test_legal_moves_skips_empty_own_pits():
    board = (0, 3, 0, 2, 0, 1, 4, 4, 4, 4, 4, 4)
    state = GameState(board=board, scores=(0, 0), player=0)
    assert legal_moves(state) == [1, 3, 5]


def test_legal_moves_player_one():
    board = (4, 4, 4, 4, 4, 4, 0, 5, 0, 2, 0, 0)
    state = GameState(board=board, scores=(0, 0), player=1)
    assert legal_moves(state) == [7, 9]


def test_feeding_rule_filters_to_moves_that_reach_opponent():
    # Opponent side (6..11) empty; only pit 5 (1 seed -> pit 6) can feed. Pit 0
    # has 3 seeds but only reaches pit 3, so it is excluded despite being legal
    # material.
    board = (3, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0)
    state = GameState(board=board, scores=(0, 0), player=0)
    assert legal_moves(state) == [5]


def test_feeding_rule_no_move_returns_empty():
    # Opponent side empty and no own pit can reach it -> no legal moves.
    board = (1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    state = GameState(board=board, scores=(0, 0), player=0)
    assert legal_moves(state) == []


def test_feeding_rule_long_sow_that_wraps_counts_as_feeding():
    # A pit deep on the mover's side with enough seeds to reach the opponent.
    board = (0, 0, 0, 0, 0, 8, 0, 0, 0, 0, 0, 0)
    state = GameState(board=board, scores=(0, 0), player=0)
    assert legal_moves(state) == [5]


# --- apply_move ---


def _sow_events(pits):
    return [{"type": "sow", "pit": p} for p in pits]


def test_apply_move_scripted_six_move_opening():
    # A hand-computed, capture-free opening. Each step asserts the exact board,
    # scores, side to move, ply, and event list produced by apply_move.
    state = GameState.initial()

    script = [
        # (pit, expected_board, expected_events, expected_next_player)
        (2, (4, 4, 0, 5, 5, 5, 5, 4, 4, 4, 4, 4), _sow_events([3, 4, 5, 6]), 1),
        (9, (5, 5, 0, 5, 5, 5, 5, 4, 4, 0, 5, 5), _sow_events([10, 11, 0, 1]), 0),
        (4, (5, 5, 0, 5, 0, 6, 6, 5, 5, 1, 5, 5), _sow_events([5, 6, 7, 8, 9]), 1),
        (10, (6, 6, 1, 6, 0, 6, 6, 5, 5, 1, 0, 6), _sow_events([11, 0, 1, 2, 3]), 0),
        (0, (0, 7, 2, 7, 1, 7, 7, 5, 5, 1, 0, 6), _sow_events([1, 2, 3, 4, 5, 6]), 1),
        (11, (1, 8, 3, 8, 2, 8, 7, 5, 5, 1, 0, 0), _sow_events([0, 1, 2, 3, 4, 5]), 0),
    ]

    for i, (pit, exp_board, exp_events, exp_next) in enumerate(script, start=1):
        state, events = apply_move(state, pit)
        assert state.board == exp_board, f"move {i}"
        assert state.scores == (0, 0), f"move {i}"
        assert state.player == exp_next, f"move {i}"
        assert state.ply == i, f"move {i}"
        assert events == exp_events, f"move {i}"
        assert sum(state.board) + sum(state.scores) == 48, f"move {i}"


def test_apply_move_capture_updates_score_and_events():
    # Pit 5 (1 seed) drops into opponent pit 6 (3 -> 4): a single capture of 4.
    board = (4, 4, 4, 4, 4, 1, 3, 4, 4, 4, 4, 4)
    state = GameState(board=board, scores=(0, 0), player=0)
    new_state, events = apply_move(state, 5)
    assert new_state.board == (4, 4, 4, 4, 4, 0, 0, 4, 4, 4, 4, 4)
    assert new_state.scores == (4, 0)
    assert new_state.player == 1
    assert events == [
        {"type": "sow", "pit": 6},
        {"type": "capture", "pit": 6, "seeds": 4},
    ]


def test_apply_move_grand_slam_annulled_leaves_move_standing():
    # Capturing pit 6 would empty the opponent entirely -> annulled. The sown
    # seeds stay, nothing is scored, and an annulled_capture event is emitted.
    # South only has pit 5 so they have no other choice, making the move legal.
    board = (0, 0, 0, 0, 0, 1, 3, 0, 0, 0, 0, 0)
    state = GameState(board=board, scores=(0, 0), player=0)
    new_state, events = apply_move(state, 5)
    assert new_state.board == (0, 0, 0, 0, 0, 0, 4, 0, 0, 0, 0, 0)
    assert new_state.scores == (0, 0)
    assert new_state.player == 1
    assert events == [
        {"type": "sow", "pit": 6},
        {"type": "annulled_capture", "pits": [6]},
    ]


def test_apply_move_illegal_raises():
    state = GameState.initial()
    with pytest.raises(IllegalMove):
        apply_move(state, 6)  # opponent's pit
    empty_own = GameState(
        board=(0, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4), scores=(0, 0), player=0
    )
    with pytest.raises(IllegalMove):
        apply_move(empty_own, 0)  # own but empty


def test_feeding_rule_lookahead_avoid_emptying_opponent():
    # Opponent (player 1, pits 6..11) has exactly 3 seeds in pit 6, and 0 in all other pits.
    # Player 0 (South) has:
    # - pit 5 with 1 seed. Playing pit 5 lands in pit 6 (making it 4), which would trigger
    #   a capture of pit 6, leaving player 1 completely empty.
    # - pit 0 with 2 seeds. Playing pit 0 lands in pits 1 and 2, which does not empty player 1.
    # Because player 0 has a move (pit 0) that avoids emptying the opponent, pit 5 is illegal.
    board = (2, 0, 0, 0, 0, 1, 3, 0, 0, 0, 0, 0)
    state = GameState(board=board, scores=(0, 0), player=0)
    # Only pit 0 is legal because playing pit 5 would empty the opponent.
    assert legal_moves(state) == [0]


def test_feeding_rule_lookahead_all_moves_empty_opponent():
    # Opponent has 3 seeds in pit 6, and 0 elsewhere.
    # Player 0 only has pit 5 with 1 seed.
    # Playing pit 5 would empty the opponent, but since it is the only move, it is legal.
    # (The capture will be annulled during apply_move).
    board = (0, 0, 0, 0, 0, 1, 3, 0, 0, 0, 0, 0)
    state = GameState(board=board, scores=(0, 0), player=0)
    assert legal_moves(state) == [5]
