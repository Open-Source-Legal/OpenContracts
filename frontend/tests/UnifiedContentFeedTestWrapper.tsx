import React, { useEffect } from "react";
import { Provider as JotaiProvider, useAtom, useSetAtom } from "jotai";
import {
  MockedProvider,
  MockedResponse,
  MockLink,
} from "@apollo/client/testing";
import { InMemoryCache, ApolloLink } from "@apollo/client";
import { relayStylePagination } from "@apollo/client/utilities";
import { MemoryRouter } from "react-router-dom";
import { UnifiedContentFeed } from "../src/components/knowledge_base/document/unified_feed";
import {
  authStatusVar,
  authToken,
  userObj,
  openedDocument,
  openedCorpus,
  selectedAnalysesIds,
  selectedExtractIds,
  selectedAnnotationIds,
} from "../src/graphql/cache";
import {
  ContentFilters,
  ContentItemType,
  SortOption,
  Note,
} from "../src/components/knowledge_base/document/unified_feed/types";
import {
  searchTextAtom,
  textSearchStateAtom,
  selectedDocumentAtom,
} from "../src/components/annotator/context/DocumentAtom";
import {
  pdfAnnotationsAtom,
  structuralAnnotationsAtom,
} from "../src/components/annotator/context/AnnotationAtoms";
import { corpusStateAtom } from "../src/components/annotator/context/CorpusAtom";
import {
  selectedAnnotationsAtom,
  selectedRelationsAtom,
  showStructuralAnnotationsAtom,
  showStructuralRelationshipsAtom,
  showAnnotationBoundingBoxesAtom,
  showAnnotationLabelsAtom,
  showSelectedAnnotationOnlyAtom,
  hideLabelsAtom,
} from "../src/components/annotator/context/UISettingsAtom";
import {
  TextSearchSpanResult,
  TextSearchTokenResult,
} from "../src/components/types";
import { PdfAnnotations } from "../src/components/annotator/types/annotations";
import { spanLabelsToViewAtom } from "../src/components/annotator/context/AnnotationControlAtoms";
import { LabelDisplayBehavior } from "../src/types/graphql-api";

// Create a minimal test cache configuration
const createTestCache = () =>
  new InMemoryCache({
    typePolicies: {
      Query: {
        fields: {
          annotations: relayStylePagination(),
          userFeedback: relayStylePagination(),
          pageAnnotations: { keyArgs: false, merge: true },
          documents: relayStylePagination(),
          corpuses: relayStylePagination(),
          userexports: relayStylePagination(),
          labelsets: relayStylePagination(),
          annotationLabels: relayStylePagination(),
          relationshipLabels: relayStylePagination(),
          extracts: relayStylePagination(),
          columns: relayStylePagination(),
        },
      },
      DocumentType: {
        keyFields: ["id"],
      },
      CorpusType: {
        keyFields: ["id"],
      },
      AnnotationType: {
        keyFields: ["id"],
      },
      AnalysisType: {
        keyFields: ["id"],
      },
    },
  });

// Create a wildcard link that handles all GraphQL operations gracefully
const createWildcardLink = (mocks: ReadonlyArray<MockedResponse>) => {
  const defaultMockLink = new MockLink(mocks);
  return new ApolloLink((operation, forward) => {
    // Try the mock link first
    const result = defaultMockLink.request(operation, forward);
    if (result) {
      return result;
    }

    // If no mock found, return empty data to prevent errors
    return ApolloLink.empty();
  });
};

// Error boundary to catch rendering errors
class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean; error: Error | null }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error) {
    console.error("ErrorBoundary caught error:", error);
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error("ErrorBoundary error details:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: 20, background: "red", color: "white" }}>
          <h1>Component Error</h1>
          <pre>{this.state.error?.message}</pre>
          <pre>{this.state.error?.stack}</pre>
        </div>
      );
    }

    return this.props.children;
  }
}

