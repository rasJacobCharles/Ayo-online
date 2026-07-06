"""Core Ayo move mechanics: sowing (and, later, capture / legality / apply)."""

from __future__ import annotations

from engine.state import NUM_PITS, PITS_PER_SIDE, GameState


class IllegalMove(Exception):
    """Raised when a move is not permitted for the current state."""


def _is_opponent_pit(idx: int, player: int) -> bool:
    """True if pit `idx` belongs to `player`'s opponent."""
    opp_start = (1 - player) * PITS_PER_SIDE
    return opp_start <= idx < opp_start + PITS_PER_SIDE


def _sow_path(board: tuple[int, ...], pit: int) -> list[int]:
    """Ordered pit indices that receive a seed when sowing `pit`.

    Runs counter-clockwise, skipping the origin pit on any loop-back. The list
    has one entry per seed lifted (with repeats across multiple laps), so its
    length equals `board[pit]` and its last element is the final seed's pit.
    """
    seeds = board[pit]
    path: list[int] = []
    idx = pit
    while len(path) < seeds:
        idx = (idx + 1) % NUM_PITS
        if idx == pit:  # loop back to origin -> skip it
            continue
        path.append(idx)
    return path


def _apply_sow(board: tuple[int, ...], pit: int) -> tuple[tuple[int, ...], list[int]]:
    """Return the board after sowing `pit` and the ordered drop path."""
    path = _sow_path(board, pit)
    new_board = list(board)
    new_board[pit] = 0
    for i in path:
        new_board[i] += 1
    return tuple(new_board), path


def sow(board: tuple[int, ...], pit: int) -> tuple[tuple[int, ...], int]:
    """Sow all seeds from `pit` counter-clockwise.

    Lifts every seed out of `pit` (leaving it empty) and drops them one per pit
    in ascending index order, wrapping 11->0. The origin pit is skipped whenever
    the sowing loops back around to it, so it stays empty for the whole sowing
    (only reachable when 12 or more seeds are lifted).

    Returns the new board and the index of the pit that received the final seed.
    Assumes `pit` holds at least one seed (guaranteed by `legal_moves`).
    """
    new_board, path = _apply_sow(board, pit)
    last = path[-1] if path else pit
    return new_board, last


def resolve_capture(
    board: tuple[int, ...], last_index: int, player: int
) -> tuple[tuple[int, ...], int, list[dict]]:
    """Resolve captures after a sowing that ended at `last_index`.

    A capture triggers only when the final seed landed in an opponent pit that
    now holds exactly 4 seeds. The capture then chains backwards (against the
    sowing direction) over consecutive opponent pits holding exactly 4, stopping
    at the first pit that is not an opponent pit or does not hold exactly 4.

    Grand-slam rule: if the capture would leave the opponent with no seeds at all
    on their side, the entire capture is annulled — the board is returned
    unchanged, nothing is scored, and a single `annulled_capture` event is
    emitted so the caller can report it.

    Returns `(new_board, captured_count, events)`.
    """
    if not _is_opponent_pit(last_index, player) or board[last_index] != 4:
        return board, 0, []

    captured_pits: list[int] = []
    idx = last_index
    while _is_opponent_pit(idx, player) and board[idx] == 4:
        captured_pits.append(idx)
        idx = (idx - 1) % NUM_PITS

    captured_count = 4 * len(captured_pits)

    opp_start = (1 - player) * PITS_PER_SIDE
    opp_total = sum(board[i] for i in range(opp_start, opp_start + PITS_PER_SIDE))
    if opp_total - captured_count == 0:  # grand slam -> annul entire capture
        return board, 0, [{"type": "annulled_capture", "pits": list(captured_pits)}]

    new_board = list(board)
    events: list[dict] = []
    for pit in captured_pits:
        new_board[pit] = 0
        events.append({"type": "capture", "pit": pit, "seeds": 4})

    return tuple(new_board), captured_count, events


def _reaches_opponent(board: tuple[int, ...], pit: int, player: int) -> bool:
    """True if sowing `pit` drops at least one seed onto the opponent's side."""
    sown, _ = sow(board, pit)
    return any(_is_opponent_pit(i, player) and sown[i] > board[i] for i in range(NUM_PITS))


def legal_moves(state: GameState) -> list[int]:
    """Return the pits the player to move may legally play, in ascending order.

    Candidates are the mover's own non-empty pits. Under the feeding rule, if the
    opponent's side is entirely empty the mover must play a pit whose sowing
    delivers at least one seed to the opponent; if no such move exists the list
    is empty (the game will end by starvation — handled in endings).
    """
    board = state.board
    player = state.player
    candidates = [p for p in state.own_pits() if board[p] > 0]

    if state.side_total(1 - player) == 0:
        return [p for p in candidates if _reaches_opponent(board, p, player)]

    return candidates


def apply_move(state: GameState, pit: int) -> tuple[GameState, list[dict]]:
    """Play `pit` and return the resulting state and an ordered event list.

    Validates legality (raising `IllegalMove`), sows, resolves captures, credits
    any captured seeds to the mover, and passes the turn. Events are emitted in
    play order: one `sow` event per seed drop, then `capture` events per pit, or
    a single `annulled_capture` event if the grand-slam rule voided the capture.
    """
    if pit not in legal_moves(state):
        if _is_opponent_pit(pit, state.player):
            raise IllegalMove(f"Pit {pit}: Not your pit")
        elif state.board[pit] == 0:
            raise IllegalMove(f"Pit {pit}: Pit is empty")
        else:
            raise IllegalMove(f"Pit {pit}: You must leave your opponent a move")

    player = state.player
    sown_board, path = _apply_sow(state.board, pit)
    last = path[-1]

    events: list[dict] = [{"type": "sow", "pit": i} for i in path]

    new_board, captured, capture_events = resolve_capture(sown_board, last, player)
    events.extend(capture_events)

    new_scores = list(state.scores)
    new_scores[player] += captured

    new_state = GameState(
        board=new_board,
        scores=(new_scores[0], new_scores[1]),
        player=1 - player,
        ply=state.ply + 1,
    )
    return new_state, events
