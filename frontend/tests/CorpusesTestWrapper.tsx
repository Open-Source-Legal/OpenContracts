import React from "react";
import {
  MockedProvider,
  MockedResponse,
  MockLink,
} from "@apollo/client/testing";
import { InMemoryCache, ApolloLink, Observable } from "@apollo/client";
import { Provider } from "jotai";
import { useHydrateAtoms } from "jotai/utils";
import { MemoryRouter, useLocation } from "react-router-dom";
import { Corpuses } from "../src/views/Corpuses";
import { relayStylePagination } from "@apollo/client/utilities";
import {
  authStatusVar,
  authToken,
  userObj,
  backendUserObj,
  openedCorpus,
  selectedTab,
  selectedFolderId,
  selectedExtractIds,
  corpusDetailView,
  corpusPowerUserMode,
  deletingCorpus,
} from "../src/graphql/cache";
import { mergeArrayByIdFieldPolicy } from "../src/graphql/cache";
import {
  GET_CORPUSES,
  GET_DOCUMENTS,
  GET_ANNOTATIONS,
  GET_ANALYSES,
  GET_EXTRACTS,
  GET_CONVERSATIONS,
  GET_CORPUS_STATS,
  GET_CORPUS_WITH_HISTORY,
  GET_CORPUS_ACTIONS,
  GET_CORPUS_CONVERSATIONS,
  GET_CORPUS_ENGAGEMENT_METRICS,
  GET_BADGES,
  GET_CORPUS_ARTICLE,
} from "../src/graphql/queries";
import { GET_CORPUS_FOLDERS } from "../src/graphql/queries/folders";
import { GET_CORPUS_METADATA_COLUMNS } from "../src/graphql/metadataOperations";
import { CorpusType } from "../src/types/graphql-api";
import { corpusStateAtom } from "../src/components/annotator/context/CorpusAtom";
import { getPermissions } from "../src/utils/transform";
import { PermissionTypes } from "../src/components/types";

// Create minimal cache similar to DocumentKnowledgeBaseTestWrapper
const createTestCache = () =>
  new InMemoryCache({
    typePolicies: {
      Query: {
        fields: {
          corpuses: relayStylePagination(),
          documents: relayStylePagination([
            "inCorpusWithId",
            "inFolderId",
            "textSearch",
            "hasLabelWithId",
            "hasAnnotationsWithIds",
            "includeCaml",
            "title",
          ]),
          annotations: relayStylePagination(),
          analyses: relayStylePagination(),
          extracts: relayStylePagination(),
          conversations: relayStylePagination(),
        },
      },
      CorpusType: {
        keyFields: ["id"],
        fields: {
          documents: relayStylePagination(),
          annotations: relayStylePagination(),
        },
      },
      DocumentType: { keyFields: ["id"] },
      ServerAnnotationType: {
        keyFields: ["id"],
        fields: {
          userFeedback: mergeArrayByIdFieldPolicy,
        },
      },
      AnalysisType: { keyFields: ["id"] },
      ExtractType: { keyFields: ["id"] },
      ConversationType: { keyFields: ["id"] },
    },
  });

/**
 * Minimal URL-to-state sync for tests (mimics CentralRouteManager Phase 2)
 * Only syncs tab and folder params - tests don't render full CentralRouteManager
 */
const UrlToStateSync: React.FC = () => {
  const location = useLocation();

  React.useEffect(() => {
    const searchParams = new URLSearchParams(location.search);
    const tabParam = searchParams.get("tab");
    const folderParam = searchParams.get("folder");
    const modeParam = searchParams.get("mode");

    // Sync tab param to reactive var
    selectedTab(tabParam);

    // Sync folder param to reactive var
    selectedFolderId(folderParam);

    // Sync power user mode param to reactive var
    corpusPowerUserMode(modeParam === "power");
  }, [location.search]);

  return null;
};

/**
 * Helper to compute permissions from corpus object
 *
 * Handles both:
 * 1. Test mock format: PermissionTypes enum values (e.g., "CAN_UPDATE")
 * 2. GraphQL API format: Raw permission strings (e.g., "update_corpus")
 */
