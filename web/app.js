"use strict";

// The frontend never computes legality itself: it renders the state the server
// returns and only enables the pits the server lists in `legal_moves`.

// Visual pit order per row. Sowing runs counter-clockwise
// 0->1->...->11->0, so laying South (player 0) left-to-right along the bottom
// and North (player 1) reversed along the top makes the cycle read
// counter-clockwise: rightward across the bottom, up to pit 6, then leftward
// across the top and back down to pit 0.
const ROW_NORTH = [11, 10, 9, 8, 7, 6];
const ROW_SOUTH = [0, 1, 2, 3, 4, 5];

const PLAYER_NAMES = { 0: "South", 1: "North" };

// In vs-CPU mode the human plays South (player 0) and moves first; the CPU
// plays North (player 1).
const CPU_PLAYER = 1;

// Sowing animation: one seed-drop every SOW_MS. Disabled (instant) when the
// user prefers reduced motion. Capture flash + seed flight lasts CAPTURE_MS.
const SOW_MS = 120;
const CAPTURE_MS = 450;
const ANIMATE = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const MUTE_KEY = "ayo.muted";

const GAME_OVER_DETAIL = {
  score: "",
  draw: "",
  starvation: "by starvation",
  ply_cap: "move limit reached",
};

const STORAGE_KEY = "ayo.save.v1";

const el = {
  board: document.getElementById("board"),
  undo: document.getElementById("undo"),
  resume: document.getElementById("resume"),
  resumeDetail: document.getElementById("resume-detail"),
  resumeYes: document.getElementById("resume-yes"),
  resumeNo: document.getElementById("resume-no"),
  rowNorth: document.getElementById("row-north"),
  rowSouth: document.getElementById("row-south"),
  scoreNorth: document.getElementById("score-value-north"),
  scoreSouth: document.getElementById("score-value-south"),
  scorePanelNorth: document.getElementById("score-north"),
  scorePanelSouth: document.getElementById("score-south"),
  turn: document.getElementById("turn-indicator"),
  status: document.getElementById("status"),
  newGame: document.getElementById("new-game"),
  modeButtons: Array.from(document.querySelectorAll(".mode-btn")),
  difficulty: document.getElementById("difficulty"),
  difficultyLabel: document.getElementById("difficulty-label"),
  mute: document.getElementById("mute"),
  toastHost: document.getElementById("toast-host"),
  banner: document.getElementById("banner"),
  bannerTitle: document.getElementById("banner-title"),
  bannerDetail: document.getElementById("banner-detail"),
  bannerNewGame: document.getElementById("banner-new-game"),
};

const game = {
  state: null,
  legalMoves: [],
  history: [], // [{ pit, events }] — one entry per applied ply, human and CPU
  mode: "pvp", // "pvp" | "cpu"
  difficulty: "medium", // "easy" | "medium" | "hard" — CPU strength
  busy: false, // a move (possibly incl. the CPU reply) is being processed
  thinking: false, // the CPU is choosing a move
  animating: false, // a sowing animation is playing back
  over: false, // game has ended; no pit is playable
};

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// --- Sound (synthesized via Web Audio — no asset files, works offline) ----
// Distinct cues for seed drops, captures, and wins. The AudioContext is
// created/resumed on a user gesture (the first move) to satisfy autoplay
// policy; later CPU-move sounds reuse the already-unlocked context.

function readMuted() {
  try {
    return localStorage.getItem(MUTE_KEY) === "1";
  } catch {
    return false;
  }
}

