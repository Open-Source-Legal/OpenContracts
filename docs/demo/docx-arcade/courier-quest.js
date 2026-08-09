// CARTRIDGE A — COURIER QUEST: a single-screen platformer set in 8pt
// Courier New. You are @, a process server. Collect every § to unseal the
// exit !, stomp the pilcrows ¶, mind the spikes ^.
//
// The room you are playing IS the "ROOM n" paragraph further down the
// document: the driver re-reads it a couple of times per second and hands
// it back through onSource(). The legend below is deliberately forgiving —
// any character that isn't part of it becomes solid scenery, so typing a
// word into a room builds a ledge you can stand on.
//
//   #  solid slate        =  solid gold        -  one-way platform
//   ^  spikes (fatal)     §  collectible       !  exit (opens when all § held)
//   ¶  pilcrow patrol     @  spawn point       anything else: solid scenery

import {
  COLS,
  VIEW_ROWS,
  HUD_ROWS,
  makeGrid,
  hash2,
  drawText,
  drawBigTextCentered,
} from "./engine.js";

// ─── Physics (cells & seconds; the sim runs at a fixed 30 Hz) ─────────
const WALK = 16;
const GRAVITY = 60;
const JUMP_V = 21;
const TERMINAL_V = 30;
const STOMP_BOUNCE = 12;
const COYOTE = 0.1;
const JUMP_BUFFER = 0.12;
const ENEMY_V = 4;
const HURT_INVULN = 1.2;

const ROOM_W = COLS;
const ROOM_H = VIEW_ROWS;

// ─── Default rooms (seeded into the document as CARTRIDGE A) ──────────
// Built declaratively so the geometry is auditable without counting 92
// columns by eye. The document copy becomes the source of truth after
// seeding — these arrays are only the factory reset.
function blankRoom() {
  return Array.from({ length: ROOM_H }, () => new Array(ROOM_W).fill(" "));
}
const hspan = (m, y, x0, x1, ch) => {
  for (let x = Math.max(0, x0); x <= Math.min(ROOM_W - 1, x1); x++) m[y][x] = ch;
};
const put = (m, y, x, ch) => {
  if (y >= 0 && y < ROOM_H && x >= 0 && x < ROOM_W) m[y][x] = ch;
};
const stamp = (m, y, x, str) => {
  for (let i = 0; i < str.length; i++) if (str[i] !== " ") put(m, y, x + i, str[i]);
};
const finish = (m) => m.map((row) => row.join(""));

function buildRoom1() {
  const m = blankRoom();
  hspan(m, 23, 0, 91, "#");
  hspan(m, 24, 0, 91, "#");
  // Two spike pits carved into the ground.
  for (const [a, b] of [[30, 36], [52, 58]]) {
    hspan(m, 23, a, b, " ");
    hspan(m, 24, a, b, "^");
  }
  hspan(m, 18, 14, 22, "=");
  put(m, 17, 18, "§");
  hspan(m, 14, 26, 34, "=");
  put(m, 13, 30, "§");
  hspan(m, 10, 40, 48, "=");
  put(m, 9, 44, "§");
  hspan(m, 15, 60, 67, "=");
  put(m, 14, 63, "§");
  put(m, 22, 76, "§");
  // Scenery is solid: the exhibit sticker doubles as a high ledge.
  stamp(m, 5, 38, "EXHIBIT A");
  put(m, 4, 42, "§");
  put(m, 22, 68, "¶");
  put(m, 22, 3, "@");
  put(m, 22, 88, "!");
  return finish(m);
}

function buildRoom2() {
  const m = blankRoom();
  hspan(m, 23, 0, 91, "#");
  hspan(m, 24, 0, 91, "#");
  hspan(m, 23, 34, 60, " ");
  hspan(m, 24, 34, 60, "^");
  // A climb of one-way shelves up the left wall...
  hspan(m, 20, 4, 14, "-");
  hspan(m, 17, 12, 22, "-");
  hspan(m, 14, 4, 14, "-");
  hspan(m, 11, 12, 22, "-");
  hspan(m, 8, 4, 14, "-");
  put(m, 19, 8, "§");
  put(m, 13, 8, "§");
  put(m, 7, 8, "§");
  // ...to a gold causeway over the spikes, patrolled at both ends.
  hspan(m, 8, 26, 66, "=");
  put(m, 7, 30, "¶");
  put(m, 7, 58, "¶");
  put(m, 7, 46, "§");
  stamp(m, 16, 40, "OBJECTION");
  put(m, 15, 44, "§");
  // Descend on the right to the sealed door.
  hspan(m, 13, 72, 80, "-");
  hspan(m, 18, 80, 88, "-");
  put(m, 12, 76, "§");
  put(m, 22, 66, "¶");
  put(m, 22, 3, "@");
  put(m, 22, 88, "!");
  return finish(m);
}

