- Fixed: the admin settings panel
  (`frontend/src/components/admin/GlobalSettingsPanel.tsx`, `/admin/settings`)
  had a navigation card for Authority Sources (`/admin/authorities`) but none for
  the Enrichment Runner, so `/admin/enrichment` — whose route is registered in
  `App.tsx` and whose page links "Back to Admin Settings" — was unreachable from
  the GUI (only by typing the URL). Added an "Enrichment Runner" card linking to
  `/admin/enrichment`, placed alongside Authority Sources. Regression test in
  `frontend/tests/admin-components.ct.tsx`.
