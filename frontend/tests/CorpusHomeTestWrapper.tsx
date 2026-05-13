import React, { useEffect } from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { InMemoryCache } from "@apollo/client";
import { Provider } from "jotai";
import { MemoryRouter, useSearchParams } from "react-router-dom";
import { CorpusHome } from "../src/components/corpuses/CorpusHome";
import { CorpusType } from "../src/types/graphql-api";
import { relayStylePagination } from "@apollo/client/utilities";
import {
  corpusDetailView,
  CorpusDetailViewType,
  corpusHomeView,
  CorpusHomeViewType,
  tocExpandAll,
} from "../src/graphql/cache";

// Minimal cache matching production cache configuration
const createTestCache = () =>
  new InMemoryCache({
    typePolicies: {
      Query: {
        fields: {
          corpuses: relayStylePagination(),
          documents: relayStylePagination(["inCorpusWithId"]),
          documentRelationships: relayStylePagination([
            "corpusId",
            "documentId",
          ]),
        },
      },
      CorpusType: {
        keyFields: ["id"],
        fields: {
          // CRITICAL: Handle DocumentTypeConnection properly to prevent infinite loops
          documents: relayStylePagination(),
        },
      },
      DocumentRelationshipType: {
        keyFields: ["id"],
      },
      DocumentType: {
        keyFields: ["id"],
      },
    },
  });

interface Props {
  mocks: ReadonlyArray<MockedResponse>;
  corpus: CorpusType;
  /** Initial view for landing/details switch */
  initialView?: CorpusDetailViewType;
  /** Initial home view for About/TOC switch (within details view) */
  initialHomeView?: CorpusHomeViewType | null;
  initialTocExpanded?: boolean;
  /** Callback when the Focus/Power mode toggle is clicked */
  onModeToggle?: () => void;
  /** Whether the corpus is in power-user mode */
  isPowerUserMode?: boolean;
  /** Callback when the outer collection return control is clicked */
  onNavigateToCorpuses?: () => void;
  /** Label for the outer collection return control */
  navigateBackLabel?: string;
}

/**
 * Helper component that simulates CentralRouteManager Phase 2 behavior
 * by setting the reactive vars from URL params
 */
const RouteParamInitializer: React.FC<{
  children: React.ReactNode;
  initialView?: CorpusDetailViewType;
  initialHomeView?: CorpusHomeViewType | null;
  initialTocExpanded?: boolean;
}> = ({ children, initialView, initialHomeView, initialTocExpanded }) => {
  const [searchParams] = useSearchParams();

  useEffect(() => {
    // Simulate CentralRouteManager Phase 2: parse view from URL
    // URL param takes precedence to support navigation
    // When URL has no view param, that means "landing" (the default)
    // initialView is only used for initial mount, not subsequent changes
    const viewParam = searchParams.get("view");
    let newView: CorpusDetailViewType;
    if (viewParam === "details") {
      newView = "details";
    } else if (viewParam === "discussions") {
      newView = "discussions";
    } else {
      // "landing" param, no param, or any other value = landing
      newView = "landing";
    }
    corpusDetailView(newView);

    // Parse homeView from URL (for details view About/TOC tabs)
    const homeViewParam = searchParams.get("homeView");
    const newHomeView: CorpusHomeViewType | null =
      homeViewParam === "toc" || homeViewParam === "about"
        ? homeViewParam
        : initialHomeView ?? null;
    corpusHomeView(newHomeView);

    // Parse tocExpanded from URL
    const tocExpandedParam = searchParams.get("tocExpanded") === "true";
    tocExpandAll(tocExpandedParam || initialTocExpanded || false);

    // Cleanup on unmount
    return () => {
      corpusDetailView("landing");
      corpusHomeView(null);
      tocExpandAll(false);
    };
  }, [searchParams, initialView, initialHomeView, initialTocExpanded]);

  return <>{children}</>;
};

export const CorpusHomeTestWrapper: React.FC<Props> = ({
  mocks,
  corpus,
  initialView,
  initialHomeView,
  initialTocExpanded,
  onModeToggle,
  isPowerUserMode,
  onNavigateToCorpuses,
  navigateBackLabel,
}) => {
  // CRITICAL: Initialize reactive vars synchronously BEFORE render
  // This ensures the component sees the correct values on first paint
  // (useEffect in RouteParamInitializer runs AFTER render, which is too late)
  corpusDetailView(initialView ?? "landing");
  corpusHomeView(initialHomeView ?? null);
  tocExpandAll(initialTocExpanded ?? false);

  // Default stats matching the mock data in CorpusHome.ct.tsx
  const stats = {
    totalDocs: 3,
    totalAnnotations: 5,
    totalAnalyses: 0,
    totalExtracts: 0,
  };

  // Build initial route with query params if specified
  const params: string[] = [];
  if (initialView && initialView !== "landing") {
    params.push(`view=${initialView}`);
  }
  if (initialHomeView) {
    params.push(`homeView=${initialHomeView}`);
  }
  if (initialTocExpanded) {
    params.push("tocExpanded=true");
  }
  const queryString = params.length > 0 ? `?${params.join("&")}` : "";
  const initialRoute = `/c/test-user/test-corpus${queryString}`;

  return (
    <Provider>
      <MemoryRouter initialEntries={[initialRoute]}>
        <MockedProvider mocks={mocks} cache={createTestCache()} addTypename>
          <RouteParamInitializer
            initialView={initialView}
            initialHomeView={initialHomeView}
            initialTocExpanded={initialTocExpanded}
          >
            <CorpusHome
              corpus={corpus}
              onEditDescription={() => {}}
              stats={stats}
              statsLoading={false}
              chatQuery=""
              onChatQueryChange={() => {}}
              onChatSubmit={() => {}}
              onViewChatHistory={() => {}}
              onNavigateToCorpuses={onNavigateToCorpuses}
              navigateBackLabel={navigateBackLabel}
              onModeToggle={onModeToggle}
              isPowerUserMode={isPowerUserMode}
            />
          </RouteParamInitializer>
        </MockedProvider>
      </MemoryRouter>
    </Provider>
  );
};
