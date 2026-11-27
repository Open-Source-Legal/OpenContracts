import { useAtomValue } from "jotai";
import { annotationRefsAtom } from "../context/AnnotationRefsAtoms";

/**
 * The DOM elements of the annotations the plain-text annotator has drawn,
 * by annotation id (see `AnnotationRefsAtoms`).
 */
export const useAnnotationRefs = () => {
  const refs = useAtomValue(annotationRefsAtom);

  return {
    annotationElementRefs: { current: refs.annotationElementRefs },
  };
};
