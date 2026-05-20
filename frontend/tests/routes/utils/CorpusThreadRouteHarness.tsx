import { useMemo } from "react";
import { CorpusThreadRoute } from "../../../src/components/routes/CorpusThreadRoute";
import {
  openedCorpus,
  openedThread,
  routeLoading,
  routeError,
} from "../../../src/graphql/cache";

interface CorpusThreadRouteHarnessProps {
  corpusTitle: string;
}

/**
 * Browser-side harness for CorpusThreadRoute, a dumb-consumer route that only
 * reads reactive vars. The vars must be seeded in the browser realm — a
 * Playwright CT `beforeEach` runs in Node and cannot reach them. useMemo with
 * empty deps seeds them once, before CorpusThreadRoute first reads them.
 */
export function CorpusThreadRouteHarness({
  corpusTitle,
}: CorpusThreadRouteHarnessProps) {
  useMemo(() => {
    routeLoading(false);
    routeError(null);
    openedThread({ id: "thread-1" } as any);
    openedCorpus({
      id: "corpus-1",
      title: corpusTitle,
      slug: "compliance-review",
      creator: { id: "user-1", username: "testuser", slug: "testuser" },
    } as any);
  }, []);

  return <CorpusThreadRoute />;
}
