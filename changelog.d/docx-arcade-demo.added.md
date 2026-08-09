- **The Docx Arcade** (`docs/demo/docx-arcade/`) — an embeddable, fully
  client-side demo of the Docxodus DOCX engine: two playable ASCII games
  (single-screen platformer "Courier Quest" + first-person raycaster "Docx
  Dungeon") rendered *inside a live Word document* in the stock ribbon
  editor. The screen is one Word paragraph redrawn ~12×/s via Unid-preserving
  `DocxSession.raw.replaceXml` + `DocxEditor.refresh()` (the Docx Observatory
  pattern), and the levels are editable paragraphs in the same document —
  typing into a room/floor-plan rebuilds the world live (dirty blocks are
  read from the editor DOM via `engine.js::domBlockToRows`, since the editor
  commits text on blur; blank level rows seed as NBSP so they stay
  caret-addressable). Ships as static files deployed verbatim by mkdocs
  (`demo/docx-arcade/` on the docs site), pinned to docxodus 9.7.0 via
  jsDelivr with an `?engine=` override; embeds anywhere via iframe. Docs page
  at `docs/demo/index.md` (new "Demos" nav tab), manual test script at
  `docs/test_scripts/docx_arcade_demo.md`, curated screenshots under
  `docs/assets/images/screenshots/docx_arcade_*.png`. No backend or GraphQL
  surface touched.
