// The Docx Arcade driver. Seeds one real Word document — title, screen,
// captions, and both game cartridges as plain monospace paragraphs — through
// DocxSession's agentic editing surface, then runs the selected game against
// it: per frame, a Unid-preserving raw.replaceXml on the screen paragraph and
// one editor.refresh() (incremental: exactly one block repaints).
//
// The controls story: the KEYBOARD has two owners. Click the screen and the
// game takes it (WASD play, caret never moves). Click anywhere else and the
// document takes it back — and because the driver re-reads the active
// cartridge paragraph a couple of times per second, whatever you type into a
// ROOM or the FLOOR PLAN becomes level geometry while the game is running.
//
// Host pages supply the dock DOM; see index.html. The per-frame OOXML
// mechanics follow the Docx Observatory (JSv4/Docxodus, docs/demo/).

import {
  COLS,
  ROWS,
  VIEW_ROWS,
  FONT,
  frameXml,
  cartridgeXml,
  paraXmlToRows,
  domBlockToRows,
  drawText,
  createInput,
  createBleeper,
} from "./engine.js";
import { createCourierQuest, QUEST_ROOMS } from "./courier-quest.js";
import { createDocxDungeon, DUNGEON_PLAN, PLAN_W, PLAN_H } from "./docx-dungeon.js";

const SIM_STEP = 1 / 30; // fixed-step sim; rendering floats with the pace
const SOURCE_POLL_FRAMES = 5; // re-read the active cartridge every N frames

/** Minimal HTML escape for the one dock string not authored by this repo
 *  (editor.lastReconcileFallback) — the stats line renders via innerHTML. */
const escHtml = (s) =>
  String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

// ─── Seeding: build the arcade document through the agentic surface ───
function check(r, what) {
  if (!r.success) throw new Error(`${what} failed: ${r.error?.code} ${r.error?.message}`);
  return r;
}

/** Insert a styled prose paragraph after `anchor`; returns its anchor id. */
function addPara(session, anchor, text, { size = 8, color = "6B7280", bold = false, align = "center", before = 0, after = 0 } = {}) {
  const created = check(session.insertParagraph(anchor, "after", text), `insert "${text.slice(0, 24)}…"`)
    .created[0].id;
  check(
    session.setParagraphFormat(created, { alignment: align, spacingBefore: before, spacingAfter: after }),
    "paragraph format"
  );
  check(
    session.applyFormat(created, null, { bold, fontFamily: FONT, fontSizePts: size, color }),
    "run format"
  );
  return created;
}

/** Insert a cartridge (a level-as-paragraph): placeholder → captured open
 *  tag → replaceXml with monospace rows. Returns its anchor id. */
function addCartridge(session, anchor, rows) {
  const created = check(session.insertParagraph(anchor, "after", "…"), "cartridge insert").created[0].id;
  const seedXml = session.raw.getXml(created);
  const gt = seedXml.indexOf(">");
  let openTag = seedXml.slice(0, gt + 1);
  if (openTag.endsWith("/>")) openTag = openTag.slice(0, -2) + ">";
  const res = session.raw.replaceXml(created, cartridgeXml(openTag, rows));
  if (!res.success) throw new Error(`cartridge replaceXml: ${res.error?.code} ${res.error?.message}`);
  return res.modified[0]?.id ?? created;
}

/** Seed the whole arcade into a blank session. Returns every anchor the
 *  driver needs, plus the screen paragraph's opening tag (it carries the
 *  Unid that keeps the anchor alive across per-frame replaceXml calls). */
