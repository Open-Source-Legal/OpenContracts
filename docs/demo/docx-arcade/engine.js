// The Docx Arcade's shared engine: cell-grid framebuffer, grid→OOXML frame
// writer, OOXML→text cartridge reader, a 3×5 banner font, key/gamepad input,
// and a square-wave bleeper. Game cartridges (courier-quest.js,
// docx-dungeon.js) import from here; arcade.js drives everything against a
// live DocxSession.
//
// The frame-writer pattern (one w:p per frame, colored runs + w:br rows,
// Unid-preserving replaceXml) follows the Docx Observatory demo
// (JSv4/Docxodus docs/demo/ascii-scenes.js). The run-count economics are the
// same here: every color change inside a row is its own w:r and each run has
// real conversion cost, so palettes are banded and spaces piggyback on the
// current run. Games should budget ≲250 runs per frame.

// ─── Screen geometry ──────────────────────────────────────────────────
// 92 columns of 8pt Courier New ≈ 6.1in — fits the blank doc's 6.5in text
// column without wrapping. Line rule "exact" 200 twips (10pt) gives a
// terminal-ish cell aspect of ~2:1 (height:width).
export const COLS = 92;
export const ROWS = 26;
export const FONT = "Courier New";
export const SZ = 16; // w:sz half-points → 8pt
export const LINE_TWIPS = 200; // 10pt exact line height

// Row 0 is the HUD; the playfield is everything below it.
export const HUD_ROWS = 1;
export const VIEW_ROWS = ROWS - HUD_ROWS;

// ─── Tiny deterministic noise (no Math.random: frames must be a pure
//     function of t so replays and tests stay honest) ──────────────────
export function hash2(x, y) {
  let h = (x * 374761393 + y * 668265263) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}

export function makeGrid() {
  const chars = [], colors = [];
  for (let y = 0; y < ROWS; y++) {
    chars.push(new Array(COLS).fill(" "));
    colors.push(new Array(COLS).fill("FFFFFF"));
  }
  return { chars, colors };
}

/** Write a string into the grid. Spaces are transparent unless `opaque`. */
export function drawText(g, x, y, str, color, opaque = false) {
  if (y < 0 || y >= ROWS) return;
  for (let i = 0; i < str.length; i++) {
    const cx = x + i;
    if (cx < 0 || cx >= COLS) continue;
    const ch = str[i];
    if (ch === " " && !opaque) continue;
    g.chars[y][cx] = ch;
    g.colors[y][cx] = color;
  }
}

// ─── Frame → OOXML ────────────────────────────────────────────────────
const esc = (s) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

/** Merge each row's cells into runs: a new run only where a visible glyph
 *  changes color (spaces piggyback on the current run — background ink
 *  is invisible, so they never force a split). */
function rowRuns(chars, colors) {
  const runs = [];
  let text = "", color = null;
  for (let x = 0; x < COLS; x++) {
    const ch = chars[x];
    if (ch !== " " && colors[x] !== color && color !== null) {
      runs.push([text, color]);
      text = "";
    }
    if (ch !== " ") color = colors[x] ?? color;
    text += ch;
  }
  runs.push([text, color ?? "9CB3C9"]);
  return runs;
}

/** The whole frame as one w:p: the captured opening tag (which carries the
 *  paragraph's Unid — THE thing that keeps the anchor stable across frames),
 *  a pPr with shading + exact line height, then per row: colored runs joined
 *  by w:br. */
export function frameXml(openTag, grid, bg) {
  const parts = [
    openTag,
    "<w:pPr>",
    `<w:spacing w:before="0" w:after="0" w:line="${LINE_TWIPS}" w:lineRule="exact"/>`,
    `<w:shd w:val="clear" w:color="auto" w:fill="${bg}"/>`,
    "</w:pPr>",
  ];
  let runs = 0;
  for (let y = 0; y < ROWS; y++) {
    if (y > 0) parts.push("<w:r><w:br/></w:r>");
    for (const [text, color] of rowRuns(grid.chars[y], grid.colors[y])) {
      runs++;
      parts.push(
        `<w:r><w:rPr><w:rFonts w:ascii="${FONT}" w:hAnsi="${FONT}" w:cs="${FONT}"/>` +
          `<w:color w:val="${color}"/><w:sz w:val="${SZ}"/><w:szCs w:val="${SZ}"/></w:rPr>` +
          `<w:t xml:space="preserve">${esc(text)}</w:t></w:r>`
      );
    }
  }
  parts.push("</w:p>");
  return { xml: parts.join(""), runs };
}

