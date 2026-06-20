- Migration `0093_load_authority_namespaces_baseline` now upserts
  `AuthorityNamespace` rows via `apps.get_model` (the historical model) instead
  of calling the live `AuthorityMappingLoader` service, so a fresh-database
  `migrate` runs against the schema as of that migration — a later
  `AuthorityNamespace` schema change can no longer break fresh-DB migrate / CI /
  onboarding (matches the fix already applied to 0092).
- `GovernanceGraphExplorer` now calls `d3.interrupt(svgEl)` in its zoom effect
  cleanup, cancelling any in-flight zoom/reset transition on unmount so a tween
  can no longer fire `setTransform` on an unmounted component (React warning +
  leak when navigating away mid-transition).