const sound = {
  ctx: null,
  muted: readMuted(),

  ensure() {
    if (this.muted) return;
    try {
      if (!this.ctx) {
        const Ctx = window.AudioContext || window.webkitAudioContext;
        if (!Ctx) return;
        this.ctx = new Ctx();
      }
      if (this.ctx.state === "suspended") this.ctx.resume();
    } catch {
      // Audio unavailable — silently continue.
    }
  },

  _blip(freq, dur, type, gain, when = 0) {
    if (this.muted || !this.ctx) return;
    const t = this.ctx.currentTime + when;
    const osc = this.ctx.createOscillator();
    const env = this.ctx.createGain();
    osc.type = type;
    osc.frequency.value = freq;
    env.gain.setValueAtTime(0.0001, t);
    env.gain.exponentialRampToValueAtTime(gain, t + 0.008);
    env.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    osc.connect(env).connect(this.ctx.destination);
    osc.start(t);
    osc.stop(t + dur + 0.02);
  },

  drop() {
    this.ensure();
    this._blip(680, 0.06, "triangle", 0.1);
  },

  capture() {
    this.ensure();
    this._blip(523.25, 0.12, "sine", 0.2);
    this._blip(783.99, 0.16, "sine", 0.2, 0.09);
  },

  win() {
    this.ensure();
    [523.25, 659.25, 783.99, 1046.5].forEach((f, i) =>
      this._blip(f, 0.18, "sine", 0.16, i * 0.11)
    );
  },
};

// --- Persistence (localStorage) ------------------------------------------

function save() {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        state: game.state,
        mode: game.mode,
        difficulty: game.difficulty,
        history: game.history,
        legalMoves: game.legalMoves,
        over: game.over,
      })
    );
  } catch {
    // Storage unavailable (private mode / quota) — play continues unsaved.
  }
}

function loadSave() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY));
  } catch {
    return null;
  }
}

function cpuLabel(player) {
  return game.mode === "cpu" && player === CPU_PLAYER
    ? `${PLAYER_NAMES[player]} (CPU)`
    : PLAYER_NAMES[player];
}

function pitElement(index, seeds, legal) {
  const pit = document.createElement("div");
  pit.className =
    "pit" +
    (seeds === 0 ? " is-empty" : "") +
    (legal ? " is-legal" : " is-disabled");
  pit.dataset.pit = String(index);

  const count = document.createElement("span");
  count.className = "pit-count";
  count.textContent = String(seeds);
  pit.appendChild(count);

  const label = document.createElement("span");
  label.className = "pit-index";
  label.textContent = String(index);
  pit.appendChild(label);

  return pit;
}

function renderRow(container, indices, legalSet) {
  container.replaceChildren(
    ...indices.map((i) => pitElement(i, game.state.board[i], legalSet.has(i)))
  );
}

function render() {
  if (!game.state) return;
  const { scores, player } = game.state;
  // No pit is playable while the CPU thinks or a sowing is animating.
  const locked = game.over || game.thinking || game.animating;
  const legalSet = locked ? new Set() : new Set(game.legalMoves);

  renderRow(el.rowNorth, ROW_NORTH, legalSet);
  renderRow(el.rowSouth, ROW_SOUTH, legalSet);

  el.scoreSouth.textContent = String(scores[0]);
  el.scoreNorth.textContent = String(scores[1]);

  if (game.over) {
    el.turn.textContent = "Game over";
  } else if (game.thinking) {
    el.turn.textContent = `${cpuLabel(player)} is thinking…`;
  } else {
    el.turn.textContent = `${cpuLabel(player)} to move`;
  }
  el.scorePanelSouth.classList.toggle("is-turn", !game.over && player === 0);
  el.scorePanelNorth.classList.toggle("is-turn", !game.over && player === 1);

  el.undo.disabled =
    game.busy || game.thinking || game.animating || game.history.length === 0;
}

function setStatus(message, isError = false) {
  el.status.textContent = message;
  el.status.classList.toggle("is-error", isError);
}

function toast(message) {
  const node = document.createElement("div");
  node.className = "toast";
  node.textContent = message;
  el.toastHost.appendChild(node);
  // Matches the toast-out animation end (~2s total) plus a small buffer.
  setTimeout(() => node.remove(), 2100);
}

function announceCaptures(events, mover) {
  const captured = events
    .filter((e) => e.type === "capture")
    .reduce((sum, e) => sum + e.seeds, 0);
  if (captured > 0) {
    toast(`${PLAYER_NAMES[mover]} captured ${captured} seeds!`);
  }
  if (events.some((e) => e.type === "annulled_capture")) {
    toast("Grand slam — capture annulled!");
  }
}