const computePermissions = (corpus: CorpusType | null): PermissionTypes[] => {
  if (!corpus) return [];

  const rawPermissions = corpus.myPermissions || [];
  const isAlreadyParsed = rawPermissions.some(
    (p) =>
      p === PermissionTypes.CAN_UPDATE ||
      p === PermissionTypes.CAN_READ ||
      p === PermissionTypes.CAN_REMOVE ||
      p === PermissionTypes.CAN_CREATE ||
      p === PermissionTypes.CAN_PERMISSION ||
      p === PermissionTypes.CAN_PUBLISH ||
      p === PermissionTypes.CAN_COMMENT
  );

  return isAlreadyParsed
    ? (rawPermissions as PermissionTypes[])
    : getPermissions(rawPermissions);
};

/**
 * Initialize corpus state atom with permissions from corpus object
 * Uses useHydrateAtoms to set state synchronously during render,
 * ensuring permission-gated UI elements render correctly on first paint.
 */
const CorpusStateInitializer: React.FC<{ corpus: CorpusType | null }> = ({
  corpus,
}) => {
  const permissions = computePermissions(corpus);

  // useHydrateAtoms sets atom state synchronously during render (before children render)
  // This ensures Corpuses component sees the correct permissions immediately
  useHydrateAtoms([
    [
      corpusStateAtom,
      {
        selectedCorpus: corpus,
        myPermissions: permissions,
        spanLabels: [],
        humanSpanLabels: [],
        relationLabels: [],
        docTypeLabels: [],
        humanTokenLabels: [],
        allowComments: corpus?.allowComments ?? true,
        isLoading: false,
      },
    ],
  ]);

  return null;
};

/**
 * Query matchers for wildcard responses
 * Maps query names to their GraphQL documents for flexible matching
 */
const WILDCARD_QUERIES = [
  { name: "GetCorpuses", query: GET_CORPUSES },
  { name: "GetDocuments", query: GET_DOCUMENTS },
  { name: "GetAnnotations", query: GET_ANNOTATIONS },
  { name: "GetAnalyses", query: GET_ANALYSES },
  { name: "GetExtracts", query: GET_EXTRACTS },
  { name: "GetConversations", query: GET_CONVERSATIONS },
  { name: "GetCorpusStats", query: GET_CORPUS_STATS },
  { name: "GetCorpusWithHistory", query: GET_CORPUS_WITH_HISTORY },
  { name: "GetCorpusConversations", query: GET_CORPUS_CONVERSATIONS },
  { name: "GetCorpusFolders", query: GET_CORPUS_FOLDERS },
  { name: "GetCorpusArticle", query: GET_CORPUS_ARTICLE },
] as const;

// Create wildcard link to respond to repeated queries with consistent results
const createWildcardLink = (mocks: ReadonlyArray<MockedResponse>) => {
  // Ordinary single-shot behaviour for most mocks
  const mockLink = new MockLink(mocks);

  // Build a map of canonical results for frequently-queried operations
  const canonicalResults = new Map<string, any>();
  for (const { name, query } of WILDCARD_QUERIES) {
    const mockResult = mocks.find((m) => m.request.query === query)?.result;
    if (mockResult) {
      canonicalResults.set(name, mockResult);
    }
  }

  // Find the latest (most complete) document result that has documents
  const documentsResults = mocks.filter(
    (m) => m.request.query === GET_DOCUMENTS
  );
  const documentsWithData = documentsResults.find(
    (m) =>
      (m.result as any)?.data?.documents?.edges?.length > 0 ||
      (m.request.variables as any)?.inCorpusWithId
  );
  const documentsResult =
    documentsWithData?.result || documentsResults[0]?.result;
  if (documentsResult) {
    canonicalResults.set("GetDocuments", documentsResult);
  }

  // Find metadata columns result with actual columns (not empty)
  const metadataColumnsResults = mocks.filter(
    (m) => m.request.query === GET_CORPUS_METADATA_COLUMNS
  );
  const columnsWithData = metadataColumnsResults.find(
    (m) => (m.result as any)?.data?.corpusMetadataColumns?.length > 0
  );
  // Use columns with data after some requests, otherwise use first mock
  let metadataColumnsCallCount = 0;
  const getMetadataColumnsResult = () => {
    metadataColumnsCallCount++;
    // After 2 calls (initial + refetch), return columns with data
    if (metadataColumnsCallCount > 2 && columnsWithData) {
      return columnsWithData.result;
    }
    return metadataColumnsResults[0]?.result;
  };

  return new ApolloLink((operation) => {
    const opName = operation.operationName;

    // Check if this is a wildcard query that should return consistent results
    for (const { name, query } of WILDCARD_QUERIES) {
      if (opName === name || operation.query === query) {
        const result = canonicalResults.get(name);
        if (result) {
          console.log(`[MOCK] wildcard ${name}`, operation.variables);
          return Observable.of(result);
        }
      }
    }

    // Special handling for metadata columns (progressive response)
    if (operation.query === GET_CORPUS_METADATA_COLUMNS) {
      const result = getMetadataColumnsResult();
      if (result) {
        console.log(
          "[MOCK] wildcard GetCorpusMetadataColumns (call #" +
            metadataColumnsCallCount +
            ")",
          operation.variables
        );
        return Observable.of(result as any);
      }
    }

    // Delegate everything else to MockLink (single-shot semantics)
    return mockLink.request(operation) as any;
  });
};

