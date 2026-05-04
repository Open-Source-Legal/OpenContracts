import React from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { InMemoryCache } from "@apollo/client";
import { Provider } from "jotai";
import { MemoryRouter } from "react-router-dom";
import { CorpusListView } from "../src/components/corpuses/CorpusListView";
import { authToken, userObj } from "../src/graphql/cache";
import { CorpusType, PageInfo } from "../src/types/graphql-api";
import { START_FORK_CORPUS } from "../src/graphql/mutations";

// Create minimal cache
const createTestCache = () =>
  new InMemoryCache({
    typePolicies: {
      CorpusType: { keyFields: ["id"] },
    },
  });

// Mock for fork mutation (always succeeds)
const createMocks = (): MockedResponse[] => [
  {
    request: {
      query: START_FORK_CORPUS,
    },
    variableMatcher: () => true,
    result: {
      data: {
        startForkCorpus: {
          ok: true,
          __typename: "StartForkCorpusMutation",
        },
      },
    },
  },
];

interface WrapperProps {
  corpuses: CorpusType[];
  searchValue: string;
  userEmail?: string;
  isAuthenticated?: boolean;
  loading?: boolean;
  pageInfo?: PageInfo;
  onSearchChange?: (value: string) => void;
  onCreateCorpus?: () => void;
  onImportCorpus?: () => void;
  allowImport?: boolean;
}

/**
 * Compute the four tab counts from a static list. Mirrors the server-side
 * filter semantics so test counts match what the real backend would return.
 */
const computeFilterCounts = (
  corpuses: CorpusType[],
  currentUserEmail?: string
) => {
  const all = corpuses.length;
  let mine = 0;
  let shared = 0;
  let publicCount = 0;
  for (const c of corpuses) {
    const isOwner = c.creator?.email === currentUserEmail;
    if (isOwner) mine++;
    else if (!c.isPublic) shared++;
    if (c.isPublic) publicCount++;
  }
  return { all, mine, shared, public: publicCount };
};

/**
 * Apply tab filtering client-side in the test harness. The real
 * `CorpusListView` no longer filters internally because the server does that
 * — but tests pass a static list, so the wrapper has to replicate the
 * server's tab semantics for the active filter.
 */
const applyTabFilter = (
  corpuses: CorpusType[],
  activeFilter: string,
  currentUserEmail?: string
): CorpusType[] => {
  switch (activeFilter) {
    case "my":
      return corpuses.filter((c) => c.creator?.email === currentUserEmail);
    case "shared":
      return corpuses.filter(
        (c) => c.creator?.email !== currentUserEmail && !c.isPublic
      );
    case "public":
      return corpuses.filter((c) => c.isPublic);
    default:
      return corpuses;
  }
};

export const CorpusListViewTestWrapper: React.FC<WrapperProps> = ({
  corpuses,
  searchValue,
  userEmail = "test@example.com",
  isAuthenticated = true,
  loading = false,
  pageInfo,
  onSearchChange = () => {},
  onCreateCorpus = () => {},
  onImportCorpus,
  allowImport = false,
}) => {
  // Set up auth state for tests
  React.useEffect(() => {
    if (isAuthenticated && userEmail) {
      authToken("test-token");
      userObj({ email: userEmail } as any);
    } else {
      authToken("");
      userObj(null);
    }
  }, [isAuthenticated, userEmail]);

  const [activeFilter, setActiveFilter] = React.useState("all");

  const filterCounts = React.useMemo(
    () => computeFilterCounts(corpuses, userEmail),
    [corpuses, userEmail]
  );

  const visibleCorpuses = React.useMemo(
    () => applyTabFilter(corpuses, activeFilter, userEmail),
    [corpuses, activeFilter, userEmail]
  );

  const defaultPageInfo: PageInfo = {
    hasNextPage: false,
    hasPreviousPage: false,
    startCursor: null,
    endCursor: null,
    __typename: "PageInfo",
  };

  return (
    <Provider>
      <MemoryRouter initialEntries={["/corpuses"]}>
        <MockedProvider mocks={createMocks()} cache={createTestCache()}>
          <CorpusListView
            corpuses={visibleCorpuses}
            pageInfo={pageInfo ?? defaultPageInfo}
            loading={loading}
            fetchMore={() => {}}
            onCreateCorpus={onCreateCorpus}
            onImportCorpus={onImportCorpus}
            searchValue={searchValue}
            onSearchChange={onSearchChange}
            allowImport={allowImport}
            activeFilter={activeFilter}
            onFilterChange={setActiveFilter}
            filterCounts={filterCounts}
          />
        </MockedProvider>
      </MemoryRouter>
    </Provider>
  );
};
