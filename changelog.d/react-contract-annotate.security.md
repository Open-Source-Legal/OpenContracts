- **A converted DOCX can no longer style the OpenContracts page.** The old
  renderer inserted the document's stylesheet page-globally, and docxodus
  12.4.1 emits font names unescaped, so a crafted DOCX could inject CSS into
  the app. The library scopes the stylesheet to its viewer, reduces document
  CSS and HTML to allow-lists (no URLs fetched, no `position: fixed`, no
  shared names), and contains the viewer's layout and paint. Links inside a
  DOCX no longer navigate the host tab; they go through the same link policy
  as PDF links.