/** A static monospace paragraph (cartridge): one run per line joined by
 *  w:br, single ink color, dark shading — a blueprint the player can edit.
 *
 *  Spaces are emitted as NBSP: a line of ordinary spaces hangs at the line
 *  end under pre-wrap, so the browser refuses to place a caret inside it
 *  and typing into blank level rows silently goes nowhere. NBSP renders
 *  identically in the editor but stays caret-addressable; paraXmlToRows
 *  folds it back to a plain space when the game reads the level. */
export function cartridgeXml(openTag, rows, { ink = "8FA8C4", bg = "0E1626" } = {}) {
  const parts = [
    openTag,
    "<w:pPr>",
    `<w:spacing w:before="0" w:after="0" w:line="${LINE_TWIPS}" w:lineRule="exact"/>`,
    `<w:shd w:val="clear" w:color="auto" w:fill="${bg}"/>`,
    "</w:pPr>",
  ];
  for (let i = 0; i < rows.length; i++) {
    if (i > 0) parts.push("<w:r><w:br/></w:r>");
    parts.push(
      `<w:r><w:rPr><w:rFonts w:ascii="${FONT}" w:hAnsi="${FONT}" w:cs="${FONT}"/>` +
        `<w:color w:val="${ink}"/><w:sz w:val="${SZ}"/><w:szCs w:val="${SZ}"/></w:rPr>` +
        `<w:t xml:space="preserve">${esc(rows[i]).replace(/ /g, " ")}</w:t></w:r>`
    );
  }
  parts.push("</w:p>");
  return parts.join("");
}

// ─── OOXML → text (reading a cartridge back out of the document) ──────
const unesc = (s) =>
  s
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&amp;/g, "&");

/**
 * Flatten a paragraph's XML into text rows. Only w:t (text), w:br/w:cr
 * (row breaks) and w:tab (a space) matter; every other element — including
 * whatever run formatting the player applied from the ribbon — is layout
 * we don't care about. Rows are padded/truncated to `width`; the row count
 * is padded to `height` so a half-deleted cartridge degrades to empty
 * space instead of crashing the game.
 *
 * Docxodus re-serializes every element with p1:Unid attributes, so the
 * break/tab patterns must tolerate attributes. The paragraph's pPr block
 * is stripped first: a w:tabs tab-stop definition in there would otherwise
 * read as a phantom leading space.
 */
export function paraXmlToRows(xml, width, height) {
  const rows = [];
  let cur = "";
  const body = xml.replace(/<w:pPr[\s\S]*?<\/w:pPr>/, "");
  const re = /<w:(br|cr|tab)(?:\s[^>]*)?\/>|<w:t(?:\s[^>]*)?>([\s\S]*?)<\/w:t>/g;
  let m;
  while ((m = re.exec(body)) !== null) {
    if (m[1] === "br" || m[1] === "cr") {
      rows.push(cur);
      cur = "";
    } else if (m[1] === "tab") {
      cur += " ";
    } else {
      cur += unesc(m[2]).replace(/ /g, " ");
    }
  }
  rows.push(cur);
  while (rows.length < height) rows.push("");
  return rows
    .slice(0, height)
    .map((r) => (r.length >= width ? r.slice(0, width) : r.padEnd(width, " ")));
}

/**
 * Flatten a rendered cartridge block (the editor's live DOM) into text rows.
 *
 * The editor commits typed text to the session only on BLUR, so while the
 * player is typing into a level its paragraph's freshest text exists only in
 * the DOM. The renderer emits each w:br as a sentinel span containing only
 * bidi marks (it cannot use <br>), so: a child whose text is entirely bidi
 * marks is a row break; everything else contributes its text (bidi marks
 * stripped, NBSP folded to space) to the current row.
 */
export function domBlockToRows(el, width, height) {
  const rows = [];
  let cur = "";
  const BIDI = /[‎‏⁦-⁩]/g;
  for (const child of el.childNodes) {
    const raw = child.textContent ?? "";
    const text = raw.replace(BIDI, "");
    if (raw.length > 0 && text.length === 0) {
      rows.push(cur);
      cur = "";
    } else {
      cur += text.replace(/ /g, " ");
    }
  }
  rows.push(cur);
  while (rows.length < height) rows.push("");
  return rows
    .slice(0, height)
    .map((r) => (r.length >= width ? r.slice(0, width) : r.padEnd(width, " ")));
}

