# Ayò Ọlọ́pọ́n — Online Board Game

Ayò Ọlọ́pọ́n is a traditional mathematical mancala board game of the Yoruba people of South Western Nigeria. Known as the "Game of the Intellectual," it is a finite, deterministic game of perfect information. It is modeled mathematically as a circular zero-sum combinatorial system where seed redistribution operates under circular modular arithmetic.

This project implements a web-based version of Ayo with a stateless FastAPI backend rules engine, an adversarial minimax CPU agent, and an interactive, responsive HTML5/CSS3/JavaScript frontend.

---

## 🎮 Game Rules & Mechanics

### 1. Board Representation
*   **The Grid:** A 2×6 layout of 12 pits.
    *   **South (Player 0):** Pits `0` to `5` (left-to-right along the bottom).
    *   **North (Player 1):** Pits `6` to `11` (reversed right-to-left along the top).
*   **Sowing Direction:** Counter-clockwise: `0 → 1 → ... → 5 → 11 → 10 → ... → 6 → 0`.
*   **Initial State:** 4 seeds per pit (48 total active seeds). Scores begin at `0 - 0`.

### 2. Circular Modulo Sowing
*   Redistribution lifts all seeds from a chosen pit and drops them one-by-one counter-clockwise.
*   **Starting Pit Skip Rule:** If a sowing contains $\ge 12$ seeds (looping back to the origin), the starting pit is skipped during redistribution, requiring modulo-11 arithmetic. The origin remains empty at the end of sowing.

### 3. Capture Rules
*   **Landing Condition:** A capture triggers only when the final seed lands in an opponent's pit and makes exactly **4 seeds** (house win).
*   **Chain Captures:** Sowing then checks backwards (against sowing direction) in adjacent opponent pits. Any consecutive preceding pits containing exactly 4 seeds are also captured. The chain stops at the first pit that is not an opponent's pit or does not contain exactly 4 seeds.
*   **Grand-Slam Annulment:** If a capture would leave the opponent with zero seeds on their side, the entire capture is annulled (no seeds scored, seeds stay in place), allowing the opponent to continue playing.

### 4. Tournament-Accurate Feeding Rules (Lookahead)
*   If the opponent's side is currently empty, the player is obligated to choose a move that delivers at least one seed to the opponent's side.
*   If the opponent's side is not empty, the player is prohibited from making a move that would empty the opponent's side (either by capturing all their seeds or failing to feed them), unless no alternative exists.
*   If no feeding move is possible (opponent is empty and no move can reach them), the game ends by starvation and the mover collects all remaining seeds on their own side.

### 5. Endgame Loop Resolution (Repetition Detection)
*   To resolve infinite cycling of a few remaining seeds, the game tracks visited states.
*   If any configuration `(board, player_to_move)` is reached a second time (repetition), the game ends immediately. Each player adds the seeds currently on their side of the board to their final score.

---

## 🏗️ Architecture

The project is structured as a decoupled, stateless client-server application:

```
ayo/
├── engine/               # Pure Python package (no dependencies)
│   ├── __init__.py
│   ├── state.py          # Immutable GameState representation
│   ├── rules.py          # Sowing, captures, and lookahead legal moves
│   └── endings.py        # Win, draw, starvation, & repetition endings
├── ai/
│   ├── __init__.py
│   ├── heuristic.py      # Positional evaluation utility
│   └── search.py         # Iterative-deepening alpha-beta with transposition table
├── api/
│   └── main.py           # FastAPI server and stateless endpoints
├── web/
│   ├── index.html        # HTML structure
│   ├── style.css         # Theme styles, mobile queries, and animations
│   └── app.js            # Frontend logic, audio synthesizer, and local persistence
└── tests/                # Automated pytest suite
```

### Stateless API Contract
Every request carries the full board state and history. The server computes the transitions and legality, returning the new state, generated events, next legal moves, and game-over state.
- `POST /new-game` → Initialize a new game.
- `POST /move` → Apply human move validation and execution.
- `POST /cpu-move` → Select CPU move using selected difficulty levels.

---

## 🌟 Frontend features

*   **Rich Aesthetics:** Deep warm-themed board styled with HSL gradients, shadows, and glassmorphism.
*   **Responsive Layout:** Automatically scales down to mobile size (375px viewports) with optimized touch targets ($\ge 44\text{px}$).
*   **Web Audio Synth:** Synthesizes realistic seed drops, captures, and victory melodies using the browser's Web Audio API (completely offline-friendly).
*   **Ota Match Series:** Tracks consecutive wins across games. The first player to win 3 straight games is declared **Ota** (champion) with a dedicated screen, while the loser is labeled **Ope** (novice).
*   **Teaching Hints:** A "Hint" button in vs-CPU Easy mode highlights the AI's suggested move (computed at Medium difficulty) without playing it.
*   **State Persistence & Undo:** Automatically saves games to `localStorage` for resumption and supports multi-ply Undo.

---

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- Virtualenv or Conda

### Installation

1.  Clone the repository and navigate to the project directory:
    ```bash
    cd ayo
    ```

2.  Create and activate a virtual environment:
    ```bash
    python3 -m venv .venv
    source .venv/bin/env/activate  # Or your platform equivalent
    ```

3.  Install development dependencies:
    ```bash
    pip install fastapi uvicorn pydantic pytest httpx
    ```

### Running the Game

1.  Start the FastAPI backend server:
    ```bash
    uvicorn api.main:app --reload
    ```

2.  Open your browser and navigate to `http://localhost:8000` to play the game.

### Running Tests

Execute the automated test suite to verify rules and AI algorithms:
```bash
pytest
```
