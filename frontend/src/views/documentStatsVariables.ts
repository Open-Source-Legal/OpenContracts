import type { RequestDocumentStatsInputs } from "../graphql/queries";

// Minimal corpus shape needed for the stats query — only the id is read, but
// ``includeCaml`` is also forced on for any corpus selection so the count
// matches the list view (which does the same). Kept as a structural type so
// callers can pass any Corpus-like object without an extra round-trip cast.
export interface DocumentStatsCorpus {
  id: string;
}

export interface BuildDocumentStatsVariablesInput {
  searchTerm?: string | null;
  labelId?: string | null;
  corpus?: DocumentStatsCorpus | null;
}

// Translates the Documents view's reactive-var filter state into the variable
// shape expected by ``GET_DOCUMENT_STATS``. Conditional spreads keep the wire
// payload minimal: each filter is omitted when falsy so MockedProvider tests
// can match ``{}`` for the unfiltered case and the backend resolver can keep
// using its argument-presence convention to skip filter clauses.
export const buildDocumentStatsVariables = ({
  searchTerm,
  labelId,
  corpus,
}: BuildDocumentStatsVariablesInput): RequestDocumentStatsInputs => ({
  ...(searchTerm && { textSearch: searchTerm }),
  ...(labelId && { hasLabelWithId: labelId }),
  ...(corpus && {
    inCorpusWithId: corpus.id,
    includeCaml: true,
  }),
});