function showGameOver(gameOver) {
  game.over = true;
  const { winner, reason, scores } = gameOver;

  // Final scores may include end-of-game seed collection (starvation / ply cap),
  // so display the game_over scores rather than the board's captured-only totals.
  el.scoreSouth.textContent = String(scores[0]);
  el.scoreNorth.textContent = String(scores[1]);

  el.bannerTitle.textContent =
    winner === null ? "It's a draw!" : `${cpuLabel(winner)} wins!`;

  const detail = GAME_OVER_DETAIL[reason] || "";
  el.bannerDetail.textContent =
    `Final score — South ${scores[0]}, North ${scores[1]}` +
    (detail ? ` (${detail})` : "");

  el.banner.hidden = false;
}

// --- Sowing animation ----------------------------------------------------
// The animation mutates the existing pit DOM directly (so CSS transitions
// aren't destroyed by a rebuild); render() re-syncs to game.state at the end.

function pitNode(index) {
  return el.board.querySelector(`.pit[data-pit="${index}"]`);
}

function setPitCount(index, count) {
  const node = pitNode(index);
  if (!node) return;
  node.querySelector(".pit-count").textContent = String(count);
  node.classList.toggle("is-empty", count === 0);
}

function pulsePit(index) {
  const node = pitNode(index);
  if (!node) return;
  node.classList.remove("pit-drop");
  void node.offsetWidth; // force reflow so the animation restarts each drop
  node.classList.add("pit-drop");
}

// Replay the sow events one seed-drop at a time from `preBoard`, lifting the
// origin pit and dropping into each receiving pit with an arc/scale pulse.
async function animateSow(preBoard, pit, events) {
  const working = preBoard.slice();
  working[pit] = 0; // lift all seeds from the played pit
  setPitCount(pit, 0);
  for (const ev of events) {
    if (ev.type !== "sow") continue;
    await sleep(SOW_MS);
    working[ev.pit] += 1;
    setPitCount(ev.pit, working[ev.pit]);
    pulsePit(ev.pit);
    sound.drop();
  }
}

// Flash each captured pit and fly a few seeds from it to the mover's score
// panel, with a capture sound. The board/score numbers update afterwards via
// render(); this is purely the visual/audible flourish.
async function animateCaptures(events, mover) {
  const captures = events.filter((e) => e.type === "capture");
  if (captures.length === 0) return;

  sound.capture();
  const scorePanel = mover === 0 ? el.scorePanelSouth : el.scorePanelNorth;
  for (const ev of captures) {
    const node = pitNode(ev.pit);
    if (!node) continue;
    node.classList.add("pit-capture");
    flySeeds(node, scorePanel, ev.seeds);
  }
  await sleep(CAPTURE_MS);
  for (const ev of captures) {
    const node = pitNode(ev.pit);
    if (node) node.classList.remove("pit-capture");
  }
}

function flySeeds(fromNode, toNode, count) {
  const from = fromNode.getBoundingClientRect();
  const to = toNode.getBoundingClientRect();
  const originX = from.left + from.width / 2;
  const originY = from.top + from.height / 2;
  const dx = to.left + to.width / 2 - originX;
  const dy = to.top + to.height / 2 - originY;
  const n = Math.min(count, 4);
  for (let i = 0; i < n; i++) {
    const seed = document.createElement("div");
    seed.className = "flying-seed";
    seed.style.left = `${originX}px`;
    seed.style.top = `${originY}px`;
    seed.style.transitionDelay = `${i * 40}ms`;
    document.body.appendChild(seed);
    requestAnimationFrame(() => {
      seed.style.transform = `translate(${dx}px, ${dy}px) scale(0.3)`;
      seed.style.opacity = "0";
    });
    setTimeout(() => seed.remove(), CAPTURE_MS + 250 + i * 40);
  }
}

