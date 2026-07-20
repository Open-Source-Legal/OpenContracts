import { MockedResponse } from "@apollo/client/testing";
import { GET_CORPUSES, GET_AGENT_CONFIGURATIONS } from "../src/graphql/queries";

/**
 * Search fixtures for the two pickers the corpus-group form embeds
 * (``CorpusMultiSelect`` / ``AgentConfigurationSelect``).
 *
 * Deliberately a plain ``.ts`` module with no component imports: both
 * ``CorpusGroupSelectors.ct.tsx`` (which drives the pickers directly) and
 * ``CorpusGroupManagement.ct.tsx`` (which drives them through the form modal)
 * consume these, and a fixtures file that imported JSX would drag the picker
 * components into the Node-side test bundle as well as the browser one.
 */

/* -------------------------------------------------------------------------- */
/* Ids + labels                                                                */
/* -------------------------------------------------------------------------- */

/** Relay global ids — the selectors pass these straight through to consumers. */
export const CORPUS_ID_MSA = "Q29ycHVzVHlwZTox";
export const CORPUS_ID_NDA = "Q29ycHVzVHlwZToz";
export const CORPUS_ID_LEASES = "Q29ycHVzVHlwZTo1";
/** Deliberately absent from EVERY mocked search result — see the seed tests. */
export const CORPUS_ID_ARCHIVE = "Q29ycHVzVHlwZTo5OQ==";

export const CORPUS_TITLE_MSA = "Master Service Agreements";
export const CORPUS_TITLE_NDA = "Mutual NDAs";
export const CORPUS_TITLE_LEASES = "Commercial Leases";
export const CORPUS_TITLE_ARCHIVE = "Archived Contracts";

export const AGENT_ID_ANALYST = "QWdlbnRDb25maWc6NQ==";
export const AGENT_ID_REVIEWER = "QWdlbnRDb25maWc6Ng==";
/** Deliberately absent from EVERY mocked search result — see the seed tests. */
export const AGENT_ID_LEGACY = "QWdlbnRDb25maWc6OTk=";

export const AGENT_NAME_ANALYST = "Contract Analyst";
export const AGENT_NAME_REVIEWER = "Clause Reviewer";
export const AGENT_NAME_LEGACY = "Legacy Orchestrator";

/**
 * The terms the search tests type. Each is chosen so the filtered result set is
 * a strict SUBSET of the unfiltered one — that is what makes "reopening the
 * menu shows the unfiltered list" a real assertion rather than a tautology.
 */
export const CORPUS_SEARCH_TERM = "nda";
export const AGENT_SEARCH_TERM = "reviewer";

/* -------------------------------------------------------------------------- */
/* Node builders                                                               */
/* -------------------------------------------------------------------------- */

/**
 * Full node shape for ``GET_CORPUSES``. Every field the document selects is
 * present: an incomplete node makes Apollo's write-then-read-back round trip
 * report a missing field and hand the hook an empty ``data``, which surfaces as
 * a silently empty menu rather than as an obvious mock failure.
 */
const buildCorpusNode = (id: string, title: string) => ({
  id,
  slug: title.toLowerCase().replace(/\s+/g, "-"),
  icon: "folder",
  title,
  creator: { id: "user-1", email: "member@test.com", slug: "member" },
  description: `${title} description`,
  descriptionPreview: `${title} description`,
  isPublic: false,
  isPersonal: false,
  is_selected: false,
  is_open: false,
  myPermissions: ["read_corpus"],
  documentCount: 3,
  parent: null,
  labelSet: null,
  categories: [],
  license: null,
  licenseLink: null,
  upvoteCount: 0,
  downvoteCount: 0,
  score: 0,
  myVote: null,
});

/** Full node shape for ``GET_AGENT_CONFIGURATIONS`` — see ``buildCorpusNode``. */
const buildAgentNode = (id: string, name: string) => ({
  id,
  name,
  slug: name.toLowerCase().replace(/\s+/g, "-"),
  description: `${name} description`,
  systemInstructions: "",
  availableTools: [],
  scope: "CORPUS",
  isActive: true,
  corpus: null,
});

const corpusesResult = (nodes: ReturnType<typeof buildCorpusNode>[]) => ({
  data: {
    corpuses: {
      pageInfo: {
        hasNextPage: false,
        hasPreviousPage: false,
        startCursor: null,
        endCursor: null,
      },
      edges: nodes.map((node) => ({ node })),
    },
  },
});

const agentsResult = (nodes: ReturnType<typeof buildAgentNode>[]) => ({
  data: { agentConfigurations: { edges: nodes.map((node) => ({ node })) } },
});

/* -------------------------------------------------------------------------- */
/* Mocks                                                                       */
/* -------------------------------------------------------------------------- */

/**
 * Corpus search mocks, split on ``textSearch``.
 *
 * The split IS the test instrument. The unfiltered matcher answers the mount
 * query and every post-selection reset; the ``nda`` matcher only ever answers a
 * query whose variables actually carry the debounced term. A debounce that
 * never fired therefore cannot accidentally produce the filtered menu, and a
 * reset that never happened cannot produce the unfiltered one.
 */
export const corpusSearchMocks: MockedResponse[] = [
  {
    request: { query: GET_CORPUSES },
    variableMatcher: (variables) => !variables?.textSearch,
    maxUsageCount: Number.POSITIVE_INFINITY,
    result: corpusesResult([
      buildCorpusNode(CORPUS_ID_MSA, CORPUS_TITLE_MSA),
      buildCorpusNode(CORPUS_ID_NDA, CORPUS_TITLE_NDA),
      buildCorpusNode(CORPUS_ID_LEASES, CORPUS_TITLE_LEASES),
    ]),
  },
  {
    request: { query: GET_CORPUSES },
    variableMatcher: (variables) =>
      variables?.textSearch === CORPUS_SEARCH_TERM,
    maxUsageCount: Number.POSITIVE_INFINITY,
    result: corpusesResult([buildCorpusNode(CORPUS_ID_NDA, CORPUS_TITLE_NDA)]),
  },
];

/** Agent search mocks, split on ``name_Contains`` — see ``corpusSearchMocks``. */
export const agentSearchMocks: MockedResponse[] = [
  {
    request: { query: GET_AGENT_CONFIGURATIONS },
    variableMatcher: (variables) => !variables?.name_Contains,
    maxUsageCount: Number.POSITIVE_INFINITY,
    result: agentsResult([
      buildAgentNode(AGENT_ID_ANALYST, AGENT_NAME_ANALYST),
      buildAgentNode(AGENT_ID_REVIEWER, AGENT_NAME_REVIEWER),
    ]),
  },
  {
    request: { query: GET_AGENT_CONFIGURATIONS },
    variableMatcher: (variables) =>
      variables?.name_Contains === AGENT_SEARCH_TERM,
    maxUsageCount: Number.POSITIVE_INFINITY,
    result: agentsResult([
      buildAgentNode(AGENT_ID_REVIEWER, AGENT_NAME_REVIEWER),
    ]),
  },
];
