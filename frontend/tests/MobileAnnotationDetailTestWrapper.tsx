/**
 * Test wrapper for {@link MobileAnnotationDetail}.
 *
 * The component resolves the URL-synchronised annotation selection
 * (`selectedAnnotationIds` reactive var) against the global annotation atoms.
 * For the deep-link regression covered by these tests the selection points at
 * an id that is NOT present in the (empty) annotation atoms — exactly the
 * cold-cache state a mobile `?ann=<id>` deep-link starts in. With no matching
 * annotation the component renders either the loader (while `loading` is true)
 * or the not-found message (once loading settles).
 *
 * Provides:
 * - MockedProvider + InMemoryCache (CLAUDE.md-mandated boilerplate)
 * - Jotai Provider (annotation atoms default to empty)
 * - React Router context (the selection hook uses useNavigate/useLocation)
 * - Imperative seeding of the `selectedAnnotationIds` reactive var
 */
import React, { useLayoutEffect } from "react";
import { MockedProvider } from "@apollo/client/testing";
import { InMemoryCache } from "@apollo/client";
import { Provider as JotaiProvider } from "jotai";
import { MemoryRouter } from "react-router-dom";
import { MobileAnnotationDetail } from "../src/components/knowledge_base/document/layouts/mobile/MobileAnnotationDetail";
import { selectedAnnotationIds } from "../src/graphql/cache";

export const MobileAnnotationDetailTestWrapper: React.FC<{
  readOnly?: boolean;
  loading?: boolean;
  /** Annotation id placed in the selection (intentionally unresolved). */
  selectedId?: string;
}> = ({ readOnly = true, loading = false, selectedId = "unresolved-id" }) => {
  // Seed the URL-synchronised selection in a layout effect (not at render
  // scope) so it runs once per mount and is symmetric with cleanup. A
  // render-scope write fires on every re-render and double-invokes under
  // React StrictMode.
  useLayoutEffect(() => {
    selectedAnnotationIds([selectedId]);
    return () => {
      selectedAnnotationIds([]);
    };
  }, [selectedId]);

  // Keep the InMemoryCache instance inside the wrapper (per CLAUDE.md) to
  // avoid cross-test cache serialization crashes. The component only reads
  // atoms today, but MockedProvider is required boilerplate so the tests stay
  // robust if any annotation hook later adds an Apollo call.
  return (
    <MockedProvider mocks={[]} cache={new InMemoryCache()}>
      <JotaiProvider>
        <MemoryRouter>
          <div style={{ padding: 16, maxWidth: 400, background: "#fff" }}>
            <MobileAnnotationDetail readOnly={readOnly} loading={loading} />
          </div>
        </MemoryRouter>
      </JotaiProvider>
    </MockedProvider>
  );
};
