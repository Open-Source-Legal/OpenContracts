# Test: Docx Arcade embeddable demo (docs/demo/docx-arcade/)

## Purpose

Verifies the Docx Arcade demo boots against the real docxodus engine, both
games play from keyboard input, and live level editing (the document IS the
level) round-trips: session-level edits and caret typing both reach the
running game, and blur commits typed text to the session model.

## Prerequisites

- Chromium available to Playwright (`playwright-core` + a Chromium executable).
- Network access to jsDelivr **or** a local mirror of
  `docxodus@9.7.0/dist/embed.bundle.js` plus its `dist/wasm/_framework/`
  runtime (the bundle resolves `<module dir>/wasm/_framework/dotnet.js` from
  `import.meta.url`, so mirror the tree beside the bundle).
- No backend needed — the demo is fully client-side.

## Steps

1. Serve a directory that contains both the demo and (if mirroring) the
   engine, so the module import stays same-origin:

   ```bash
   # from a scratch dir containing: engine/ (mirror) and arcade -> docs/demo/docx-arcade
   ln -s /path/to/OpenContracts/docs/demo/docx-arcade arcade
   python3 -m http.server 8901
   ```

2. Open `http://localhost:8901/arcade/?engine=../engine/embed.bundle.js`
   (omit `?engine=` to use the CDN). Wait for the ribbon editor to appear.

3. Confirm boot: the document titled "THE DOCX ARCADE" renders with a dark
   game screen paragraph, the dock appears at the bottom, and
   `window.__arcade` is defined (`window.__arcadeError` must be undefined).

4. Courier Quest sanity:
   - Wait for the ROOM 1 title card to clear (~1.5 s).
   - Click the screen paragraph → the dock chip flips to "GAME has the
     keyboard". Hold `D` → `@` walks right; press `Space` → it jumps.
   - The HUD row (`COURIER QUEST ROOM 1/3 · § 00/06 …`) is part of the
     screen paragraph text (select it with the mouse after pausing).

5. Live level editing (the headline):
   - Press `Esc`, scroll to "ROOM 1 — THE OPENING BRIEF", click an empty
     row of the level paragraph, and type a word (e.g. `HELLO`).
   - Within ~0.5 s the word appears in the running game as solid scenery
     (`window.__arcade.debugGame().rows` contains it) — no blur needed.
   - Click the game screen: the cartridge blurs, and
     `window.__arcade.session.raw.getXml(window.__arcade.cartridgeAnchors().room0)`
     now contains the word (blur committed it to the session model).

6. Docx Dungeon sanity:
   - Click "Docx Dungeon" in the dock. After the title card, hold `W` —
     the view strides forward past the D/O/C/X letter pillars.
   - Edit the FLOOR PLAN paragraph (type a letter into a `.` floor cell):
     a wall textured with that letter appears in the 3D view.

7. Telemetry: the dock stats line should report ≥8 fps, a run count under
   ~150, and "incremental — one block repainted" (not "remounted").

8. Document-ness: Ctrl+Z rewinds frames; the ribbon **Save** downloads a
   .docx whose screen paragraph is the frozen frame.

## Expected Results

- All of the above hold; no uncaught console errors.
- Deleting the screen paragraph halts the loop with a hint ("Ctrl+Z to
  restore it, then press Play") instead of crashing.

## Cleanup

None — the demo runs entirely in-tab on a blank in-memory document.

## Automation notes

The committed harness `scripts/verify_docx_arcade.js` implements exactly
these steps as assertions — boot, both games' input/physics, live editing
through the session API and real caret typing, blur-commit semantics, and
astral-character resilience. It
drives the page through `window.__arcade` (the demo's debug/controller
handle, analogous to the Observatory's `window.__moneyshot`), serves the
demo itself on an ephemeral port, and is configured by env vars —
`CHROMIUM_PATH`, and `ENGINE_URL`/`ENGINE_DIR` for a local engine mirror
(see the header comment). It is not in CI; run it after touching
`docs/demo/docx-arcade/`:

```bash
node scripts/verify_docx_arcade.js                      # CDN engine
CHROMIUM_PATH=/opt/pw-browsers/chromium \
ENGINE_DIR=/path/to/mirror ENGINE_URL=/engine/embed.bundle.js \
node scripts/verify_docx_arcade.js                      # offline mirror
```
