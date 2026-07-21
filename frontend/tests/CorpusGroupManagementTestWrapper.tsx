import React, { useEffect, useState } from "react";
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
import { authStatusVar, backendUserObj } from "../src/graphql/cache";
import { UserType } from "../src/types/graphql-api";
import { GET_CORPUSES, GET_AGENT_CONFIGURATIONS } from "../src/graphql/queries";
import {
  corpusSearchMocks,
  agentSearchMocks,
} from "./CorpusGroupPickerFixtures";

/**
 * Which of the panel's three identity states to mount in.
 *
 * The panel reads TWO reactive vars, and the interesting states are the ones
 * where they disagree, so both are always written explicitly rather than left
 * on their module defaults:
 *
 * - ``signed-in``  — user present: the list query runs.
 * - ``anonymous``  — definitely logged out: sign-in prompt, query skipped.
 * - ``resolving``  — a bearer token exists but the GET_ME round trip has not
 *   landed. ``backendUserObj`` alone still reads null here, so the panel must
 *   show a spinner instead of accusing an authenticated user of being logged
 *   out. This state is unreachable without setting ``authStatusVar``, whose
 *   module default is ``"LOADING"``.
 */
export type CorpusGroupAuthState = "signed-in" | "anonymous" | "resolving";

interface Props {
  /**
   * Test-supplied mocks. These cross the Node→browser realm boundary as mount
   * props, so they must be PLAIN DATA: Playwright serializes them, and neither
   * ``Error`` instances (``error: new Error(...)`` silently arrives as an empty
   * object, surfacing as Apollo's "Error message not found.") nor
   * ``variableMatcher`` functions survive the trip. Model transport failures as
   * ``result: { errors: [{ message }] }``, and reach for ``pickerData`` below
   * when a test needs matcher-based picker mocks.
   */
  mocks: ReadonlyArray<MockedResponse>;
  auth?: CorpusGroupAuthState;
  /**
   * Serve the shared picker fixtures instead of the empty defaults, so the
   * corpora/agent dropdowns inside the form modal have something to pick. They
   * are wired up HERE rather than passed in because they match on a
   * ``variableMatcher`` callback, which only works inside the browser realm.
   */
  pickerData?: boolean;
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
  auth = "signed-in",
  pickerData = false,
}) => {
  const [seeded, setSeeded] = useState(false);

  // Reactive vars live in the browser realm, so they can only be written from
  // inside the mounted component tree — never from the Node-side test body.
  useEffect(() => {
    const seedUser: UserType = {
      id: "user-1",
      username: "member",
      email: "member@test.com",
      isSuperuser: false,
    };
    // Both vars are written on every branch. Leaving either on its module
    // default would make the branch under test depend on load order rather
    // than on this prop.
    backendUserObj(auth === "signed-in" ? seedUser : null);
    authStatusVar(auth === "anonymous" ? "ANONYMOUS" : "AUTHENTICATED");
    setSeeded(true);
  }, [auth]);

  // Defined inside the wrapper so Playwright CT's per-test serialization never
  // has to reach an Apollo cache instance — see CLAUDE.md pitfall #8.
  const cache = new InMemoryCache({ addTypename: false });

  return (
    <JotaiProvider>
      <MockedProvider
        mocks={[
          ...mocks,
          ...(pickerData
            ? [...corpusSearchMocks, ...agentSearchMocks]
            : pickerMocks),
        ]}
        addTypename={false}
        cache={cache}
      >
        <MemoryRouter>
          <div style={{ width: "100vw" }}>
            <CorpusGroupManagement />
            <ToastContainer />
            {/* Positive signal that the identity seeding effect has run. The
                pre-effect first paint renders the SAME sign-in prompt as the
                anonymous branch, so a test asserting "anonymous, and nothing
                was fetched" needs something to wait on that cannot be
                satisfied by the un-seeded first render. */}
            {seeded && <div data-testid="auth-seeded" />}
          </div>
        </MemoryRouter>
      </MockedProvider>
    </JotaiProvider>
  );
};
