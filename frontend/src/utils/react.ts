import React from "react";

/**
 * Returns ``true`` when ``node`` would render something user-visible.
 *
 * Useful for components that conditionally render wrappers around their
 * children: ``null``, ``undefined``, booleans, empty fragments and arrays
 * of those are all treated as "renders nothing".
 *
 * Boundary cases: strings (including the empty string ``""``) and numbers
 * (including ``0``) all return ``true`` — they're text React would render.
 * Callers that consider the empty string "nothing" must guard separately.
 */
export const hasRenderableNode = (node: React.ReactNode): boolean => {
  if (node === null || node === undefined || typeof node === "boolean") {
    return false;
  }

  if (Array.isArray(node)) {
    return node.some(hasRenderableNode);
  }

  if (React.isValidElement(node) && node.type === React.Fragment) {
    return hasRenderableNode(
      (node as React.ReactElement<{ children?: React.ReactNode }>).props
        .children
    );
  }

  return true;
};
