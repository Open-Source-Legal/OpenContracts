- **Wanted-authorities panel** — the missing-law backlog, surfaced. A new
  card (`WantedAuthoritiesCard` / `WantedAuthoritiesLive` in
  `frontend/src/components/corpuses/CorpusHome/intelligence/`) renders
  beneath the governance graph inside `GovernanceGraphLive`, so every surface
  that shows the graph — the Corpus Intelligence overview and the
  `[component:governance-graph]` CAML article embed — also shows
  the `wantedAuthorities` GraphQL backlog: which bodies of law the collection
  cites that aren't in the library yet, ranked by citation demand, with the
  most-cited sections as dashed "ghost" chips (`DGCL § 262 ×11`) echoing the
  graph's cited-not-yet-ingested vocabulary. Renders nothing at all when the
  backlog is empty — an empty backlog is not news. Query + types in
  `frontend/src/graphql/queries.ts` (`GET_WANTED_AUTHORITIES`); row cap in
  `frontend/src/assets/configurations/constants.ts`
  (`WANTED_AUTHORITIES_MAX_ROWS`); component tests in
  `frontend/tests/WantedAuthorities.ct.tsx`.