export function seedArcade(session) {
  const firstP = session.findByKind("p", "body")[0];
  if (!firstP) throw new Error("blank document has no body paragraph");
  const title = firstP.id;
  check(session.replaceText(title, "THE DOCX ARCADE"), "title");
  check(session.setParagraphFormat(title, { alignment: "center", spacingAfter: 40 }), "title format");
  check(
    session.applyFormat(title, null, { bold: true, fontFamily: FONT, fontSizePts: 14, color: "1F2937" }),
    "title run format"
  );

  const tagline = addPara(
    session,
    title,
    "INSERT COIN — the entire arcade is one Word document.",
    { size: 8, color: "6B7280", after: 120 }
  );

  const screenSeed = check(session.insertParagraph(tagline, "after", "(inserting coin…)"), "screen insert")
    .created[0].id;
  const seedXml = session.raw.getXml(screenSeed);
  const gt = seedXml.indexOf(">");
  let screenOpenTag = seedXml.slice(0, gt + 1);
  if (screenOpenTag.endsWith("/>")) screenOpenTag = screenOpenTag.slice(0, -2) + ">";

  const caption = addPara(
    session,
    screenSeed,
    `The screen above is a single Word paragraph — ${COLS}×${ROWS} characters redrawn live. ` +
      "The cartridges below are paragraphs too: edit them and the games rebuild around you.",
    { size: 8, color: "6B7280", before: 120, after: 160 }
  );
  // A real footnote, because this is a real document.
  check(
    session.insertFootnote(
      caption,
      21, // after "The screen above is a"
      "Each frame is OOXML: colored runs and w:br breaks in one Word paragraph, swapped in by " +
        "DocxSession.raw.replaceXml and repainted by editor.refresh(). Pause mid-jump and Save — " +
        "the ribbon downloads the frozen frame as .docx.",
    ),
    "footnote"
  );

  const headA = addPara(session, caption, "CARTRIDGE A — COURIER QUEST", {
    size: 10,
    color: "1F2937",
    bold: true,
    align: "left",
    before: 200,
    after: 40,
  });
  let cursor = addPara(
    session,
    headA,
    "# solid · = gold · - one-way shelf · ^ spikes · § collect them all · ¶ pilcrow patrol · " +
      "@ spawn · ! exit — any other character is solid scenery, so typing a word builds a ledge.",
    { size: 8, color: "6B7280", align: "left", after: 80 }
  );
  const cartridges = {};
  QUEST_ROOMS.forEach((room, i) => {
    cursor = addPara(session, cursor, `ROOM ${i + 1} — ${room.label}`, {
      size: 9,
      color: "374151",
      bold: true,
      align: "left",
      before: 120,
      after: 20,
    });
    cursor = cartridges[`room${i}`] = addCartridge(session, cursor, room.rows);
  });

  const headB = addPara(session, cursor, "CARTRIDGE B — DOCX DUNGEON", {
    size: 10,
    color: "1F2937",
    bold: true,
    align: "left",
    before: 240,
    after: 40,
  });
  cursor = addPara(
    session,
    headB,
    "# stone · % gilt · . floor · P you start here · E the exit door · ¶ a ghost — " +
      "any other character becomes a wall textured with itself. This plan IS the level; edit it mid-run.",
    { size: 8, color: "6B7280", align: "left", after: 80 }
  );
  cursor = addPara(session, cursor, "FLOOR PLAN", {
    size: 9,
    color: "374151",
    bold: true,
    align: "left",
    before: 120,
    after: 20,
  });
  cursor = cartridges.plan = addCartridge(session, cursor, DUNGEON_PLAN);

  addPara(
    session,
    cursor,
    "HOW TO PLAY — Click the screen to take the keyboard; Esc gives it back to the document. " +
      "Undo rewinds frame by frame. Save downloads whatever is on screen, mid-jump included.",
    { size: 8, color: "6B7280", align: "left", before: 200 }
  );

  return { screenAnchor: screenSeed, screenOpenTag, cartridges };
}

// ─── The driver ───────────────────────────────────────────────────────
/**
 * `ui`: { games, playpause, reset, pace, mute, embed, stats, hint, chip } —
 * the dock's DOM elements. `params`: URLSearchParams (game, fps).
 * Returns the controller published as window.__arcade.
 */