// ─── 3×5 banner font ──────────────────────────────────────────────────
// Each glyph is five 3-char strings; `1` marks ink. Enough alphabet for
// the arcade's shouting: titles, verdicts, room cards.
const FONT3X5 = {
  A: ["010", "101", "111", "101", "101"],
  B: ["110", "101", "110", "101", "110"],
  C: ["011", "100", "100", "100", "011"],
  D: ["110", "101", "101", "101", "110"],
  E: ["111", "100", "110", "100", "111"],
  F: ["111", "100", "110", "100", "100"],
  G: ["011", "100", "101", "101", "011"],
  H: ["101", "101", "111", "101", "101"],
  I: ["111", "010", "010", "010", "111"],
  J: ["001", "001", "001", "101", "010"],
  K: ["101", "110", "100", "110", "101"],
  L: ["100", "100", "100", "100", "111"],
  M: ["101", "111", "111", "101", "101"],
  N: ["101", "111", "111", "111", "101"],
  O: ["010", "101", "101", "101", "010"],
  P: ["110", "101", "110", "100", "100"],
  Q: ["010", "101", "101", "011", "001"],
  R: ["110", "101", "110", "110", "101"],
  S: ["011", "100", "010", "001", "110"],
  T: ["111", "010", "010", "010", "010"],
  U: ["101", "101", "101", "101", "111"],
  V: ["101", "101", "101", "101", "010"],
  W: ["101", "101", "111", "111", "101"],
  X: ["101", "101", "010", "101", "101"],
  Y: ["101", "101", "010", "010", "010"],
  Z: ["111", "001", "010", "100", "111"],
  0: ["111", "101", "101", "101", "111"],
  1: ["010", "110", "010", "010", "111"],
  2: ["110", "001", "010", "100", "111"],
  3: ["110", "001", "010", "001", "110"],
  4: ["101", "101", "111", "001", "001"],
  5: ["111", "100", "110", "001", "110"],
  6: ["011", "100", "110", "101", "010"],
  7: ["111", "001", "010", "010", "010"],
  8: ["010", "101", "010", "101", "010"],
  9: ["010", "101", "011", "001", "110"],
  "!": ["010", "010", "010", "000", "010"],
  "&": ["010", "101", "010", "101", "011"],
  "-": ["000", "000", "111", "000", "000"],
  ".": ["000", "000", "000", "000", "010"],
  " ": ["000", "000", "000", "000", "000"],
};

/** Width of `text` rendered in the banner font (3 cols + 1 gap per glyph). */
export function bigTextWidth(text) {
  return text.length * 4 - 1;
}

/** Stamp `text` into the grid in 3×5 blocks of `glyph`. */
export function drawBigText(g, x, y, text, color, glyph = "#") {
  let cx = x;
  for (const raw of text.toUpperCase()) {
    const rowsDef = FONT3X5[raw] ?? FONT3X5[" "];
    for (let r = 0; r < 5; r++) {
      const gy = y + r;
      if (gy < 0 || gy >= ROWS) continue;
      for (let c = 0; c < 3; c++) {
        if (rowsDef[r][c] === "1") {
          const gx = cx + c;
          if (gx >= 0 && gx < COLS) {
            g.chars[gy][gx] = glyph;
            g.colors[gy][gx] = color;
          }
        }
      }
    }
    cx += 4;
  }
}

/** Center a banner line horizontally. */
export function drawBigTextCentered(g, y, text, color, glyph = "#") {
  drawBigText(g, Math.floor((COLS - bigTextWidth(text)) / 2), y, text, color, glyph);
}

// ─── Input: keyboard (capture-phase) + gamepad ────────────────────────
// Two owners for the keyboard: the GAME (keys are gameplay, default
// prevented so the caret never eats them) and the DOCUMENT (keys are
// typing; the arcade only watches Escape-free). Pointer placement decides:
// pointerdown on the screen paragraph grabs the controls, pointerdown
// anywhere else in the editor hands them back — the document stays a
// document the whole time.
const GAME_KEYS = new Set([
  "w", "a", "s", "d", "q", "e", "r", "p", "m",
  "arrowup", "arrowdown", "arrowleft", "arrowright", " ", "enter",
]);

