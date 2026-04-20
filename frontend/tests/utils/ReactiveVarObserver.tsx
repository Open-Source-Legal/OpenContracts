import React from "react";
import { useReactiveVar } from "@apollo/client";
import { viewingDocument, editingDocument } from "../../src/graphql/cache";

/**
 * Apollo reactive vars are module-level singletons, so the test runner (Node)
 * and the component under test (browser) see separate instances. Mounting
 * this observer inside the tree exposes the browser-side values via data
 * attributes, which the test can query without crossing the process boundary.
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
