"""FastAPI app exposing the Ayo rules engine as a stateless HTTP API.

The server is the single source of truth for move legality. Every request
carries the full game state; every response returns the new state, the events
to animate, the legal moves for the next player, and any game-over descriptor.
The browser owns persistence (localStorage) — the server keeps no game state.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ai.search import choose_move
from engine.endings import check_game_over
from engine.rules import IllegalMove, apply_move, legal_moves
from engine.state import GameState

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

# Search time budget (ms) per difficulty. "easy" plays a random legal move.
DIFFICULTY_BUDGET_MS = {"medium": 300, "hard": 2000}


# --- Serialization models -------------------------------------------------
# JSON has no tuples, so states arrive with list-valued board/scores. We must
# rebuild GameState with tuples: the frozen dataclass does no runtime coercion,
# and lists would break hashing (Phase 4 transposition table) and equality
# (Phase 6 repetition detection). `ply` is round-tripped so the endgame cap
# survives across requests.


class StateModel(BaseModel):
    """Wire representation of a GameState."""

    board: list[int]
    scores: list[int]
    player: int
    ply: int = 0


def to_state(model: StateModel) -> GameState:
    """Rebuild an immutable GameState (with tuples) from its wire form."""
    return GameState(
        board=tuple(model.board),
        scores=(model.scores[0], model.scores[1]),
        player=model.player,
        ply=model.ply,
    )


def from_state(state: GameState) -> StateModel:
    """Serialize a GameState to its wire form."""
    return StateModel(
        board=list(state.board),
        scores=list(state.scores),
        player=state.player,
        ply=state.ply,
    )


# --- Request / response models -------------------------------------------


class NewGameResponse(BaseModel):
    state: StateModel
    legal_moves: list[int]


class MoveRequest(BaseModel):
    state: StateModel
    pit: int
    history: list[StateModel] | None = None


class MoveResponse(BaseModel):
    state: StateModel
    events: list[dict[str, Any]]
    legal_moves: list[int]
    game_over: dict[str, Any] | None


class CpuMoveRequest(BaseModel):
    state: StateModel
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    # Optional override of the difficulty's search budget (used by tests to keep
    # "hard" fast); ignored for "easy".
    time_limit_ms: int | None = Field(default=None, ge=0)
    history: list[StateModel] | None = None


class CpuMoveResponse(MoveResponse):
    chosen_pit: int | None


# --- App ------------------------------------------------------------------

app = FastAPI(title="Ayo", description="Ayo (Ayo Olopon) rules engine API.")

# Dev convenience: the frontend is served from this same origin in production,
# but allow any localhost port so a separately-served dev frontend can call us.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/new-game", response_model=NewGameResponse)
def new_game() -> NewGameResponse:
    """Start a fresh game: standard opening, player 0 to move."""
    state = GameState.initial()
    return NewGameResponse(state=from_state(state), legal_moves=legal_moves(state))


@app.post("/move", response_model=MoveResponse)
def move(req: MoveRequest) -> MoveResponse:
    """Apply the human move `pit` to `state`.

    Returns the new state, the ordered event list, the next player's legal
    moves, and a game-over descriptor (or null). Illegal moves — the core
    incorrect-move prevention — yield HTTP 400 with a human-readable reason.
    """
    state = to_state(req.state)
    try:
        new_state, events = apply_move(state, req.pit)
    except IllegalMove as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    history_states = [to_state(h) for h in req.history] if req.history else None
    new_history = history_states + [state] if history_states is not None else None

    return MoveResponse(
        state=from_state(new_state),
        events=events,
        legal_moves=legal_moves(new_state),
        game_over=check_game_over(new_state, new_history),
    )


@app.post("/cpu-move", response_model=CpuMoveResponse)
def cpu_move(req: CpuMoveRequest) -> CpuMoveResponse:
    """Play a move on behalf of the CPU (the player to move in `state`).

    Difficulty selects the mover: "easy" plays a random legal move; "medium" and
    "hard" run the alpha-beta search with a 300 ms / 2000 ms budget respectively
    (overridable via `time_limit_ms`). Returns the same shape as /move plus
    `chosen_pit`. If the position is already terminal (no legal moves), nothing
    is played and `chosen_pit` is null.
    """
    state = to_state(req.state)
    history_states = [to_state(h) for h in req.history] if req.history else None

    game_over = check_game_over(state, history_states)
    legal = legal_moves(state)
    if game_over is not None or not legal:
        return CpuMoveResponse(
            state=req.state,
            events=[],
            legal_moves=legal,
            game_over=game_over,
            chosen_pit=None,
        )

    if req.difficulty == "easy":
        pit = random.choice(legal)
    else:
        budget = (
            req.time_limit_ms
            if req.time_limit_ms is not None
            else DIFFICULTY_BUDGET_MS[req.difficulty]
        )
        pit, _info = choose_move(state, time_limit_ms=budget)
    new_state, events = apply_move(state, pit)
    new_history = history_states + [state] if history_states is not None else None

    return CpuMoveResponse(
        state=from_state(new_state),
        events=events,
        legal_moves=legal_moves(new_state),
        game_over=check_game_over(new_state, new_history),
        chosen_pit=pit,
    )


# Static frontend. Mounted last so the API routes above take precedence over
# this catch-all "/" mount.
if WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
