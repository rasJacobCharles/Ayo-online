"""Canonical, immutable game state for Ayo.

The board is a 12-pit cycle. Pits 0-5 belong to player 0 (South); pits 6-11
belong to player 1 (North). Sowing runs counter-clockwise: 0->1->...->11->0.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

NUM_PITS = 12
PITS_PER_SIDE = 6
SEEDS_PER_PIT = 4
TOTAL_SEEDS = NUM_PITS * SEEDS_PER_PIT  # 48


@dataclass(frozen=True, slots=True)
class GameState:
    """Immutable snapshot of a game.

    Attributes:
        board: 12-tuple of seed counts, indexed by pit.
        scores: 2-tuple of captured-seed counts, indexed by player.
        player: the player to move (0 or 1).
        ply: number of half-moves played so far (used by the endgame cap).
    """

    board: tuple[int, ...]
    scores: tuple[int, int]
    player: int
    # Excluded from equality/hash so position identity is (board, scores, player)
    # only: lets GameState serve directly as a transposition-table key (Task 4.2)
    # and enables repetition detection (Task 6.2). `ply` still drives the endgame
    # cap in endings.py.
    ply: int = field(default=0, compare=False)

    @classmethod
    def initial(cls, player: int = 0) -> "GameState":
        """Standard opening: 4 seeds in every pit, scores 0-0, player 0 to move."""
        return cls(
            board=tuple([SEEDS_PER_PIT] * NUM_PITS),
            scores=(0, 0),
            player=player,
            ply=0,
        )

    def own_pits(self, player: int | None = None) -> range:
        """Pit indices belonging to `player` (defaults to the player to move)."""
        p = self.player if player is None else player
        start = p * PITS_PER_SIDE
        return range(start, start + PITS_PER_SIDE)

    def opponent_pits(self, player: int | None = None) -> range:
        """Pit indices belonging to `player`'s opponent."""
        p = self.player if player is None else player
        return self.own_pits(1 - p)

    def side_total(self, player: int | None = None) -> int:
        """Total seeds currently on `player`'s side of the board."""
        return sum(self.board[i] for i in self.own_pits(player))

    def with_(self, **changes) -> "GameState":
        """Return a copy with the given fields replaced."""
        return replace(self, **changes)
