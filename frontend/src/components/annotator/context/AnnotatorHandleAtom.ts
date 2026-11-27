import { atom } from "jotai";
import type { AnnotatorHandle } from "@os-legal/react-contract-annotate/core";

/**
 * The handle of the mounted PDF/DOCX viewer (`@os-legal/react-contract-annotate`),
 * or null while none is mounted (plain text, Markdown, still loading).
 *
 * Code outside the viewer that must move it without changing the selection
 * (for instance, jumping to a relationship) goes through this handle; a
 * change of the selected annotations or the active highlight already scrolls
 * the viewer by itself.
 */
export const annotatorHandleAtom = atom<AnnotatorHandle | null>(null);
