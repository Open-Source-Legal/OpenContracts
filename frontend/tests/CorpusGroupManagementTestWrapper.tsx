import React, { useEffect } from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { InMemoryCache } from "@apollo/client";
import { Provider as JotaiProvider } from "jotai";
import { MemoryRouter } from "react-router-dom";
import { ToastContainer } from "react-toastify";
// Split-import rule (CLAUDE.md pitfall #16): JSX-component imports must live in
// their own statement, separate from the helper/var imports below, or
// Playwright CT's babel transform leaves the component reference unrewritten
// and ``mount()`` throws.
import { CorpusGroupManagement } from "../src/components/corpus_groups/CorpusGroupManagement";
import { backendUserObj } from "../src/graphql/cache";
import { UserType } from "../src/types/graphql-api";
import { GET_CORPUSES, GET_AGENT_CONFIGURATIONS } from "../src/graphql/queries";

interface Props {
  mocks: ReadonlyArray<MockedResponse>;
}

/**
 * The two pickers inside the create/edit modal each fire their own search
 * query the moment the modal mounts (``Modal`` renders ``null`` while closed,
 * so nothing is fetched until then). Neither picker's data is under test here
 * — the panel only reads back the ids the pickers were seeded with — so both
 * get a permanently-reusable empty-result mock appended AFTER the
 * test-supplied mocks. A test that wants specific picker data can declare its
 * own mock and it will be matched first.
 *
 * ``variableMatcher`` rather than an exact ``variables`` object: the debounced
 * search rewrites ``textSearch``/``name_Contains`` between renders, and
 * ``GET_CORPUSES`` carries ``@client`` fields that are stripped from the
 * operation before it reaches the link.
 */
const pickerMocks: MockedResponse[] = [
  {
    request: { query: GET_CORPUSES },
    variableMatcher: () => true,
    maxUsageCount: Number.POSITIVE_INFINITY,
    result: {
      data: {
        corpuses: {
          pageInfo: {
            hasNextPage: false,
            hasPreviousPage: false,
            startCursor: null,
            endCursor: null,
          },
          edges: [],
        },
      },
    },
  },
  {
    request: { query: GET_AGENT_CONFIGURATIONS },
    variableMatcher: () => true,
    maxUsageCount: Number.POSITIVE_INFINITY,
    result: { data: { agentConfigurations: { edges: [] } } },
  },
];

/**
 * Wrapper for the CorpusGroupManagement CT tests.
 *
 * The panel gates on the ``backendUserObj`` reactive var — an anonymous viewer
 * gets a sign-in prompt and the list query is skipped entirely. It is seeded
 * here with a signed-in NON-superuser: corpus groups are deliberately per-user
 * with no superuser gate, so the ordinary-user path is the one under test.
 */
export const CorpusGroupManagementTestWrapper: React.FC<Props> = ({
  mocks,
}) => {
  // Reactive vars live in the browser realm, so they can only be written from
  // inside the mounted component tree — never from the Node-side test body.
  useEffect(() => {
    const seedUser: UserType = {
      id: "user-1",
      username: "member",
      email: "member@test.com",
      isSuperuser: false,
    };
    backendUserObj(seedUser);
  }, []);

  // Defined inside the wrapper so Playwright CT's per-test serialization never
  // has to reach an Apollo cache instance — see CLAUDE.md pitfall #8.
  const cache = new InMemoryCache({ addTypename: false });

  return (
    <JotaiProvider>
      <MockedProvider
        mocks={[...mocks, ...pickerMocks]}
        addTypename={false}
        cache={cache}
      >
        <MemoryRouter>
          <div style={{ width: "100vw" }}>
            <CorpusGroupManagement />
            <ToastContainer />
          </div>
        </MemoryRouter>
      </MockedProvider>
    </JotaiProvider>
  );
};
