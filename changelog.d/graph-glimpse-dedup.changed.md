- **Graph-glimpse scaffolding deduplicated** — `DocumentGraphGlimpse` and
  `GovernanceGraphGlimpse` shared ~120 lines of copy-pasted card chrome and
  deterministic-layout machinery; both now compose shared modules instead:
  `frontend/src/components/corpuses/CorpusHome/intelligence/graphCardChrome.ts`
  (card shell, header, SVG frame, parametrised skeleton, legend, empty state,
  explore link) and `frontend/src/utils/graphLayout.ts` (`createSeededRandom`
  Park–Miller LCG + `runSimulationTicks` synchronous d3 tick loop, unit-tested
  in `graphLayout.test.ts`). The governance ghost-key display form moved to
  `formatCanonicalLawKey` in `frontend/src/utils/formatters.ts` (unit-tested)
  so the wanted-authorities panel renders keys identically. Also fixed
  `frontend/tests/CorpusIntelligenceOverview.ct.tsx`, which had been broken
  since the overview gained `GovernanceGraphLive`: the mount lacked a Router
  context (`useNavigate` threw) and the `GET_GOVERNANCE_GRAPH` mock was
  missing.
