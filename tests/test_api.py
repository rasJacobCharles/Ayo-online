"""Tests for the FastAPI app (api.main).

FastAPI's TestClient is httpx-based, satisfying the "httpx-based tests"
criterion without needing an async transport.
"""

from fastapi.testclient import TestClient

from api.main import app
from engine.rules import apply_move, legal_moves
from engine.state import GameState

client = TestClient(app)


def test_new_game_returns_initial_state_and_legal_moves():
    resp = client.post("/new-game")
    assert resp.status_code == 200
    data = resp.json()
    assert data["state"]["board"] == [4] * 12
    assert data["state"]["scores"] == [0, 0]
    assert data["state"]["player"] == 0
    assert data["state"]["ply"] == 0
    # All six of player 0's pits are non-empty and playable.
    assert data["legal_moves"] == [0, 1, 2, 3, 4, 5]


def test_move_advances_state_and_returns_events():
    state = client.post("/new-game").json()["state"]
    resp = client.post("/move", json={"state": state, "pit": 2})
    assert resp.status_code == 200
    data = resp.json()
    # Player swapped, ply incremented.
    assert data["state"]["player"] == 1
    assert data["state"]["ply"] == 1
    # Origin emptied; four seeds sown counter-clockwise into pits 3,4,5,6.
    assert data["state"]["board"] == [4, 4, 0, 5, 5, 5, 5, 4, 4, 4, 4, 4]
    assert data["events"] == [
        {"type": "sow", "pit": 3},
        {"type": "sow", "pit": 4},
        {"type": "sow", "pit": 5},
        {"type": "sow", "pit": 6},
    ]
    # Legal moves are now for player 1.
    assert data["legal_moves"] == [6, 7, 8, 9, 10, 11]
    assert data["game_over"] is None


def test_illegal_move_returns_400_with_reason():
    state = client.post("/new-game").json()["state"]
    # Pit 7 belongs to player 1; player 0 to move -> illegal.
    resp = client.post("/move", json={"state": state, "pit": 7})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Pit 7: Not your pit"


def test_move_on_empty_pit_returns_400():
    state = client.post("/new-game").json()["state"]
    state["board"][3] = 0  # empty one of player 0's own pits
    resp = client.post("/move", json={"state": state, "pit": 3})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Pit 3: Pit is empty"


def test_feeding_rule_illegal_move_returns_400():
    # Opponent side (6..11) empty; only pit 5 can feed. Pit 0 is illegal.
    state = {
        "board": [4, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0],
        "scores": [0, 0],
        "player": 0,
        "ply": 0,
    }
    resp = client.post("/move", json={"state": state, "pit": 0})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Pit 0: You must leave your opponent a move"


def test_cpu_move_plays_a_legal_move():
    state = client.post("/new-game").json()["state"]
    resp = client.post("/cpu-move", json={"state": state})
    assert resp.status_code == 200
    data = resp.json()
    assert data["chosen_pit"] in [0, 1, 2, 3, 4, 5]
    assert data["state"]["player"] == 1
    assert data["state"]["ply"] == 1
    assert len(data["events"]) >= 1


def test_cpu_move_accepts_time_limit_and_is_terminal_safe():
    # A finished position (player 0 already won): CPU plays nothing.
    won = {"board": [0] * 12, "scores": [25, 0], "player": 0, "ply": 40}
    resp = client.post("/cpu-move", json={"state": won, "time_limit_ms": 300})
    assert resp.status_code == 200
    data = resp.json()
    assert data["chosen_pit"] is None
    assert data["game_over"]["reason"] == "score"
    assert data["game_over"]["winner"] == 0


def test_cpu_move_each_difficulty_returns_a_legal_move():
    state = client.post("/new-game").json()["state"]
    for difficulty in ("easy", "medium", "hard"):
        # time_limit_ms override keeps "hard" fast for the test.
        resp = client.post(
            "/cpu-move",
            json={"state": state, "difficulty": difficulty, "time_limit_ms": 50},
        )
        assert resp.status_code == 200, difficulty
        assert resp.json()["chosen_pit"] in [0, 1, 2, 3, 4, 5]


def test_cpu_move_search_difficulties_find_the_obvious_capture():
    # Player 0 can play pit 5 (2 seeds) for a double capture of 8. The searching
    # difficulties must find it deterministically (easy is random, so untested).
    state = {
        "board": [1, 0, 0, 0, 0, 2, 3, 3, 0, 0, 0, 1],
        "scores": [0, 0],
        "player": 0,
        "ply": 0,
    }
    for difficulty in ("medium", "hard"):
        resp = client.post(
            "/cpu-move",
            json={"state": state, "difficulty": difficulty, "time_limit_ms": 200},
        )
        data = resp.json()
        assert data["chosen_pit"] == 5, difficulty
        assert data["state"]["scores"][0] == 8, difficulty


def test_cpu_move_rejects_unknown_difficulty():
    state = client.post("/new-game").json()["state"]
    resp = client.post("/cpu-move", json={"state": state, "difficulty": "insane"})
    assert resp.status_code == 422


def test_state_round_trip_matches_engine():
    # Feed a returned state back into /move and confirm it stays faithful to a
    # direct engine call: ply increments and the board matches exactly. This is
    # the serialization-fidelity check a single-shot test would miss.
    first = client.post("/move", json={"state": client.post("/new-game").json()["state"], "pit": 0})
    mid_state = first.json()["state"]
    second = client.post("/move", json={"state": mid_state, "pit": 6})
    api_state = second.json()["state"]

    # Reconstruct the same two plies directly through the engine.
    s0 = GameState.initial()
    s1, _ = apply_move(s0, 0)
    s2, _ = apply_move(s1, 6)

    assert api_state["board"] == list(s2.board)
    assert api_state["scores"] == list(s2.scores)
    assert api_state["player"] == s2.player
    assert api_state["ply"] == 2 == s2.ply
    assert second.json()["legal_moves"] == legal_moves(s2)