// Update local game state from a /move or /cpu-move response. `mover` is the
// player who just played (for capture attribution); `pit` is the pit they
// played (recorded in history for undo). When `animate` is set, the sowing is
// played back before the final board is shown. Returns true if the game ended.
async function applyResult(data, mover, pit, animate = true) {
  const preBoard = game.state.board.slice(); // board still shown before this move
  game.state = data.state;
  game.legalMoves = data.legal_moves;
  game.history.push({ pit, events: data.events });

  if (animate && ANIMATE) {
    game.animating = true;
    try {
      await animateSow(preBoard, pit, data.events);
      await animateCaptures(data.events, mover);
    } finally {
      game.animating = false;
    }
  } else if (data.events.some((e) => e.type === "capture")) {
    sound.capture(); // still cue captures when animation is off
  }

  announceCaptures(data.events, mover);
  render(); // re-sync DOM to the true state (captures, scores, turn, legality)
  const over = Boolean(data.game_over);
  if (over) {
    showGameOver(data.game_over);
    if (data.game_over.winner !== null) sound.win();
  }
  save();
  return over;
}

async function cpuMove() {
  game.thinking = true;
  render(); // shows the "thinking…" indicator and locks the board
  try {
    const mover = game.state.player; // the CPU (captured before state updates)
    // Enforce a brief minimum so the indicator is perceptible even though the
    // random mover responds instantly.
    const [res] = await Promise.all([
      fetch("/cpu-move", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ state: game.state, difficulty: game.difficulty }),
      }),
      sleep(450),
    ]);
    if (!res.ok) {
      setStatus(`CPU move failed (${res.status})`, true);
      return;
    }
    const data = await res.json();
    game.thinking = false;
    await applyResult(data, mover, data.chosen_pit);
  } catch (err) {
    setStatus(`CPU move failed: ${err.message}`, true);
  } finally {
    game.thinking = false;
  }
}

async function playMove(pit) {
  if (game.busy || game.thinking || game.animating || game.over) return;
  game.busy = true;
  sound.ensure(); // unlock audio within this user gesture
  setStatus("");
  try {
    const mover = game.state.player;
    const res = await fetch("/move", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ state: game.state, pit }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      setStatus(body.detail || `Move rejected (${res.status})`, true);
      return;
    }
    const data = await res.json();
    const over = await applyResult(data, mover, pit);
    if (!over && game.mode === "cpu" && game.state.player === CPU_PLAYER) {
      await cpuMove();
    }
  } catch (err) {
    setStatus(`Move failed: ${err.message}`, true);
  } finally {
    game.busy = false;
  }
}

function onBoardClick(event) {
  const pitNode = event.target.closest(".pit");
  if (!pitNode) return;
  const pit = Number(pitNode.dataset.pit);
  // Trust the server's legal-move list, never a client-side legality guess.
  if (game.legalMoves.includes(pit)) playMove(pit);
}

async function newGame() {
  game.over = false;
  game.busy = false;
  game.thinking = false;
  game.history = [];
  el.banner.hidden = true;
  el.resume.hidden = true;
  setStatus("Dealing seeds…");
  try {
    const res = await fetch("/new-game", { method: "POST" });
    if (!res.ok) throw new Error(`Server responded ${res.status}`);
    const data = await res.json();
    game.state = data.state;
    game.legalMoves = data.legal_moves;
    syncControls();
    render();
    save();
    setStatus("");
  } catch (err) {
    setStatus(`Could not start a game: ${err.message}`, true);
  }
}

// Undo one full move. In PvP that is a single ply; in vs-CPU it is the CPU
// reply plus the human move that prompted it, returning control to the human.
// Because the human always plays even history indices, the target is the last
// even index: remove 2 plies when an even number are recorded, else 1.
async function undo() {
  if (game.busy || game.thinking || game.animating || game.history.length === 0) return;
  const removeCount =
    game.mode === "cpu" && game.history.length % 2 === 0 ? 2 : 1;
  const remaining = game.history.slice(0, game.history.length - removeCount);
  await replay(remaining);
}