function buildRoom3() {
  const m = blankRoom();
  hspan(m, 23, 0, 91, "#");
  hspan(m, 24, 0, 91, "#");
  // The floor is mostly lava — er, spikes.
  for (const [a, b] of [[14, 28], [36, 52], [60, 78]]) {
    hspan(m, 23, a, b, " ");
    hspan(m, 24, a, b, "^");
  }
  // Stepping stones across the pits.
  hspan(m, 19, 18, 24, "=");
  hspan(m, 15, 30, 36, "=");
  hspan(m, 19, 42, 48, "=");
  hspan(m, 13, 52, 58, "=");
  hspan(m, 18, 64, 70, "=");
  put(m, 18, 21, "§");
  put(m, 14, 33, "§");
  put(m, 18, 45, "§");
  put(m, 12, 55, "§");
  put(m, 17, 67, "§");
  put(m, 18, 20, "¶");
  put(m, 12, 54, "¶");
  put(m, 22, 82, "¶");
  stamp(m, 7, 34, "CLOSING ARGUMENT");
  put(m, 6, 41, "§");
  put(m, 22, 3, "@");
  put(m, 22, 88, "!");
  return finish(m);
}

export const QUEST_ROOMS = [
  { label: "THE OPENING BRIEF", rows: buildRoom1() },
  { label: "DISCOVERY", rows: buildRoom2() },
  { label: "CLOSING ARGUMENT", rows: buildRoom3() },
];

// ─── Palette ──────────────────────────────────────────────────────────
const INK = {
  slate: "6B7F99",
  gold: "D9A441",
  oneway: "4FD1C5",
  spike: "FF5470",
  coin: "FFD75E",
  coinHi: "FFF3B0",
  scenery: "56698A",
  enemy: "FF6B6B",
  player: "F5F9FF",
  hud: "9CB3C9",
  star: "31415C",
  locked: "5E7392",
  banner: "FFD75E",
  bannerAlt: "7FD7F0",
};

