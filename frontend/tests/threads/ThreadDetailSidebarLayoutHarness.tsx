import React, { useEffect } from "react";
import { DocumentDiscussionsContent } from "../../src/components/discussions/DocumentDiscussionsContent";
import { authToken, selectedThreadId } from "../../src/graphql/cache";

/**
 * Boots the discussions sidebar straight into the thread-detail view
 * by priming the reactive vars that CentralRouteManager would normally
 * set from URL params. Lives in its own file so the .ct.tsx test can
 * import it via a pure-JSX-component import statement (Playwright CT
 * babel rewrite requirement — see CLAUDE.md pitfall #16).
 */
export function SidebarLayoutHarness() {
  useEffect(() => {
    authToken("test-auth-token");
    selectedThreadId("thread-1");
    return () => {
      authToken("");
      selectedThreadId(null);
    };
  }, []);

  return (
    <div
      style={{
        width: 360,
        height: 760,
        overflow: "hidden",
        border: "1px solid #e5e7eb",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <DocumentDiscussionsContent documentId="doc-1" corpusId="corpus-1" />
    </div>
  );
}
