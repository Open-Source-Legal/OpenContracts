- **Authority Console — Phase 2 (relationships editing + DRY consolidation).** The
  standalone `/admin/authority-mappings` panel (`AuthorityMappings.tsx`) is now
  **absorbed** into the console's **Aliases & Relationships** tab and **deleted**
  (along with its CT + test wrapper and its route/export), leaving no duplicate
  component. The act-section ↔ USC/CFR key-equivalence editor (inline create +
  manual-only edit/delete, source chips, search) is extracted into shared
  primitives (`authority/shared/KeyEquivalenceEditor.tsx`) reused by **both** the
  Mappings tab and the single-authority detail's **Relationships** section — so a
  body of law's relationships can now be created/edited/deleted in-context on its
  detail page (prefix-prefilled), driving the same superuser-gated
  `create/update/delete AuthorityKeyEquivalence` mutations. The registry's create
  form is also refactored onto the shared `CreateForm`/`CreateField` chrome. No
  backend changes (the equivalence CRUD already existed). Playwright CT cover the
  registry, detail-with-relationships, access gate, and mappings render + create.
