# Test: PDF/DOCX viewer runs on `@os-legal/react-contract-annotate`

## Purpose
Verify the library-backed PDF and DOCX viewers (`frontend/src/components/annotator/bindings/`,
`components/wrappers/{Pdf,Docx}AnnotatorWrapper.tsx`) build and resolve correctly in both the
production build and the Vite dev server, beyond what the component tests (a production build)
cover: one pdf.js instance shared by OpenContracts and the library, and the docxodus WebAssembly
runtime served at `wasmBaseUrl`.

## Prerequisites
- `frontend/node_modules` installed (`yarn install --frozen-lockfile`).
- Port 5174 free.

## Steps
1. Production build (type-check + bundle):
   ```bash
   cd frontend && yarn build
   ls dist/docxodus-wasm/_framework | head
   ```
2. Start a dev server:
   ```bash
   cd frontend && npx vite --port 5174 --strictPort
   ```
3. The docxodus runtime is served where `DocxAnnotatorWrapper` points in dev
   (`DOCXODUS_WASM_DEV_PATH`):
   ```bash
   W=$(ls node_modules/docxodus/dist/wasm/_framework | grep '\.wasm$' | head -1)
   curl -s -o /dev/null -w "%{http_code} %{content_type}\n" \
     "http://127.0.0.1:5174/node_modules/docxodus/dist/wasm/_framework/$W"
   ```
4. Both wrappers transform, and the library and OpenContracts import the same pdf.js:
   ```bash
   B=http://127.0.0.1:5174
   curl -s "$B/src/components/annotator/components/wrappers/PdfAnnotatorWrapper.tsx" | grep -o 'from "[^"]*react-contract-annotate[^"]*"'
   curl -s "$B/src/components/knowledge_base/document/document_kb/useDocumentLoader.ts" | grep -o 'from "[^"]*pdfjs[^"]*"'
   # then fetch the library's pdf pre-bundle printed above and look for its pdf.js import:
   curl -s "$B/node_modules/.vite/deps/@os-legal_react-contract-annotate_pdf.js" | grep -o '^import[^;]*pdfjs[^;]*;'
   ```
5. The library's DOCX pre-bundle keeps docxodus external (it is excluded from dep optimisation so
   it can find its own files):
   ```bash
   curl -s "$B/node_modules/.vite/deps/@os-legal_react-contract-annotate_docx.js" | grep -o '^import[^;]*docxodus[^;]*;'
   ```

## Expected Results
- Step 1 exits 0 and `dist/docxodus-wasm/` holds the runtime.
- Step 3 prints `200 application/wasm`.
- Step 4: the library's pdf pre-bundle imports `/node_modules/.vite/deps/pdfjs-dist_legacy_build_pdf__mjs.js`,
  the same module `useDocumentLoader` imports (one pdf.js instance; the worker set by
  `configurePdfWorker` applies to both).
- Step 5: docxodus is imported from `/node_modules/docxodus/dist/index.js`, not bundled.

## Cleanup
Stop the dev server (Ctrl+C). `yarn build` regenerates `public/env-config.js` (gitignored).

Last run 2026-11-26: all expected results observed. Not run: a live document load against a
backend (no local OpenContracts backend was up); the component tests cover the viewers in a
production build.
