import { atom } from "jotai";

/**
 * DOM elements of the annotations the plain-text annotator (`TxtAnnotator`)
 * has drawn, by annotation id, so code outside it can scroll one into view.
 *
 * The PDF and DOCX viewers (`@os-legal/react-contract-annotate`) keep their
 * elements to themselves; they are moved through `annotatorHandleAtom`.
 */
export type RefType = "annotation";

const annotationElementRefsAtom = atom<Record<string, HTMLElement | null>>({});

/**
 * Atom for registering refs
 */
export const registerRefAtom = atom(
  null,
  (
    get,
    set,
    params: {
      type: RefType;
      ref: React.MutableRefObject<HTMLElement | null>;
      id: string | number;
    }
  ) => {
    set(annotationElementRefsAtom, {
      ...get(annotationElementRefsAtom),
      [params.id.toString()]: params.ref.current,
    });
  }
);

/**
 * Atom for unregistering refs
 */
export const unregisterRefAtom = atom(
  null,
  (
    get,
    set,
    params: {
      type: RefType;
      id: string | number;
    }
  ) => {
    const newRefs = { ...get(annotationElementRefsAtom) };
    delete newRefs[params.id.toString()];
    set(annotationElementRefsAtom, newRefs);
  }
);

/**
 * Combined read-only atom for accessing all refs
 */
export const annotationRefsAtom = atom((get) => ({
  annotationElementRefs: get(annotationElementRefsAtom),
}));
