- **Removed dead GraphQL selections from the pipeline settings admin queries
  (issue #2122).** `graphql.ts`'s `GET_PIPELINE_SETTINGS`/
  `UPDATE_PIPELINE_SETTINGS`/`RESET_PIPELINE_SETTINGS` response selections
  requested the top-level `parserKwargs` and `componentsWithSecrets` fields,
  but neither was ever read anywhere in the admin component code — per-
  component secret status is surfaced via each component's own
  `settingsSchema.hasValue` instead. Removed both from all three documents'
  output selections (the `UpdateComponentSecretsMutation`/
  `DeleteComponentSecretsMutation` responses' own, actively-used
  `componentsWithSecrets` field is untouched, as is the unrelated
  `componentSettings` field, and the `parserKwargs` mutation *argument* is
  preserved for future use).
- **Corrected the Reset-to-Defaults confirmation dialog wording.**
  `SystemSettings.tsx`'s reset modal said resetting "all pipeline settings"
  with no further detail; this was inaccurate on two counts: it never
  mentioned that stored secrets (component API keys and the new agent tool
  secrets from #2117) are completely untouched by Reset, and
  `preferred_enrichers` (#2118 above) is now included in Reset rather than
  being an undocumented exception. Reworded to state plainly which settings
  reset and that secrets must be cleared separately.
