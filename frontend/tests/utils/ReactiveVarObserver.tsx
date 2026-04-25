import React from "react";
import { useReactiveVar } from "@apollo/client";
import { viewingDocument, editingDocument } from "../../src/graphql/cache";

/**
 * Apollo reactive vars are module-level singletons, so the test runner (Node)
 * and the component under test (browser) see separate instances. Mounting
 * this observer inside the tree exposes the browser-side values via data
 * attributes, which the test can query without crossing the process boundary.
 *
 * Currently observes `viewingDocument` and `editingDocument`. To expose an
 * additional reactive var, follow the same pattern:
 *   1. Import the var from `../../src/graphql/cache`.
 *   2. Subscribe with `useReactiveVar(...)` inside the component.
 *   3. Render its value as a `data-<name>-id` attribute on the same element.
 * Tests then read it with `page.getByTestId("rv-observer").getAttribute(...)`.
 */
export const ReactiveVarObserver: React.FC = () => {
  const viewing = useReactiveVar(viewingDocument);
  const editing = useReactiveVar(editingDocument);
  return (
    <div
      data-testid="rv-observer"
      data-viewing-id={viewing?.id ?? ""}
      data-editing-id={editing?.id ?? ""}
    />
  );
};
