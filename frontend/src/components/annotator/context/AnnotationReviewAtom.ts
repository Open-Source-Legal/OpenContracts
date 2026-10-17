import { atom } from "jotai";
import { AnnotationLabelType } from "../../../types/graphql-api";

/** A manual placement belongs to exactly one document/corpus, never the next route. */
export const pendingAnnotationReviewAtom = atom<{
  annotationId: string;
  documentId: string;
  corpusId: string;
  label: AnnotationLabelType;
} | null>(null);
