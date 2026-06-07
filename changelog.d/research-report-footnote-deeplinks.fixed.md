- **Deep-research report body: `## Sources` footnotes now deep-link to the cited annotation.**
  In the research report detail view the rendered report body's footnote
  definitions (e.g. *"page 41 annotation 395149 — …"*) were plain text, so a
  reader could not click through to the source — only the separate Citations
  tab carried links. The footnote definitions in the body are now click-to-source
  targets that navigate to the cited document with the cited annotation selected
  (`?ann=<global id>`), mirroring the Citations tab.
  - `frontend/src/views/ResearchReportDetail.tsx`: extracted the per-citation
    deep-link logic into a shared `buildCitationHref` helper (used by both the
    Citations tab rows and the new footnote links so they stay in lock-step),
    built a `footnote → href` map keyed by the backend's `[^n]` number, and
    passed a custom `li` renderer to the body markdown that upgrades footnote
    definitions (`<li id="user-content-fn-n">`) into client-side-routed links.
    The annotation's canonical global ID is taken from the server's
    `fullSourceAnnotationList` (typename `ServerAnnotationType`), never
    reconstructed from the raw PK.
  - `frontend/src/components/knowledge_base/markdown/SafeMarkdown.tsx`: now
    accepts an optional `components` override (forwarded to ReactMarkdown) so a
    caller can customise specific nodes without weakening the shared
    `urlTransform` safety gate.