export function startArcade({ editor, session, ui, params }) {
  if (typeof editor.refresh !== "function") {
    throw new Error("This engine predates DocxEditor.refresh() — the arcade needs docxodus ≥ 9.6.0.");
  }
  const seeded = seedArcade(session);
  let screenAnchor = seeded.screenAnchor;
  const screenOpenTag = seeded.screenOpenTag;
  const cartridgeAnchors = seeded.cartridges;
  editor.refresh();

  const fx = createBleeper();
  const games = [createCourierQuest(), createDocxDungeon()];
  let game = games.find((g) => g.name === params.get("game")) ?? games[0];

  let playing = true;
  let timer = 0;
  let tAnim = 0;
  let acc = 0;
  let lastWall = performance.now();
  let frames = 0;
  let fps = 0;
  let lastRuns = 0;
  let lastFrameEnd = performance.now();
  const timings = { mutate: 0, refresh: 0 };
  let interval = Number(params.get("fps")) ? Math.round(1000 / Number(params.get("fps"))) : Number(ui.pace.value);
  const sourceCache = new Map(); // sourceKey → last raw xml
  let lastSourceKey = null;
  let haltReason = null;

  const input = createInput({
    onControlChange: updateChip,
    onKeyTap: (key) => {
      fx.unlock();
      if (key === "p") {
        setPlaying(!playing);
        return;
      }
      if (key === "m") {
        fx.setMuted(!fx.muted);
        ui.mute.textContent = fx.muted ? "Unmute" : "Mute";
        return;
      }
      game.onKeyTap?.(key);
    },
  });

  function cartridgeDims(sourceKey) {
    return sourceKey === "plan"
      ? { width: PLAN_W, height: PLAN_H }
      : { width: COLS, height: VIEW_ROWS };
  }

  /** Re-read the active cartridge and hand it to the game when it changed.
   *
   *  Two sources of truth, freshest wins: the editor commits typed text to
   *  the session only on blur, so while the player's caret is parked in a
   *  dirty cartridge its live text exists only in the DOM — read the block
   *  element directly so walls rise keystroke by keystroke. Everything else
   *  (undo, agent edits, the committed steady state) reads the model.
   *
   *  A missing paragraph (someone deleted the level) is not fatal: the game
   *  keeps its last world and the stats line says why. */
  function pollSource(force = false) {
    const key = game.sourceKey();
    const anchor = cartridgeAnchors[key];
    if (!anchor) return;
    if (!force && key === lastSourceKey && frames % SOURCE_POLL_FRAMES !== 0) return;
    lastSourceKey = key;
    const { width, height } = cartridgeDims(key);

    let rows = null;
    const el = editor.root.querySelector(`[data-anchor="${unidOf(anchor)}"]`);
    if (el && el.dataset.committedText !== undefined) {
      const flat = (el.textContent ?? "").replace(/[‎‏⁦-⁩]/g, "");
      if (flat !== el.dataset.committedText.replace(/[‎‏⁦-⁩]/g, "")) {
        rows = domBlockToRows(el, width, height);
      }
    }
    if (!rows) {
      let xml;
      try {
        xml = session.raw.getXml(anchor);
      } catch {
        xml = null;
      }
      if (!xml) {
        haltReason = `cartridge "${key}" is missing — Ctrl+Z brings it back`;
        return;
      }
      rows = paraXmlToRows(xml, width, height);
    }
    if (haltReason?.startsWith("cartridge")) haltReason = null;
    const sig = `${key} ${rows.join("\n")}`;
    if (sourceCache.get(key) === sig) return;
    sourceCache.set(key, sig);
    game.onSource(rows);
  }

  function drawFrame() {
    const wall = performance.now();
    const dt = Math.min(0.25, (wall - lastWall) / 1000);
    lastWall = wall;
    tAnim += dt;

    input.pollGamepad();
    acc = Math.min(0.25, acc + dt);
    while (acc >= SIM_STEP) {
      game.tick(SIM_STEP, input, fx);
      acc -= SIM_STEP;
    }
    pollSource();

    const grid = game.render(tAnim);
    if (input.control === "doc") {
      const msg = "  CLICK THE SCREEN TO TAKE THE CONTROLS  ";
      drawText(grid, Math.floor((COLS - msg.length) / 2), ROWS - 1, msg, "F5F9FF", true);
    }

    const { xml, runs } = frameXml(screenOpenTag, grid, game.bg);
    lastRuns = runs;
    const t0 = performance.now();
    const res = session.raw.replaceXml(screenAnchor, xml);
    const t1 = performance.now();
    if (!res.success) {
      haltReason = "the screen paragraph is gone — Ctrl+Z to restore it, then press Play";
      setPlaying(false);
      updateStats();
      return;
    }
    screenAnchor = res.modified[0]?.id ?? res.created[0]?.id ?? screenAnchor;
    editor.refresh();
    const t2 = performance.now();

    const mix = (a, b) => (a === 0 ? b : a * 0.9 + b * 0.1);
    timings.mutate = mix(timings.mutate, t1 - t0);
    timings.refresh = mix(timings.refresh, t2 - t1);
    fps = mix(fps, 1000 / Math.max(1, t2 - wall + (wall - lastFrameEnd)));
    lastFrameEnd = t2;
    frames++;
    updateStats();
  }

  function updateStats() {
    if (haltReason) {
      ui.stats.innerHTML = `<b>halted:</b> ${haltReason}`;
      return;
    }
    const fb = editor.lastReconcileFallback;
    ui.stats.innerHTML =
      `<b>${game.label}</b> · ${game.statusWord()} · <b>${fps.toFixed(1)}</b> fps · ` +
      `replaceXml <b>${timings.mutate.toFixed(1)}</b> ms · refresh <b>${timings.refresh.toFixed(1)}</b> ms · ` +
      `<b>${lastRuns}</b> runs · ` +
      (fb ? `remounted (${escHtml(fb)})` : `<span class="inc">incremental — one block repainted</span>`);
  }

  function updateChip() {
    const gameHasKeys = input.control === "game";
    ui.chip.textContent = gameHasKeys
      ? "GAME has the keyboard — Esc hands it back to the document"
      : "DOCUMENT has the keyboard — click the screen to play";
    ui.chip.dataset.mode = gameHasKeys ? "game" : "doc";
  }

  function loop() {
    if (!playing) return;
    const started = performance.now();
    try {
      drawFrame();
    } catch (e) {
      playing = false;
      ui.stats.textContent = "halted: " + e.message;
      throw e;
    }
    timer = setTimeout(loop, Math.max(0, interval - (performance.now() - started)));
  }

  function setPlaying(next) {
    if (playing === next) return;
    playing = next;
    ui.playpause.textContent = playing ? "Pause" : "Play";
    if (playing) {
      if (haltReason?.startsWith("the screen")) haltReason = null;
      lastWall = performance.now();
      loop();
    } else {
      clearTimeout(timer);
    }
  }

  const gameBtns = new Map();
  for (const g of games) {
    const b = document.createElement("button");
    b.textContent = g.label;
    b.setAttribute("aria-pressed", String(g === game));
    b.addEventListener("click", () => setGame(g.name));
    gameBtns.set(g.name, b);
    ui.games.appendChild(b);
  }
  function setGame(name) {
    const next = games.find((g) => g.name === name);
    if (!next) return;
    game = next;
    game.reset();
    sourceCache.delete(game.sourceKey());
    gameBtns.forEach((b, n) => b.setAttribute("aria-pressed", String(n === name)));
    ui.hint.textContent = game.hint;
    pollSource(true);
    if (!playing) setPlaying(true);
  }

  ui.playpause.addEventListener("click", () => setPlaying(!playing));
  ui.reset.addEventListener("click", () => {
    game.reset();
    pollSource(true);
    if (!playing) setPlaying(true);
  });
  ui.pace.addEventListener("change", () => {
    interval = Number(ui.pace.value);
  });
  ui.mute.addEventListener("click", () => {
    fx.setMuted(!fx.muted);
    ui.mute.textContent = fx.muted ? "Unmute" : "Mute";
  });
  ui.embed.addEventListener("click", async () => {
    const url = location.origin + location.pathname;
    const snippet =
      `<iframe src="${url}" width="1060" height="800" style="border:0;border-radius:12px;overflow:hidden" ` +
      `title="The Docx Arcade — games running inside a live Word document" allow="gamepad; fullscreen" loading="lazy"></iframe>`;
    try {
      await navigator.clipboard.writeText(snippet);
      const old = ui.embed.textContent;
      ui.embed.textContent = "Copied!";
      setTimeout(() => (ui.embed.textContent = old), 1400);
    } catch {
      window.prompt("Copy the embed snippet:", snippet);
    }
  });

  // Pointer placement decides who owns the keyboard. Clicking the screen
  // paragraph grabs the controls (and never drops a caret into the
  // framebuffer); clicking anywhere else is ordinary editing.
  // Anchor unids are library-generated hex, but CSS.escape keeps the
  // attribute selectors robust rather than relying on that format.
  const unidOf = (anchor) => CSS.escape(anchor.split(":")[2]);
  editor.root.addEventListener(
    "pointerdown",
    (ev) => {
      const screenEl = editor.root.querySelector(`[data-anchor="${unidOf(screenAnchor)}"]`);
      if (screenEl && screenEl.contains(ev.target)) {
        // preventDefault keeps the caret out of the framebuffer — but it
        // also suppresses the focus change, so blur the active block
        // explicitly: that is what commits any level text still sitting
        // uncommitted in the DOM to the session model.
        ev.preventDefault();
        if (document.activeElement instanceof HTMLElement && editor.root.contains(document.activeElement)) {
          document.activeElement.blur();
        }
        fx.unlock();
        input.setControl("game");
        if (!playing && !haltReason) setPlaying(true);
      } else {
        input.setControl("doc");
      }
    },
    true
  );

  ui.hint.textContent = game.hint;
  updateChip();
  pollSource(true);
  drawFrame();
  loop();

  return {
    editor,
    session,
    game: () => game.name,
    setGame,
    games: () => games.map((g) => g.name),
    playing: () => playing,
    pause: () => setPlaying(false),
    play: () => setPlaying(true),
    frames: () => frames,
    fps: () => fps,
    timings: () => ({ ...timings, runs: lastRuns }),
    screenAnchor: () => screenAnchor,
    cartridgeAnchors: () => ({ ...cartridgeAnchors }),
    screenText: () =>
      editor.root.querySelector(`[data-anchor="${unidOf(screenAnchor)}"]`)?.textContent ?? "",
    control: () => input.control,
    setControl: (c) => input.setControl(c),
    debugGame: () => game.debug,
    save: () => editor.save(),
  };
}
