import { useAtomValue } from "jotai";
import { allAnnotationsAtom } from "../context/AnnotationAtoms";
import {
  ServerTokenAnnotation,
  ServerSpanAnnotation,
} from "../types/annotations";

/** Returns the global, duplicate-free annotation array. */
export function useAllAnnotations(): (
  ServerTokenAnnotation | ServerSpanAnnotation
)[] {
  return useAtomValue(allAnnotationsAtom);
}
