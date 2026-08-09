// CARTRIDGE B — DOCX DUNGEON: a first-person raycaster whose entire level
// is the "FLOOR PLAN" paragraph further down the document. The driver
// re-reads that paragraph while you play, so drawing a wall in the plan —
// or typing your name into it — raises architecture in front of you,
// textured with the very glyphs you typed.
//
//   #  stone wall     %  gilt wall      . or space  floor
//   P  you start here E  the exit door  ¶  a ghost haunts here
//   any other character: a wall rendered IN that character
//
// Find the E door and serve it. The pilcrow ghosts disagree.

import {
  COLS,
  ROWS,
  VIEW_ROWS,
  HUD_ROWS,
  makeGrid,
  hash2,
  drawText,
  drawBigTextCentered,
  fmtTime,
} from "./engine.js";

export const PLAN_W = 48;
export const PLAN_H = 22;

const MOVE_V = 3.4; // cells/s
const STRAFE_V = 2.7;
const TURN_V = 2.6; // rad/s
const FOV_PLANE = 0.66; // tan(FOV/2) ≈ 66°
const BODY_R = 0.28;
const GHOST_WANDER_V = 1.5;
const GHOST_CHASE_V = 2.3;
const GHOST_SIGHT = 9;
const CATCH_R = 0.6;

// ─── Default floor plan (seeded into the document as CARTRIDGE B) ─────
function buildPlan() {
  const m = Array.from({ length: PLAN_H }, () => new Array(PLAN_W).fill("."));
  const put = (y, x, ch) => {
    if (y >= 0 && y < PLAN_H && x >= 0 && x < PLAN_W) m[y][x] = ch;
  };
  const h = (y, x0, x1, ch = "#") => {
    for (let x = x0; x <= x1; x++) put(y, x, ch);
  };
  const v = (x, y0, y1, ch = "#") => {
    for (let y = y0; y <= y1; y++) put(y, x, ch);
  };
  // Outer walls.
  h(0, 0, PLAN_W - 1);
  h(PLAN_H - 1, 0, PLAN_W - 1);
  v(0, 0, PLAN_H - 1);
  v(PLAN_W - 1, 0, PLAN_H - 1);
  // A few chambers and corridors.
  v(16, 1, 8);
  put(4, 16, ".");
  put(5, 16, ".");
  h(8, 8, 24);
  put(8, 12, ".");
  put(8, 13, ".");
  v(32, 8, 20);
  put(14, 32, ".");
  put(15, 32, ".");
  h(14, 6, 26);
  put(14, 20, ".");
  put(14, 21, ".");
  // The gilt vestibule around the exit door, top-right.
  v(40, 1, 6, "%");
  h(6, 40, 46, "%");
  put(3, 40, ".");
  put(2, 46, "E");
  // Founders' pillars: letters are walls, textured with themselves.
  put(17, 6, "D");
  put(17, 9, "O");
  put(17, 12, "C");
  put(17, 15, "X");
  // Cast.
  put(19, 3, "P");
  put(4, 24, "¶");
  put(11, 38, "¶");
  put(18, 40, "¶");
  return m.map((row) => row.join(""));
}

export const DUNGEON_PLAN = buildPlan();

// ─── Palettes (5 distance bands, near → far). Side walls (E/W faces)
//     borrow the next band down: two-tone shading with zero extra colors.
const STONE = ["EAF2FA", "C0D2E4", "8FA9C4", "5E7C9C", "35506E"];
const GILT = ["FFF3C4", "FFDE7A", "E0B54E", "A98833", "6E5A22"];
const LETTER = ["F3E8FF", "D6B4FE", "A78BFA", "7C5CD6", "52339E"];
const EXIT_A = ["FFF7D6", "FFE9A8", "FFD75E", "D9A441", "A87B26"];
const EXIT_B = ["FFFFFF", "FFF7D6", "FFE9A8", "FFD75E", "D9A441"];
const GHOST = ["F4F8FF", "C9D8F2", "93ACD1", "5F7BA6", "3A5378"];
const STONE_GLYPH = ["#", "#", "=", ":", "."];
const GILT_GLYPH = ["%", "%", "=", ":", "."];
const FLOOR_NEAR = "39516F";
const FLOOR_FAR = "22334D";
const INK = {
  hud: "9CB3C9",
  banner: "FFD75E",
  bannerAlt: "7FD7F0",
  hurt: "FF5470",
};