interface WrapperProps {
  mocks: ReadonlyArray<MockedResponse>;
  initialEntries?: string[];
  initialCorpus?: CorpusType | null;
  /** Set to false to test unauthenticated state */
  authenticated?: boolean;
  /**
   * Seeds the `deletingCorpus` reactive var so the delete-confirmation
   * modal is visible on mount. Lets a test exercise `handleDeleteCorpus`
   * without driving the corpus-card context menu.
   */
  initialDeletingCorpus?: CorpusType | null;
}

export const CorpusesTestWrapper: React.FC<WrapperProps> = ({
  mocks,
  initialEntries = ["/corpuses"],
  initialCorpus = null,
  authenticated = true,
  initialDeletingCorpus = null,
}) => {
  // Set up authentication state BEFORE useEffect runs
  // This ensures auth is available when components first render
  if (authenticated) {
    authToken("test-auth-token");
    userObj({
      id: "test-user-1",
      email: "test@example.com",
      username: "testuser",
      slug: "testuser",
    } as any);
    backendUserObj({
      id: "test-user-1",
      email: "test@example.com",
      username: "testuser",
      isUsageCapped: false,
    } as any);
  }

  // CRITICAL: Initialize corpusDetailView synchronously BEFORE render
  // This ensures CorpusHome sees "landing" view on first paint
  // (prevents stale values from previous tests)
  corpusDetailView("landing");

  // Mark authentication as done immediately for tests
  // Component tests set reactive vars directly (pragmatic exception to The ONE PLACE TO RULE THEM ALL)
  React.useEffect(() => {
    authStatusVar(authenticated ? "AUTHENTICATED" : "UNAUTHENTICATED");
  }, [authenticated]);

  // Ensure the openedCorpus reactive var is initialised **in the browser runtime**
  React.useEffect(() => {
    openedCorpus(initialCorpus);
    // Clear extract selection when mounting
    selectedExtractIds([]);
  }, [initialCorpus]);

  // Seed the delete-confirmation modal when a test asks for it.
  React.useEffect(() => {
    deletingCorpus(initialDeletingCorpus);
  }, [initialDeletingCorpus]);

  // Cleanup on unmount
  React.useEffect(() => {
    return () => {
      authToken("");
      userObj(null);
      backendUserObj(null);
      openedCorpus(null);
      selectedTab(null);
      selectedFolderId(null);
      selectedExtractIds([]);
      corpusDetailView("landing");
      corpusPowerUserMode(false);
      deletingCorpus(null);
    };
  }, []);

  const link = createWildcardLink(mocks);
  return (
    <Provider>
      <MemoryRouter initialEntries={initialEntries}>
        {/* Minimal URL-to-state sync for tab/folder params (mimics CentralRouteManager Phase 2) */}
        <UrlToStateSync />
        {/* Initialize corpus state atom with permissions before rendering Corpuses */}
        <CorpusStateInitializer corpus={initialCorpus} />
        <MockedProvider link={link} cache={createTestCache()} addTypename>
          <Corpuses />
        </MockedProvider>
      </MemoryRouter>
    </Provider>
  );
};