interface UnifiedContentFeedTestWrapperProps {
  notes?: Note[];
  filters?:
    | ContentFilters
    | {
        contentTypes: string[] | Set<ContentItemType>;
        annotationFilters?: {
          labels?: Set<string>;
          showStructural?: boolean;
        };
        relationshipFilters?: {
          showStructural?: boolean;
        };
        searchQuery?: string;
      };
  sortBy?: SortOption;
  isLoading?: boolean;
  onItemSelect?: () => void;
  fetchMore?: () => Promise<void>;
  readOnly?: boolean;
  // Mock data configuration
  mockAnnotations?: any[];
  mockRelations?: any[];
  selectedAnnotationIds?: string[];
  mocks?: MockedResponse[];
  /** Override the default container style (400×600px) */
  containerStyle?: React.CSSProperties;
  /**
   * When true, leaves the corpusStateAtom empty so that tests can exercise
   * the "no corpus" branches of the feed (hides the selection toolbar,
   * disables multi-select checkboxes, etc.).
   */
  noCorpus?: boolean;
  /**
   * When true, seeds a `showStructural=true` entry in
   * `showStructuralAnnotationsAtom` so tests can verify structural items
   * appear (they are normally filtered out).
   */
  showStructural?: boolean;
  /**
   * Optional initial search query applied via the searchTextAtom so the
   * "search" content type can be driven from tests.
   */
  searchText?: string;
  /**
   * Optional initial text search matches applied via textSearchStateAtom.
   */
  textSearchMatches?: any[];
}

// Default filters
const defaultFilters: ContentFilters = {
  contentTypes: new Set(["note", "annotation", "relationship", "search"]),
  annotationFilters: {
    showStructural: false,
  },
  relationshipFilters: {
    showStructural: false,
  },
  searchQuery: "",
};

// Mock note factory
const createMockNote = (id: string, title: string, content: string): Note => ({
  id,
  title,
  content,
  created: new Date().toISOString(),
  creator: {
    email: "test@example.com",
  },
});

// Inner component to set up Jotai atoms
const InnerWrapper: React.FC<
  UnifiedContentFeedTestWrapperProps & { children: React.ReactNode }
> = ({
  mockAnnotations = [],
  mockRelations = [],
  selectedAnnotationIds: propSelectedAnnotationIds = [],
  noCorpus = false,
  showStructural = false,
  searchText = "",
  textSearchMatches = [],
  children,
}) => {
  const setPdfAnnotations = useSetAtom(pdfAnnotationsAtom);
  const setStructuralAnnotations = useSetAtom(structuralAnnotationsAtom);
  const setTextSearchState = useSetAtom(textSearchStateAtom);
  const setSearchText = useSetAtom(searchTextAtom);
  const setSelectedAnnotations = useSetAtom(selectedAnnotationsAtom);
  const setSelectedRelations = useSetAtom(selectedRelationsAtom);
  const setSpanLabelsToView = useSetAtom(spanLabelsToViewAtom);
  const setShowStructural = useSetAtom(showStructuralAnnotationsAtom);
  const setShowStructuralRelationships = useSetAtom(
    showStructuralRelationshipsAtom
  );

  // Additional atoms for annotation display
  const setShowBoundingBoxes = useSetAtom(showAnnotationBoundingBoxesAtom);
  const setShowLabels = useSetAtom(showAnnotationLabelsAtom);
  const setShowSelectedOnly = useSetAtom(showSelectedAnnotationOnlyAtom);
  const setHideLabels = useSetAtom(hideLabelsAtom);

  // Document and corpus atoms
  const setSelectedDocument = useSetAtom(selectedDocumentAtom);
  const setCorpusState = useSetAtom(corpusStateAtom);

  // Initialize atoms once on mount
  React.useEffect(() => {
    // Initialize Apollo reactive vars first
    authStatusVar("AUTHENTICATED");
    openedDocument({
      id: "test-document-id",
      slug: "test-document",
      title: "Test Document",
      creator: { id: "test-user", slug: "testuser", username: "testuser" },
    } as any);
    openedCorpus({
      id: "test-corpus-id",
      slug: "test-corpus",
      title: "Test Corpus",
      creator: { id: "test-user", slug: "testuser", username: "testuser" },
    } as any);
    selectedAnalysesIds([]);
    selectedExtractIds([]);
    selectedAnnotationIds([]);

    // Separate structural from regular annotations
    const regularAnnotations = mockAnnotations.filter((ann) => !ann.structural);
    const structuralAnns = mockAnnotations.filter((ann) => ann.structural);

    // Initialize atoms with proper structure
    setPdfAnnotations(
      new PdfAnnotations(regularAnnotations, mockRelations, [])
    );
    setStructuralAnnotations(structuralAnns);
    setTextSearchState({
      matches: textSearchMatches,
      selectedIndex: 0,
    });
    setSearchText(searchText);
    setSelectedAnnotations(propSelectedAnnotationIds);
    setSelectedRelations([]);
    // Don't filter by labels - show all annotations
    setSpanLabelsToView(null);
    setShowStructural(showStructural);
    setShowStructuralRelationships(showStructural);

    // Initialize annotation display atoms
    setShowBoundingBoxes(false);
    setShowLabels(LabelDisplayBehavior.ALWAYS);
    setShowSelectedOnly(false);
    setHideLabels(false);

    // Initialize document and corpus state atoms
    setSelectedDocument({
      id: "test-document-id",
      title: "Test Document",
      description: "Test document for unified feed",
      backendLock: false,
      pdfFile: "test.pdf",
      txtExtractFile: null,
      pawlsParseFile: null,
      isPublic: false,
      isOpen: false,
      created: new Date().toISOString(),
      modified: new Date().toISOString(),
      myPermissions: ["READ", "WRITE", "UPDATE", "DELETE"],
      isSelected: false,
      fileType: "application/pdf",
      __typename: "DocumentType",
    } as any);

    setCorpusState({
      selectedCorpus: noCorpus
        ? null
        : ({
            id: "test-corpus-id",
            title: "Test Corpus",
            description: "Test corpus",
            icon: null,
            isPublic: false,
            backendLock: false,
            created: new Date().toISOString(),
            modified: new Date().toISOString(),
            myPermissions: ["READ", "WRITE", "UPDATE", "DELETE"],
            __typename: "CorpusType",
          } as any),
      myPermissions: [],
      spanLabels: [],
      humanSpanLabels: [],
      relationLabels: [],
      docTypeLabels: [],
      humanTokenLabels: [],
      allowComments: true,
      isLoading: false,
    });
  }, []); // Run only once on mount

  return <>{children}</>;
};