const bandOf = (d) => (d < 2 ? 0 : d < 4 ? 1 : d < 7 ? 2 : d < 11 ? 3 : 4);

export function createDocxDungeon() {
  const state = {
    rows: null,
    grid: null, // PLAN_W×PLAN_H chars, "." for floor
    spawn: { x: 3.5, y: 19.5 },
    ghosts: new Map(), // spawnKey → {x, y, heading}
    px: 3.5,
    py: 19.5,
    angle: 0,
    drafts: 3,
    time: 0,
    phase: "card", // card | play | win | gameover
    phaseT: 0,
    flash: 0, // red vignette timer after a catch
    won: false,
  };

  function hardReset() {
    state.drafts = 3;
    state.time = 0;
    state.phase = "card";
    state.phaseT = 0;
    state.flash = 0;
    state.px = state.spawn.x;
    state.py = state.spawn.y;
    state.angle = 0;
    for (const [key, gh] of state.ghosts) {
      const [x, y] = key.split(",").map(Number);
      gh.x = x + 0.5;
      gh.y = y + 0.5;
    }
  }

  const cellAt = (cx, cy) => {
    if (cx < 0 || cx >= PLAN_W || cy < 0 || cy >= PLAN_H) return "#";
    return state.grid[cy][cx];
  };
  // applySource normalizes the grid before storage (P and ¶ become floor),
  // so cells are only ".", "E", or wall glyphs.
  const isWall = (ch) => ch !== "." && ch !== "E";
  const isSolid = (ch) => ch !== "."; // the E door blocks movement too
  const solidCell = (cx, cy) => isSolid(cellAt(cx, cy));

  function applySource(rows) {
    state.rows = rows;
    const grid = [];
    let spawn = null;
    const ghostSpawns = new Set();
    for (let y = 0; y < PLAN_H; y++) {
      const row = [];
      for (let x = 0; x < PLAN_W; x++) {
        let ch = rows[y]?.[x] ?? ".";
        if (ch === " ") ch = ".";
        if (ch === "P") {
          spawn = { x: x + 0.5, y: y + 0.5 };
          ch = ".";
        } else if (ch === "¶") {
          ghostSpawns.add(`${x},${y}`);
          ch = ".";
        }
        row.push(ch);
      }
      grid.push(row.join(""));
    }
    state.grid = grid;
    if (spawn) state.spawn = spawn;
    for (const key of [...state.ghosts.keys()]) {
      if (!ghostSpawns.has(key)) state.ghosts.delete(key);
    }
    for (const key of ghostSpawns) {
      if (!state.ghosts.has(key)) {
        const [x, y] = key.split(",").map(Number);
        state.ghosts.set(key, { x: x + 0.5, y: y + 0.5, heading: hash2(x, y) * 6.28 });
      }
    }
    // If an edit sealed the player inside a wall, step out to nearby floor.
    if (solidCell(Math.floor(state.px), Math.floor(state.py))) {
      outer: for (let r = 1; r < 6; r++) {
        for (let dy = -r; dy <= r; dy++) {
          for (let dx = -r; dx <= r; dx++) {
            if (!solidCell(Math.floor(state.px) + dx, Math.floor(state.py) + dy)) {
              state.px = Math.floor(state.px) + dx + 0.5;
              state.py = Math.floor(state.py) + dy + 0.5;
              break outer;
            }
          }
        }
      }
    }
  }

  /** Move a circle through the grid, sliding on walls. Returns the wall
   *  character that blocked motion (for E-door detection), else null. */
  function slide(o, dx, dy) {
    let bumped = null;
    for (const [mx, my] of [
      [dx, 0],
      [0, dy],
    ]) {
      const nx = o.x + mx;
      const ny = o.y + my;
      const cx = Math.floor(nx + Math.sign(mx) * BODY_R);
      const cy = Math.floor(ny + Math.sign(my) * BODY_R);
      const hit =
        (mx !== 0 &&
          (solidCell(cx, Math.floor(o.y - BODY_R)) || solidCell(cx, Math.floor(o.y + BODY_R)))) ||
        (my !== 0 &&
          (solidCell(Math.floor(o.x - BODY_R), cy) || solidCell(Math.floor(o.x + BODY_R), cy)));
      if (hit) {
        const bx = mx !== 0 ? cx : Math.floor(o.x);
        const by = my !== 0 ? cy : Math.floor(o.y);
        bumped = cellAt(bx, by);
      } else {
        o.x = nx;
        o.y = ny;
      }
    }
    return bumped;
  }

  /** Grid line-of-sight via ray sampling (cheap and good enough for AI). */
  function canSee(x0, y0, x1, y1) {
    const dist = Math.hypot(x1 - x0, y1 - y0);
    if (dist > GHOST_SIGHT) return false;
    const steps = Math.ceil(dist * 3);
    for (let i = 1; i < steps; i++) {
      const t = i / steps;
      if (isWall(cellAt(Math.floor(x0 + (x1 - x0) * t), Math.floor(y0 + (y1 - y0) * t))))
        return false;
    }
    return true;
  }

  function tickPlay(dt, input, fx) {
    state.time += dt;
    if (state.flash > 0) state.flash -= dt;

    // Steering: W/S walk, A/D (and ◄►) turn, Q/E sidestep.
    if (input.down("a", "arrowleft")) state.angle -= TURN_V * dt;
    if (input.down("d", "arrowright")) state.angle += TURN_V * dt;
    const cos = Math.cos(state.angle);
    const sin = Math.sin(state.angle);
    let mx = 0;
    let my = 0;
    if (input.down("w", "arrowup")) {
      mx += cos * MOVE_V * dt;
      my += sin * MOVE_V * dt;
    }
    if (input.down("s", "arrowdown")) {
      mx -= cos * MOVE_V * dt;
      my -= sin * MOVE_V * dt;
    }
    if (input.down("q")) {
      mx += sin * STRAFE_V * dt;
      my -= cos * STRAFE_V * dt;
    }
    if (input.down("e")) {
      mx -= sin * STRAFE_V * dt;
      my += cos * STRAFE_V * dt;
    }
    const me = { x: state.px, y: state.py };
    const bumped = slide(me, mx, my);
    state.px = me.x;
    state.py = me.y;
    if (bumped === "E") {
      state.phase = "win";
      state.phaseT = 0;
      fx.win();
      return;
    }

    // Ghosts: drift until they see you, then glide in. Wander turns are
    // rolled once per ~1.7s window (not per tick, which would spin them).
    const wanderWindow = Math.floor(state.time * 0.6);
    for (const gh of state.ghosts.values()) {
      const sees = canSee(gh.x, gh.y, state.px, state.py);
      if (sees) {
        gh.heading = Math.atan2(state.py - gh.y, state.px - gh.x);
      } else if (gh.lastWindow !== wanderWindow) {
        gh.lastWindow = wanderWindow;
        if (hash2(wanderWindow, Math.floor(gh.x * 7 + gh.y * 13)) < 0.55) {
          gh.heading += (hash2(Math.floor(gh.x * 31), wanderWindow) - 0.5) * 3;
        }
      }
      const v = sees ? GHOST_CHASE_V : GHOST_WANDER_V;
      const before = { x: gh.x, y: gh.y };
      slide(gh, Math.cos(gh.heading) * v * dt, Math.sin(gh.heading) * v * dt);
      if (Math.abs(gh.x - before.x) < 0.001 && Math.abs(gh.y - before.y) < 0.001) {
        gh.heading += Math.PI / 2 + hash2(Math.floor(gh.x), Math.floor(gh.y)) * 1.5;
      }
      if (Math.hypot(gh.x - state.px, gh.y - state.py) < CATCH_R) {
        state.drafts--;
        state.flash = 0.8;
        fx.hurt();
        state.px = state.spawn.x;
        state.py = state.spawn.y;
        state.angle = 0;
        for (const [key, g2] of state.ghosts) {
          const [x, y] = key.split(",").map(Number);
          g2.x = x + 0.5;
          g2.y = y + 0.5;
        }
        if (state.drafts <= 0) {
          state.phase = "gameover";
          state.phaseT = 0;
          fx.lose();
        }
        return;
      }
    }
  }

  function tick(dt, input, fx) {
    state.phaseT += dt;
    switch (state.phase) {
      case "card":
        if (state.phaseT > 1.4 && state.rows) state.phase = "play";
        break;
      case "play":
        if (state.rows) tickPlay(dt, input, fx);
        if (input.down("r")) hardReset();
        break;
      case "win":
      case "gameover":
        if (input.down("r", "enter")) hardReset();
        break;
    }
  }

  function render(t) {
    const g = makeGrid();
    const O = HUD_ROWS;
    const horizon = Math.floor(VIEW_ROWS / 2);

    if (state.grid && state.phase !== "card") {
      const dirX = Math.cos(state.angle);
      const dirY = Math.sin(state.angle);
      const planeX = -dirY * FOV_PLANE;
      const planeY = dirX * FOV_PLANE;
      const zbuf = new Float32Array(COLS).fill(1e9);

      for (let x = 0; x < COLS; x++) {
        const cameraX = (2 * x) / COLS - 1;
        const rayX = dirX + planeX * cameraX;
        const rayY = dirY + planeY * cameraX;
        let mapX = Math.floor(state.px);
        let mapY = Math.floor(state.py);
        const deltaX = Math.abs(1 / (rayX || 1e-9));
        const deltaY = Math.abs(1 / (rayY || 1e-9));
        const stepX = rayX < 0 ? -1 : 1;
        const stepY = rayY < 0 ? -1 : 1;
        let sideX = rayX < 0 ? (state.px - mapX) * deltaX : (mapX + 1 - state.px) * deltaX;
        let sideY = rayY < 0 ? (state.py - mapY) * deltaY : (mapY + 1 - state.py) * deltaY;
        let side = 0;
        let cell = "#";
        for (let i = 0; i < 96; i++) {
          if (sideX < sideY) {
            sideX += deltaX;
            mapX += stepX;
            side = 0;
          } else {
            sideY += deltaY;
            mapY += stepY;
            side = 1;
          }
          cell = cellAt(mapX, mapY);
          if (isWall(cell) || cell === "E") break;
        }
        const perp = Math.max(
          0.08,
          side === 0 ? sideX - deltaX : sideY - deltaY
        );
        zbuf[x] = perp;

        const lineH = Math.min(VIEW_ROWS + 4, Math.round((VIEW_ROWS * 1.25) / perp));
        const y0 = Math.max(0, horizon - (lineH >> 1));
        const y1 = Math.min(VIEW_ROWS - 1, horizon + (lineH >> 1));
        let band = Math.min(4, bandOf(perp) + (side === 1 ? 1 : 0));
        let glyph;
        let pal;
        if (cell === "E") {
          pal = (t * 3) % 2 < 1 ? EXIT_A : EXIT_B;
          glyph = "E";
        } else if (cell === "#") {
          pal = STONE;
          glyph = STONE_GLYPH[band];
        } else if (cell === "%") {
          pal = GILT;
          glyph = GILT_GLYPH[band];
        } else {
          pal = LETTER;
          glyph = cell; // typed characters ARE the texture
        }
        const ink = pal[band];
        for (let y = y0; y <= y1; y++) {
          g.chars[y + O][x] = glyph;
          g.colors[y + O][x] = ink;
        }
        // Floor: closer screen rows are brighter. Color depends only on the
        // row, so floor spans merge into very few runs.
        for (let y = y1 + 1; y < VIEW_ROWS; y++) {
          g.chars[y + O][x] = ".";
          g.colors[y + O][x] = y > VIEW_ROWS - 6 ? FLOOR_NEAR : FLOOR_FAR;
        }
      }

      // Ghost sprites, far to near, depth-tested per column.
      const ghosts = [...state.ghosts.values()]
        .map((gh) => ({ gh, d: Math.hypot(gh.x - state.px, gh.y - state.py) }))
        .sort((a, b) => b.d - a.d);
      const invDet = 1 / (planeX * dirY - dirX * planeY);
      for (const { gh } of ghosts) {
        const rx = gh.x - state.px;
        const ry = gh.y - state.py;
        const tx = invDet * (dirY * rx - dirX * ry);
        const ty = invDet * (-planeY * rx + planeX * ry);
        if (ty <= 0.2) continue;
        const sx = Math.floor((COLS / 2) * (1 + tx / ty));
        const size = Math.min(VIEW_ROWS, Math.round((VIEW_ROWS * 0.9) / ty));
        const wide = Math.max(1, Math.round(size * 1.1));
        const band = bandOf(ty);
        const ink = GHOST[band];
        for (let dx = -(wide >> 1); dx <= wide >> 1; dx++) {
          const col = sx + dx;
          if (col < 0 || col >= COLS || ty >= zbuf[col]) continue;
          // Taper the block so the ghost reads as a figure, not a slab.
          const edge = Math.abs(dx) / Math.max(1, wide >> 1);
          const h = Math.max(1, Math.round(size * (1 - edge * edge * 0.55)));
          const gy0 = Math.max(0, horizon - (h >> 1));
          const gy1 = Math.min(VIEW_ROWS - 1, horizon + (h >> 1));
          for (let y = gy0; y <= gy1; y++) {
            g.chars[y + O][col] = "¶";
            g.colors[y + O][col] = ink;
          }
        }
      }

      // A caught frame stings: red edge vignette while the flash decays.
      if (state.flash > 0) {
        for (let x = 0; x < COLS; x++) {
          if (g.chars[O][x] === " ") g.chars[O][x] = "-";
          g.colors[O][x] = INK.hurt;
          g.colors[ROWS - 1][x] = INK.hurt;
        }
      }
    }

    // Phase dressing.
    if (state.phase === "card") {
      drawBigTextCentered(g, 7, "DOCX DUNGEON", INK.banner);
      const sub = "FIND AND SERVE THE E DOOR — THE FLOOR PLAN IS PRINTED BELOW THE SCREEN";
      drawText(g, Math.floor((COLS - sub.length) / 2), 15, sub, INK.bannerAlt);
    } else if (state.phase === "win") {
      drawBigTextCentered(g, 6, "EXECUTED", INK.banner);
      drawBigTextCentered(g, 13, "& DELIVERED", INK.banner);
      const msg = `TIME ${fmtTime(state.time)}  ·  DRAFTS LEFT ${state.drafts}  ·  PRESS R TO RE-SERVE`;
      drawText(g, Math.floor((COLS - msg.length) / 2), 20, msg, INK.bannerAlt);
    } else if (state.phase === "gameover") {
      drawBigTextCentered(g, 6, "STRICKEN", INK.hurt);
      const sub = "FROM THE RECORD · PRESS R TO REFILE";
      drawText(g, Math.floor((COLS - sub.length) / 2), 14, sub, INK.hud);
    }

    // HUD.
    const hud =
      `DOCX DUNGEON  ·  ${compass(state.angle)}` +
      `  ·  DRAFTS ${"@".repeat(Math.max(0, state.drafts))}${".".repeat(Math.max(0, 3 - state.drafts))}` +
      `  ·  ${fmtTime(state.time)}  ·  GHOSTS ${state.ghosts.size}  ·  THE MAP IS THE DOCUMENT`;
    drawText(g, 1, 0, hud.slice(0, COLS - 2), INK.hud);
    return g;
  }

  const compass = (a) => {
    const names = ["E", "SE", "S", "SW", "W", "NW", "N", "NE"];
    return names[Math.round(((a % (Math.PI * 2)) + Math.PI * 2) / (Math.PI / 4)) % 8];
  };

  hardReset();

  return {
    name: "dungeon",
    label: "Docx Dungeon",
    bg: "070B14",
    hint:
      "W/S walk · A/D turn · Q/E sidestep · R restart · the FLOOR PLAN paragraph below is the level — type into it and the walls appear around you",
    reset: hardReset,
    sourceKey: () => "plan",
    onSource: applySource,
    onKeyTap: () => {},
    tick,
    render,
    statusWord: () =>
      `${state.phase} drafts:${state.drafts} pos:${state.px.toFixed(1)},${state.py.toFixed(1)}`,
    debug: state,
  };
}
