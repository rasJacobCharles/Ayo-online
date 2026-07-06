"""Tests for ai.heuristic (Task 4.1) and ai.search (Task 4.2)."""

import random

from ai.heuristic import TERMINAL_SCORE, Weights, evaluate
from ai.search import choose_move
from engine.endings import check_game_over
from engine.rules import apply_move, legal_moves
from engine.state import GameState


# --- helpers for the search tests ----------------------------------------


def _reference_negamax(state: GameState, depth: int) -> float:
    """Plain unpruned negamax — no alpha-beta, no transposition table.

    The ground truth the real search must agree with at a fixed depth.
    """
    if depth == 0 or check_game_over(state) is not None:
        return evaluate(state, state.player)
    best = float("-inf")
    for pit in legal_moves(state):
        child, _ = apply_move(state, pit)
        best = max(best, -_reference_negamax(child, depth - 1))
    return best


def _random_position(rng: random.Random, max_plies: int) -> GameState:
    """A position reached by playing up to `max_plies` random legal moves."""
    state = GameState.initial()
    for _ in range(rng.randint(0, max_plies)):
        moves = legal_moves(state)
        if not moves or check_game_over(state) is not None:
            break
        state, _ = apply_move(state, rng.choice(moves))
    return state


def test_terminal_win_is_positive_for_winner_negative_for_loser():
    # Player 0 has crossed the winning threshold -> decided game.
    state = GameState(board=(2,) * 12, scores=(25, 3), player=1)
    win_for_0 = evaluate(state, 0)
    win_for_1 = evaluate(state, 1)

    assert win_for_0 > TERMINAL_SCORE  # winner: >1000, boosted by the margin
    assert win_for_1 < -TERMINAL_SCORE  # loser: mirror image
    assert win_for_0 == -win_for_1  # perspective symmetry


def test_bigger_terminal_margin_scores_higher():
    small = GameState(board=(0,) * 12, scores=(25, 23), player=1)
    big = GameState(board=(0,) * 12, scores=(48, 0), player=1)
    assert evaluate(big, 0) > evaluate(small, 0) > TERMINAL_SCORE


def test_terminal_draw_is_zero():
    state = GameState(board=(0,) * 12, scores=(24, 24), player=0)
    assert evaluate(state, 0) == 0.0
    assert evaluate(state, 1) == 0.0


def test_material_lead_sign_convention():
    # Player 0 holds far more seeds on their side; non-terminal, scores level.
    state = GameState(board=(5, 5, 5, 5, 5, 5, 1, 1, 1, 1, 1, 1), scores=(0, 0), player=0)
    assert evaluate(state, 0) > 0
    assert evaluate(state, 1) < 0
    assert evaluate(state, 0) == -evaluate(state, 1)


def test_immediate_capture_threat_scores_higher():
    # Player 0 can play pit 5 (1 seed) -> final seed lands in opponent pit 6,
    # making it exactly 4: an immediate capture threat.
    threat = GameState(
        board=(4, 4, 4, 4, 4, 1, 3, 4, 4, 4, 4, 4), scores=(0, 0), player=0
    )
    # Same shape but pit 6 holds 2, so landing there makes 3 — no capture. This
    # baseline even gives player 0 *less* opponent material to fear (side 1 is
    # one seed lighter), yet the threat position must still score higher.
    no_threat = GameState(
        board=(4, 4, 4, 4, 4, 1, 2, 4, 4, 4, 4, 4), scores=(0, 0), player=0
    )
    assert evaluate(threat, 0) > evaluate(no_threat, 0)


def test_vulnerability_lowers_score():
    # Symmetric to the threat case: player 1 can play pit 11 (1 seed) -> lands
    # in player 0's pit 0 making it 4. That is a vulnerability for player 0.
    vulnerable = GameState(
        board=(3, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 1), scores=(0, 0), player=1
    )
    safe = GameState(
        board=(2, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 1), scores=(0, 0), player=1
    )
    assert evaluate(vulnerable, 0) < evaluate(safe, 0)


def test_weights_are_configurable():
    state = GameState(board=(5, 5, 5, 5, 5, 5, 1, 1, 1, 1, 1, 1), scores=(0, 0), player=0)
    heavy = Weights(material=1.0)
    assert evaluate(state, 0, heavy) > evaluate(state, 0)


