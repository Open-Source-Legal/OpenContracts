import React from "react";
import { Provider as JotaiProvider, useAtom, useSetAtom } from "jotai";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { UnifiedContentFeed } from "../src/components/knowledge_base/document/unified_feed";
import {
  ContentFilters,
  ContentItemType,
  SortOption,
  Note,
} from "../src/components/knowledge_base/document/unified_feed/types";
import {
  searchTextAtom,
  textSearchStateAtom,
} from "../src/components/annotator/context/DocumentAtom";
import {
  pdfAnnotationsAtom,
  structuralAnnotationsAtom,
} from "../src/components/annotator/context/AnnotationAtoms";
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
  mocks?: MockedResponse[];
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
> = ({ mockAnnotations = [], mockRelations = [], children }) => {
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

  // Initialize atoms synchronously on first render
  const initialized = React.useRef(false);
  if (!initialized.current) {
    // Initialize atoms with proper structure
    setPdfAnnotations(new PdfAnnotations(mockAnnotations, mockRelations, []));
    setStructuralAnnotations([]);
    setTextSearchState({
      matches: [],
      selectedIndex: 0,
    });
    setSearchText("");
    setSelectedAnnotations([]);
    setSelectedRelations([]);
    // Don't filter by labels - show all annotations
    setSpanLabelsToView(null);
    setShowStructural(false);
    setShowStructuralRelationships(false);

    // Initialize annotation display atoms
    setShowBoundingBoxes(false);
    setShowLabels(LabelDisplayBehavior.ALWAYS);
    setShowSelectedOnly(false);
    setHideLabels(false);

    initialized.current = true;
  }

  return <>{children}</>;
};

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
  mocks = [],
}) => {
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
    <JotaiProvider>
      <MockedProvider mocks={mocks} addTypename>
        <ErrorBoundary>
          <InnerWrapper
            mockAnnotations={mockAnnotations}
            mockRelations={mockRelations}
          >
            <div
              style={{
                width: "400px",
                height: "600px",
                position: "relative",
                background: "#f5f5f5",
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
  );
};
