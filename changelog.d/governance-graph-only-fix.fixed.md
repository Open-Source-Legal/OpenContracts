- **`governanceGraph` crashed on real data** — `GovernanceGraphService` used
  `.only("id", "title", "custom_meta")` on a `Document` queryset, but the
  Document default manager bakes in `select_related("parent", ...)` and Django
  forbids deferring a traversed field ("Field Document.parent cannot be both
  deferred and traversed"). Switched to `values_list`
  (`opencontractserver/enrichment/services/governance_graph_service.py`).
  Found by live smoke testing against the 134-document S-1 corpus.