export function createInput({ onControlChange, onKeyTap }) {
  const held = new Set();
  let control = "doc"; // 'game' | 'doc'

  function setControl(next) {
    if (control === next) return;
    control = next;
    if (next === "doc") held.clear();
    onControlChange?.(next);
  }

  window.addEventListener(
    "keydown",
    (ev) => {
      if (ev.key === "Escape") {
        setControl("doc");
        return;
      }
      if (control !== "game") return;
      const key = ev.key.toLowerCase();
      if (!GAME_KEYS.has(key) || ev.ctrlKey || ev.metaKey || ev.altKey) return;
      ev.preventDefault();
      ev.stopPropagation();
      if (!ev.repeat) {
        held.add(key);
        onKeyTap?.(key);
      }
    },
    true
  );
  window.addEventListener(
    "keyup",
    (ev) => {
      held.delete(ev.key.toLowerCase());
    },
    true
  );
  window.addEventListener("blur", () => held.clear());

  /** The gamepad gets its own held-set, merged with the keyboard's at read
   *  time, so a pad release never clobbers a held key (and vice versa).
   *  D-pad/left stick → arrows, A → space (jump), shoulders → q/e strafe. */
  const padHeld = new Set();
  function pollGamepad() {
    const pads = navigator.getGamepads?.() ?? [];
    const pad = [...pads].find((p) => p && p.connected);
    if (!pad) {
      padHeld.clear();
      return;
    }
    const on = (idx) => pad.buttons[idx]?.pressed;
    const ax = (idx) => pad.axes[idx] ?? 0;
    const map = {
      arrowup: on(12) || ax(1) < -0.45,
      arrowdown: on(13) || ax(1) > 0.45,
      arrowleft: on(14) || ax(0) < -0.45,
      arrowright: on(15) || ax(0) > 0.45,
      " ": on(0),
      q: on(4),
      e: on(5) || on(1),
    };
    for (const [key, isOn] of Object.entries(map)) {
      if (isOn) {
        if (!padHeld.has(key)) {
          padHeld.add(key);
          onKeyTap?.(key);
          if (control !== "game") setControl("game");
        }
      } else {
        padHeld.delete(key);
      }
    }
  }

  return {
    held,
    pollGamepad,
    down: (...keys) => keys.some((k) => held.has(k) || padHeld.has(k)),
    get control() {
      return control;
    },
    setControl,
  };
}

// ─── Bleeps: a pocket square-wave synth ───────────────────────────────
// Lazy AudioContext (autoplay policy: first gesture unlocks it). Every
// sound is an oscillator with a pitch ramp and an exponential fade.
export function createBleeper() {
  let ctx = null;
  let muted = false;

  function ensure() {
    if (!ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return null;
      ctx = new AC();
    }
    if (ctx.state === "suspended") ctx.resume();
    return ctx;
  }

  function tone(f0, f1, dur, { type = "square", vol = 0.04, at = 0 } = {}) {
    if (muted) return;
    const ac = ensure();
    if (!ac) return;
    const t0 = ac.currentTime + at;
    const osc = ac.createOscillator();
    const gain = ac.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(f0, t0);
    osc.frequency.exponentialRampToValueAtTime(Math.max(20, f1), t0 + dur);
    gain.gain.setValueAtTime(vol, t0);
    gain.gain.exponentialRampToValueAtTime(0.0005, t0 + dur);
    osc.connect(gain).connect(ac.destination);
    osc.start(t0);
    osc.stop(t0 + dur + 0.02);
  }

  return {
    unlock: ensure,
    get muted() {
      return muted;
    },
    setMuted(next) {
      muted = next;
    },
    jump: () => tone(180, 520, 0.14),
    coin: () => {
      tone(920, 920, 0.06);
      tone(1380, 1380, 0.12, { at: 0.06 });
    },
    stomp: () => tone(340, 90, 0.16),
    hurt: () => tone(220, 60, 0.3, { type: "sawtooth", vol: 0.05 }),
    door: () => {
      tone(392, 392, 0.09);
      tone(523, 523, 0.09, { at: 0.09 });
      tone(659, 659, 0.16, { at: 0.18 });
    },
    win: () => {
      [523, 659, 784, 1046].forEach((f, i) => tone(f, f, 0.14, { at: i * 0.12 }));
    },
    lose: () => {
      [392, 330, 262, 196].forEach((f, i) =>
        tone(f, f * 0.97, 0.2, { at: i * 0.16, type: "triangle", vol: 0.06 })
      );
    },
    step: () => tone(120, 100, 0.03, { vol: 0.015 }),
  };
}
