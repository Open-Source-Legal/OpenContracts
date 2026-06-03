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
 * - Jotai Provider (annotation atoms default to empty)
 * - React Router context (the selection hook uses useNavigate/useLocation)
 * - Imperative seeding of the `selectedAnnotationIds` reactive var
 */
import React, { useEffect } from "react";
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
  // Seed the URL-synchronised selection synchronously before first render.
  selectedAnnotationIds([selectedId]);

  useEffect(() => {
    return () => {
      selectedAnnotationIds([]);
    };
  }, []);

  return (
    <JotaiProvider>
      <MemoryRouter>
        <div style={{ padding: 16, maxWidth: 400, background: "#fff" }}>
          <MobileAnnotationDetail readOnly={readOnly} loading={loading} />
        </div>
      </MemoryRouter>
    </JotaiProvider>
  );
};