export function createCourierQuest() {
  const state = {
    room: 0,
    rows: null, // latest cartridge text for the current room
    solids: null, // Uint8 flags per cell: 1 solid, 2 one-way, 3 spikes
    coins: new Set(), // live § cells "x,y"
    collected: [new Set(), new Set(), new Set()],
    killed: [new Set(), new Set(), new Set()],
    enemies: new Map(), // spawnKey → {x, y, dir, alive}
    spawn: { x: 3, y: 21 },
    exit: null,
    player: null,
    lives: 3,
    score: 0,
    time: 0,
    phase: "card", // card | play | clear | win | gameover
    phaseT: 0,
    invuln: 0,
    jumpBufferT: 0,
    coyoteT: 0,
    flash: null, // transient text over the playfield {text, t}
  };

  function resetPlayer() {
    state.player = {
      x: state.spawn.x + 0.5,
      y: state.spawn.y + 0.5,
      vx: 0,
      vy: 0,
      grounded: false,
      face: 1,
    };
  }

  function hardReset() {
    state.room = 0;
    state.lives = 3;
    state.score = 0;
    state.time = 0;
    for (const s of state.collected) s.clear();
    for (const s of state.killed) s.clear();
    state.rows = null;
    state.enemies.clear();
    state.phase = "card";
    state.phaseT = 0;
    resetPlayer();
  }

  /** Rebuild the world from cartridge text. Live entity state survives
   *  where its source cell survives: collected § stay collected, stomped
   *  ¶ stay stomped, a ¶ whose spawn cell was typed over vanishes. */
  function applySource(rows) {
    state.rows = rows;
    const solids = new Uint8Array(ROOM_W * ROOM_H);
    const coins = new Set();
    const enemySpawns = new Set();
    let spawn = null;
    let exit = null;
    for (let y = 0; y < ROOM_H; y++) {
      for (let x = 0; x < ROOM_W; x++) {
        const ch = rows[y][x];
        const key = `${x},${y}`;
        switch (ch) {
          case " ":
            break;
          case "#":
            solids[y * ROOM_W + x] = 1;
            break;
          case "=":
            solids[y * ROOM_W + x] = 1;
            break;
          case "-":
            solids[y * ROOM_W + x] = 2;
            break;
          case "^":
            solids[y * ROOM_W + x] = 3;
            break;
          case "§":
            if (!state.collected[state.room].has(key)) coins.add(key);
            break;
          case "¶":
            if (!state.killed[state.room].has(key)) enemySpawns.add(key);
            break;
          case "@":
            spawn = { x, y };
            break;
          case "!":
            exit = { x, y };
            break;
          default:
            solids[y * ROOM_W + x] = 1;
        }
      }
    }
    state.solids = solids;
    state.coins = coins;
    state.spawn = spawn ?? { x: 3, y: ROOM_H - 4 };
    state.exit = exit;
    // Reconcile enemies with their spawn cells.
    for (const key of [...state.enemies.keys()]) {
      if (!enemySpawns.has(key)) state.enemies.delete(key);
    }
    for (const key of enemySpawns) {
      if (!state.enemies.has(key)) {
        const [x, y] = key.split(",").map(Number);
        state.enemies.set(key, { x: x + 0.5, y: y + 0.5, dir: -1 });
      }
    }
    if (!state.player) resetPlayer();
    // If an edit buried the player, pop them up to open air.
    if (state.player && solidAt(state.player.x, state.player.y)) {
      for (let y = Math.floor(state.player.y); y >= 0; y--) {
        if (!solidAt(state.player.x, y + 0.5)) {
          state.player.y = y + 0.5;
          state.player.vy = 0;
          break;
        }
      }
    }
  }

  const cellFlag = (cx, cy) => {
    if (cx < 0 || cx >= ROOM_W) return 1; // walls beyond the page margin
    if (cy < 0) return 0;
    if (cy >= ROOM_H) return 0;
    return state.solids[cy * ROOM_W + cx];
  };
  const solidAt = (x, y) => cellFlag(Math.floor(x), Math.floor(y)) === 1;

  // ─── Player integration: axis-separated AABB vs the cell grid ───────
  const HALF_W = 0.38;
  const HALF_H = 0.46;

  function moveAxis(p, dx, dy) {
    p.x += dx;
    p.y += dy;
    const x0 = Math.floor(p.x - HALF_W);
    const x1 = Math.floor(p.x + HALF_W);
    const y0 = Math.floor(p.y - HALF_H);
    const y1 = Math.floor(p.y + HALF_H);
    for (let cy = y0; cy <= y1; cy++) {
      for (let cx = x0; cx <= x1; cx++) {
        const flag = cellFlag(cx, cy);
        if (flag === 1) {
          if (dx > 0) p.x = cx - HALF_W - 0.001;
          else if (dx < 0) p.x = cx + 1 + HALF_W + 0.001;
          else if (dy > 0) {
            p.y = cy - HALF_H - 0.001;
            p.vy = 0;
            p.grounded = true;
          } else if (dy < 0) {
            p.y = cy + 1 + HALF_H + 0.001;
            p.vy = 0;
          }
        } else if (flag === 2 && dy > 0) {
          // One-way shelf: only when falling onto it from above.
          const top = cy;
          if (p.y + HALF_H - dy <= top + 0.05) {
            p.y = top - HALF_H - 0.001;
            p.vy = 0;
            p.grounded = true;
          }
        }
      }
    }
  }

  function die(fx) {
    fx.hurt();
    state.lives--;
    state.invuln = HURT_INVULN;
    if (state.lives <= 0) {
      state.phase = "gameover";
      state.phaseT = 0;
      fx.lose();
    } else {
      state.flash = { text: "OBJECTION!", t: 0.9 };
      resetPlayer();
    }
  }

  function tickPlay(dt, input, fx) {
    const p = state.player;
    state.time += dt;
    if (state.invuln > 0) state.invuln -= dt;
    if (state.flash && (state.flash.t -= dt) <= 0) state.flash = null;

    // Input → horizontal intent, buffered jumps, coyote time.
    const left = input.down("a", "arrowleft");
    const right = input.down("d", "arrowright");
    p.vx = (right ? WALK : 0) - (left ? WALK : 0);
    if (p.vx !== 0) p.face = Math.sign(p.vx);
    state.jumpBufferT = Math.max(0, state.jumpBufferT - dt);
    state.coyoteT = p.grounded ? COYOTE : Math.max(0, state.coyoteT - dt);
    if (state.jumpBufferT > 0 && state.coyoteT > 0) {
      p.vy = -JUMP_V;
      state.jumpBufferT = 0;
      state.coyoteT = 0;
      fx.jump();
    }

    p.vy = Math.min(TERMINAL_V, p.vy + GRAVITY * dt);
    p.grounded = false;
    moveAxis(p, p.vx * dt, 0);
    moveAxis(p, 0, p.vy * dt);

    // Fell off the page.
    if (p.y > ROOM_H + 2) {
      die(fx);
      return;
    }

    // Spikes.
    if (state.invuln <= 0) {
      const cx = Math.floor(p.x);
      for (const cy of [Math.floor(p.y), Math.floor(p.y + HALF_H)]) {
        if (cellFlag(cx, cy) === 3) {
          die(fx);
          return;
        }
      }
    }

    // Collectibles.
    const pkey = `${Math.floor(p.x)},${Math.floor(p.y)}`;
    if (state.coins.has(pkey)) {
      state.coins.delete(pkey);
      state.collected[state.room].add(pkey);
      state.score += 100;
      fx.coin();
      if (state.coins.size === 0) fx.door();
    }

    // Pilcrows patrol; stomp or be stung.
    for (const [key, e] of state.enemies) {
      const ex = Math.floor(e.x + e.dir * 0.6);
      const ey = Math.floor(e.y);
      const ahead = cellFlag(ex, ey);
      const floorAhead = cellFlag(ex, ey + 1);
      if (ahead === 1 || (floorAhead !== 1 && floorAhead !== 2)) e.dir *= -1;
      else e.x += e.dir * ENEMY_V * dt;

      const dx = p.x - e.x;
      const dy = p.y - e.y;
      if (Math.abs(dx) < 0.8 && Math.abs(dy) < 0.9) {
        if (p.vy > 2 && dy < -0.25) {
          state.enemies.delete(key);
          state.killed[state.room].add(key);
          state.score += 250;
          p.vy = -STOMP_BOUNCE;
          fx.stomp();
        } else if (state.invuln <= 0) {
          die(fx);
          return;
        }
      }
    }

    // The unsealed exit.
    if (
      state.exit &&
      state.coins.size === 0 &&
      Math.abs(p.x - (state.exit.x + 0.5)) < 0.8 &&
      Math.abs(p.y - (state.exit.y + 0.5)) < 1.0
    ) {
      state.score += 1000;
      if (state.room >= QUEST_ROOMS.length - 1) {
        state.phase = "win";
        state.phaseT = 0;
        fx.win();
      } else {
        state.phase = "clear";
        state.phaseT = 0;
        fx.win();
      }
    }
  }

  function tick(dt, input, fx) {
    state.phaseT += dt;
    switch (state.phase) {
      case "card":
        if (state.phaseT > 1.4 && state.rows) {
          state.phase = "play";
          resetPlayer();
        }
        break;
      case "play":
        if (state.rows) tickPlay(dt, input, fx);
        break;
      case "clear":
        if (state.phaseT > 1.6) {
          state.room++;
          state.rows = null; // wait for the next room's cartridge poll
          state.enemies.clear();
          state.phase = "card";
          state.phaseT = 0;
        }
        break;
      case "win":
      case "gameover":
        if (input.down("r", "enter")) hardReset();
        break;
    }
    if (state.phase === "play" && input.down("r")) {
      // Local retry: rewind the room, keep the score ethos simple.
      state.collected[state.room].clear();
      state.killed[state.room].clear();
      state.lives = 3;
      state.enemies.clear();
      state.rows = null;
      state.phase = "card";
      state.phaseT = 0;
    }
  }

  function onKeyTap(key) {
    if (["w", "arrowup", " "].includes(key)) state.jumpBufferT = JUMP_BUFFER;
  }

  function render(t) {
    const g = makeGrid();
    const O = HUD_ROWS;

    // A thin nebula so empty rooms still look like a place.
    for (let y = 0; y < ROOM_H; y++) {
      for (let x = 0; x < ROOM_W; x++) {
        if (hash2(x * 3, y * 5) < 0.006) {
          g.chars[y + O][x] = ".";
          g.colors[y + O][x] = INK.star;
        }
      }
    }

    if (state.rows) {
      const open = state.coins.size === 0;
      for (let y = 0; y < ROOM_H; y++) {
        for (let x = 0; x < ROOM_W; x++) {
          const ch = state.rows[y][x];
          if (ch === " " || ch === "@" || ch === "¶" || ch === "§") continue;
          let glyph = ch;
          let ink = INK.scenery;
          if (ch === "#") ink = INK.slate;
          else if (ch === "=") ink = INK.gold;
          else if (ch === "-") ink = INK.oneway;
          else if (ch === "^") ink = INK.spike;
          else if (ch === "!") {
            ink = open
              ? (t * 4) % 2 < 1
                ? INK.coin
                : INK.coinHi
              : INK.locked;
          }
          g.chars[y + O][x] = glyph;
          g.colors[y + O][x] = ink;
        }
      }
      // Live § twinkle.
      for (const key of state.coins) {
        const [x, y] = key.split(",").map(Number);
        g.chars[y + O][x] = "§";
        g.colors[y + O][x] = (t * 3 + x) % 2 < 1 ? INK.coin : INK.coinHi;
      }
      for (const e of state.enemies.values()) {
        const x = Math.floor(e.x);
        const y = Math.floor(e.y);
        if (x >= 0 && x < ROOM_W && y >= 0 && y < ROOM_H) {
          g.chars[y + O][x] = "¶";
          g.colors[y + O][x] = INK.enemy;
        }
      }
    }

    // Player (blinks while invulnerable).
    if (state.phase === "play" && state.player) {
      const p = state.player;
      const blink = state.invuln > 0 && (t * 10) % 2 < 1;
      if (!blink) {
        const x = Math.floor(p.x);
        const y = Math.floor(p.y);
        if (x >= 0 && x < ROOM_W && y >= 0 && y < ROOM_H) {
          g.chars[y + O][x] = "@";
          g.colors[y + O][x] = INK.player;
        }
      }
    }

    // Phase dressing.
    if (state.phase === "card") {
      drawBigTextCentered(g, 8, `ROOM ${state.room + 1}`, INK.banner);
      const label = QUEST_ROOMS[state.room]?.label ?? "UNKNOWN FILING";
      drawText(g, Math.floor((COLS - label.length) / 2), 15, label, INK.bannerAlt);
    } else if (state.phase === "clear") {
      drawBigTextCentered(g, 9, "ROOM CLEAR", INK.banner);
    } else if (state.phase === "win") {
      drawBigTextCentered(g, 7, "CASE CLOSED", INK.banner);
      const msg = `SCORE ${state.score}  ·  TIME ${fmtTime(state.time)}  ·  PRESS R FOR A RETRIAL`;
      drawText(g, Math.floor((COLS - msg.length) / 2), 15, msg, INK.bannerAlt);
      // Confetti.
      for (let i = 0; i < 40; i++) {
        const x = Math.floor(hash2(i, 7) * COLS);
        const y = O + Math.floor(((hash2(i, 13) * 10 + t * (2 + hash2(i, 3) * 4)) % 1) * VIEW_ROWS);
        if (g.chars[y]?.[x] === " ") {
          g.chars[y][x] = "*";
          g.colors[y][x] = i % 2 ? INK.coin : INK.bannerAlt;
        }
      }
    } else if (state.phase === "gameover") {
      drawBigTextCentered(g, 8, "MISTRIAL", INK.spike);
      const msg = "PRESS R TO RETRY THE CASE";
      drawText(g, Math.floor((COLS - msg.length) / 2), 16, msg, INK.hud);
    }
    if (state.flash) {
      drawText(
        g,
        Math.floor((COLS - state.flash.text.length) / 2),
        6,
        state.flash.text,
        INK.spike
      );
    }

    // HUD.
    const total = state.coins.size + state.collected[state.room].size;
    const hud =
      `COURIER QUEST  ROOM ${state.room + 1}/${QUEST_ROOMS.length}` +
      `  ·  § ${String(state.collected[state.room].size).padStart(2, "0")}/${String(total).padStart(2, "0")}` +
      `  ·  ${"@".repeat(Math.max(0, state.lives))}${".".repeat(Math.max(0, 3 - state.lives))}` +
      `  ·  ${fmtTime(state.time)}  ·  SCORE ${String(state.score).padStart(6, "0")}`;
    drawText(g, 1, 0, hud.slice(0, COLS - 2), INK.hud);
    return g;
  }

  const fmtTime = (s) =>
    `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

  hardReset();

  return {
    name: "quest",
    label: "Courier Quest",
    bg: "0B1322",
    hint:
      "A/D or ◄► move · W/▲/Space jump · R retry room · scroll down and EDIT the room — type a word, it becomes a platform",
    reset: hardReset,
    sourceKey: () => `room${state.room}`,
    onSource: applySource,
    onKeyTap,
    tick,
    render,
    statusWord: () =>
      `${state.phase} r${state.room + 1} lives:${state.lives} §:${state.coins.size}`,
    debug: state,
  };
}