# --- ai.search (Task 4.2) ------------------------------------------------


def test_finds_forced_capture_at_depth_2():
    # Player 0 to move. Playing pit 5 (2 seeds) lands the final seed in pit 7,
    # making pits 6 and 7 both hold exactly 4 -> a double capture of 8. Pit 0 is
    # a non-capturing decoy. A depth-2 search must pick the capture.
    state = GameState(
        board=(1, 0, 0, 0, 0, 2, 3, 3, 0, 0, 0, 1), scores=(0, 0), player=0
    )
    move, info = choose_move(state, time_limit_ms=10_000, max_depth=2)
    assert move == 5
    assert info["depth"] >= 2
    _, events = apply_move(state, move)
    assert sum(e["seeds"] for e in events if e["type"] == "capture") == 8


def test_search_matches_reference_minimax():
    # The discriminating test: alpha-beta + TT must return the exact minimax
    # value an unpruned reference computes. Any pruning bug or bad TT bound
    # breaks this equality. (Move choice may differ among equal-valued moves;
    # we assert on value.)
    rng = random.Random(1)
    checked = 0
    for _ in range(25):
        state = _random_position(rng, 20)
        if check_game_over(state) is not None or not legal_moves(state):
            continue
        for depth in (2, 3, 4):
            _, info = choose_move(state, time_limit_ms=10_000, max_depth=depth)
            assert info["value"] == _reference_negamax(state, info["depth"])
            checked += 1
    assert checked > 0


def test_never_returns_illegal_move_over_random_positions():
    rng = random.Random(2)
    for _ in range(200):
        state = _random_position(rng, 40)
        move, _ = choose_move(state, time_limit_ms=10_000, max_depth=3)
        legal = legal_moves(state)
        if legal:
            assert move in legal
        else:
            assert move is None


def test_beats_random_mover():
    # Fixed depth stands in for the spec's 200 ms budget: deterministic and
    # fast, where a wall-clock limit would flicker by machine. Measured true
    # win rate at depth 3 is ~100%; the >= 95 threshold has ample margin.
    rng = random.Random(777)
    wins = 0
    games = 100
    for g in range(games):
        ai_player = g % 2  # alternate colors so first-move advantage is fair
        state = GameState.initial()
        while True:
            over = check_game_over(state)
            if over is not None:
                if over["winner"] == ai_player:
                    wins += 1
                break
            moves = legal_moves(state)
            if not moves:
                break
            if state.player == ai_player:
                move, _ = choose_move(state, time_limit_ms=10_000, max_depth=3)
            else:
                move = rng.choice(moves)
            state, _ = apply_move(state, move)
    assert wins >= 95


def test_hard_beats_medium():
    # "hard" searches deeper than "medium". Fixed depths (4 vs 2) stand in for
    # the API's 2000 ms / 300 ms budgets: deterministic and fast. Games start
    # from varied random openings and alternate colors; hard must win the
    # majority. Measured margin at these depths is ~4:1.
    rng = random.Random(99)
    hard_wins = medium_wins = 0
    for _ in range(10):
        opening = _random_position(rng, rng.randint(2, 8))
        if check_game_over(opening) is not None or not legal_moves(opening):
            continue
        for hard_player in (0, 1):
            state = opening
            while True:
                over = check_game_over(state)
                if over is not None:
                    if over["winner"] == hard_player:
                        hard_wins += 1
                    elif over["winner"] == 1 - hard_player:
                        medium_wins += 1
                    break
                moves = legal_moves(state)
                if not moves:
                    break
                depth = 4 if state.player == hard_player else 2
                move, _ = choose_move(state, time_limit_ms=10_000, max_depth=depth)
                state, _ = apply_move(state, move)
    assert hard_wins > medium_wins


def test_info_reports_depth_and_nodes():
    _, info = choose_move(GameState.initial(), time_limit_ms=10_000, max_depth=3)
    assert info["depth"] == 3
    assert info["nodes"] > 0
    assert info["value"] is not None


def test_terminal_position_returns_none():
    state = GameState(board=(0,) * 12, scores=(25, 23), player=0)
    move, info = choose_move(state, time_limit_ms=10_000, max_depth=3)
    assert move is None