// Set up authentication for tests - OUTSIDE component to avoid re-setting
authToken("test-auth-token");
userObj({
  id: "test-user",
  email: "test@example.com",
  username: "testuser",
});

export const UnifiedContentFeedTestWrapper: React.FC<
  UnifiedContentFeedTestWrapperProps
> = ({
  notes = [
    createMockNote("1", "Test Note 1", "This is the first test note"),
    createMockNote("2", "Test Note 2", "This is the second test note"),
  ],
  filters = defaultFilters,
  sortBy = "page",
  isLoading = false,
  onItemSelect = () => {},
  fetchMore,
  readOnly = false,
  mockAnnotations = [],
  mockRelations = [],
  selectedAnnotationIds = [],
  mocks = [],
  containerStyle,
  noCorpus = false,
  showStructural = false,
  searchText = "",
  textSearchMatches = [],
}) => {
  // Create a wildcard link that handles all operations
  const link = createWildcardLink(mocks);

  // Debug filters
  React.useEffect(() => {
    console.log("TestWrapper - filters received:", filters);
    console.log("TestWrapper - contentTypes:", filters.contentTypes);
    console.log(
      "TestWrapper - contentTypes type:",
      typeof filters.contentTypes
    );
    console.log("TestWrapper - is Set?", filters.contentTypes instanceof Set);
    console.log("TestWrapper - is Array?", Array.isArray(filters.contentTypes));
  }, [filters]);

  return (
    <MemoryRouter initialEntries={["/test"]}>
      <JotaiProvider>
        <MockedProvider
          link={link}
          cache={createTestCache()}
          addTypename
          defaultOptions={{
            watchQuery: { errorPolicy: "all" },
            query: { errorPolicy: "all" },
            mutate: { errorPolicy: "all" },
          }}
        >
          <ErrorBoundary>
            <InnerWrapper
              mockAnnotations={mockAnnotations}
              mockRelations={mockRelations}
              selectedAnnotationIds={selectedAnnotationIds}
              noCorpus={noCorpus}
              showStructural={showStructural}
              searchText={searchText}
              textSearchMatches={textSearchMatches}
            >
              <div
                style={{
                  width: "400px",
                  height: "600px",
                  position: "relative",
                  background: "#f5f5f5",
                  ...containerStyle,
                }}
              >
                <UnifiedContentFeed
                  notes={notes}
                  filters={{
                    ...filters,
                    // Handle Playwright's serialization of Set to Array
                    contentTypes:
                      filters.contentTypes instanceof Set
                        ? filters.contentTypes
                        : new Set<ContentItemType>(
                            Array.isArray(filters.contentTypes)
                              ? (filters.contentTypes as ContentItemType[])
                              : []
                          ),
                  }}
                  sortBy={sortBy}
                  isLoading={isLoading}
                  onItemSelect={onItemSelect}
                  fetchMore={fetchMore}
                  readOnly={readOnly}
                />
              </div>
            </InnerWrapper>
          </ErrorBoundary>
        </MockedProvider>
      </JotaiProvider>
    </MemoryRouter>
  );
};
