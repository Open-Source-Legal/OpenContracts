import { atom } from "jotai";
import {
  PdfAnnotations,
  ServerTokenAnnotation,
  ServerSpanAnnotation,
  DocTypeAnnotation,
  RelationGroup,
} from "../types/annotations";

/**
 * Atom to manage PdfAnnotations state.
 */
export const pdfAnnotationsAtom = atom<PdfAnnotations>(
  new PdfAnnotations([], [], [])
);

/**
 * Atom to manage structural annotations.
 */
export const structuralAnnotationsAtom = atom<ServerTokenAnnotation[]>([]);

/**
 * Atom to manage structural relationships. Loaded by the same lazy query
 * that loads structural annotations — they describe the connections between
 * structural annotations (e.g. headers ↔ paragraphs) and are toggled by the
 * same UI control. Kept separate from ``pdfAnnotationsAtom.relations`` so
 * user-editable relation CRUD operations don't have to reason about
 * structural items.
 */
export const structuralRelationshipsAtom = atom<RelationGroup[]>([]);

/**
 * Tracks whether structural annotations have been fetched for the current document.
 * Reset to false when navigating to a new document. Prevents redundant re-fetching
 * when the user toggles structural visibility multiple times.
 */
export const structuralAnnotationsLoadedAtom = atom<boolean>(false);

/**
 * Atom to manage all annotation objects.
 */
export const annotationObjsAtom = atom<
  (ServerTokenAnnotation | ServerSpanAnnotation)[]
>([]);

/**
 * Atom to manage document type annotations.
 */
export const docTypeAnnotationsAtom = atom<DocTypeAnnotation[]>([]);

/**
 * Atom to store the initial annotations when the document is first loaded.
 */
export const initialAnnotationsAtom = atom<
  (ServerTokenAnnotation | ServerSpanAnnotation)[]
>([]);

/**
 * Atom to store the initial relations when the document is first loaded.
 */
export const initialRelationsAtom = atom<RelationGroup[]>([]);

/**
 * Canonical, de-duplicated list of ALL annotations (regular + structural).
 * Re-computed only when either source array changes.
 */
export const allAnnotationsAtom = atom<
  (ServerTokenAnnotation | ServerSpanAnnotation)[]
>((get) => {
  const { annotations } = get(pdfAnnotationsAtom);
  const structural = get(structuralAnnotationsAtom);

  const seen = new Set<string>();
  const out: (ServerTokenAnnotation | ServerSpanAnnotation)[] = [];

  for (const a of [...annotations, ...structural]) {
    if (seen.has(a.id)) continue; // skip duplicates
    seen.add(a.id);
    out.push(a);
  }
  return out;
});

/**
 * Canonical, de-duplicated list of ALL relations (regular + structural).
 * Mirrors ``allAnnotationsAtom`` for relations: read this whenever a
 * consumer needs to reason about the full set, not just the user-editable
 * subset that lives in ``pdfAnnotationsAtom.relations``.
 */
export const allRelationsAtom = atom<RelationGroup[]>((get) => {
  const { relations } = get(pdfAnnotationsAtom);
  const structural = get(structuralRelationshipsAtom);

  const seen = new Set<string>();
  const out: RelationGroup[] = [];

  for (const r of [...relations, ...structural]) {
    if (seen.has(r.id)) continue;
    seen.add(r.id);
    out.push(r);
  }
  return out;
});

/**
 * Map { pageIndex -> annotations[] } built from the canonical list above.
 */
export const perPageAnnotationsAtom = atom((get) => {
  const all = get(allAnnotationsAtom);

  const map = new Map<
    number,
    (ServerTokenAnnotation | ServerSpanAnnotation)[]
  >();

  for (const a of all) {
    const pageIdx = a.page ?? 0; // annotations store zero-based page index
    if (!map.has(pageIdx)) map.set(pageIdx, []);
    map.get(pageIdx)!.push(a);
  }
  return map;
});