// Rebuild the game purely from a list of moves: deal a fresh board, then
// re-apply each recorded pit through /move (deterministic — replaying the CPU's
// actual pit reproduces its move and events).
async function replay(moves) {
  game.busy = true;
  setStatus("");
  try {
    const fresh = await (await fetch("/new-game", { method: "POST" })).json();
    let state = fresh.state;
    let legal = fresh.legal_moves;
    let gameOver = null;
    const rebuilt = [];
    for (const { pit } of moves) {
      const res = await fetch("/move", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ state, pit }),
      });
      if (!res.ok) throw new Error(`replay rejected pit ${pit} (${res.status})`);
      const data = await res.json();
      rebuilt.push({ pit, events: data.events });
      state = data.state;
      legal = data.legal_moves;
      gameOver = data.game_over;
    }
    game.state = state;
    game.legalMoves = legal;
    game.history = rebuilt;
    game.over = false;
    el.banner.hidden = true;
    render();
    // Removing the finishing move(s) should clear the game-over state; if a
    // remaining move still ends the game, honor it defensively.
    if (gameOver) showGameOver(gameOver);
    save();
  } catch (err) {
    setStatus(`Undo failed: ${err.message}`, true);
  } finally {
    game.busy = false;
    render();
  }
}

// Reflect mode/difficulty into the controls: the difficulty picker only makes
// sense in vs-CPU mode.
function syncControls() {
  el.difficulty.value = game.difficulty;
  el.difficultyLabel.classList.toggle("is-hidden", game.mode !== "cpu");
}

function selectMode(mode) {
  game.mode = mode;
  el.modeButtons.forEach((btn) =>
    btn.classList.toggle("is-active", btn.dataset.mode === mode)
  );
  newGame();
}

function resumeSavedGame(saved) {
  el.resume.hidden = true;
  game.state = saved.state;
  game.mode = saved.mode || "pvp";
  game.difficulty = saved.difficulty || "medium";
  game.history = saved.history || [];
  game.legalMoves = saved.legalMoves || [];
  game.over = false;
  game.busy = false;
  game.thinking = false;
  el.modeButtons.forEach((btn) =>
    btn.classList.toggle("is-active", btn.dataset.mode === game.mode)
  );
  syncControls();
  render();
  setStatus("");
  // A save taken between the human's move and the CPU's reply leaves the CPU to
  // move; let it proceed so the position settles back to the human's turn.
  if (game.mode === "cpu" && game.state.player === CPU_PLAYER) {
    cpuMove();
  }
}

function offerResume(saved) {
  const turn = PLAYER_NAMES[saved.state.player];
  const moves = saved.history.length;
  el.resumeDetail.textContent =
    `${saved.mode === "cpu" ? "vs CPU" : "2 players"} — ${turn} to move, ` +
    `${moves} move${moves === 1 ? "" : "s"} played.`;
  el.resume.hidden = false;
}

function init() {
  const saved = loadSave();
  if (
    saved &&
    saved.state &&
    Array.isArray(saved.history) &&
    saved.history.length > 0 &&
    !saved.over
  ) {
    offerResume(saved);
  } else {
    newGame();
  }
}

el.board.addEventListener("click", onBoardClick);
el.newGame.addEventListener("click", newGame);
el.bannerNewGame.addEventListener("click", newGame);
el.undo.addEventListener("click", undo);
el.difficulty.addEventListener("change", () => {
  game.difficulty = el.difficulty.value;
  save();
});

function updateMuteButton() {
  el.mute.textContent = sound.muted ? "🔇" : "🔊";
  el.mute.setAttribute("aria-pressed", String(sound.muted));
}

el.mute.addEventListener("click", () => {
  sound.muted = !sound.muted;
  try {
    localStorage.setItem(MUTE_KEY, sound.muted ? "1" : "0");
  } catch {
    // Persisting the mute preference failed; the in-memory toggle still works.
  }
  if (!sound.muted) sound.ensure();
  updateMuteButton();
});

updateMuteButton();
el.resumeYes.addEventListener("click", () => resumeSavedGame(loadSave()));
el.resumeNo.addEventListener("click", newGame);
el.modeButtons.forEach((btn) =>
  btn.addEventListener("click", () => selectMode(btn.dataset.mode))
);

init();
