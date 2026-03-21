/**
 * DocxAnnotator Component
 *
 * Renders DOCX documents using Docxodus WASM with incremental annotation
 * overlay. Uses the convert-once / project-many pattern:
 *
 *   1. convertDocxToHtml()  — expensive (~900ms), cached on docxBytes change
 *   2. projectAnnotationsOntoHtml() — fast (~56ms), runs on annotation change
 *   3. generateAnnotationVisibilityCss() — instant, CSS-only label toggling
 *
 * Text selection creates new annotations using character offsets (same format
 * as TXT). Selection disambiguation uses DOM positions (anchorNode/focusNode)
 * and a TreeWalker to compute exact character offsets, resolving ambiguity
 * when the same text appears multiple times.
 */

import React, {
  useState,
  useEffect,
  useCallback,
  useRef,
  useMemo,
} from "react";
import {
  ANNOTATION_LABEL_CLASS,
  getGlobalOffsetFromDomPosition,
  pickClosestOccurrence,
} from "./docxOffsetUtils";
import {
  initialize as initDocxodus,
  convertDocxToHtml,
  projectAnnotationsOntoHtml,
  generateAnnotationCss,
  generateAnnotationVisibilityCss,
  findTextOccurrences,
  AnnotationLabelMode,
  PaginationMode,
} from "docxodus";
import { PaginatedDocument } from "docxodus/react";
import type {
  ExternalAnnotationSet,
  ExternalAnnotationProjectionSettings,
  AnnotationLabel,
} from "docxodus";
import { AnnotationLabelType } from "../../../../types/graphql-api";
import { ServerSpanAnnotation } from "../../types/annotations";
import { TextSearchSpanResult } from "../../../types";
import {
  SelectionActionMenu,
  ActionMenuItem,
  MenuDivider,
  ShortcutHint,
} from "../../components/SelectionActionMenu";
import { clampMenuPosition } from "../../../../utils/layout";
import DOMPurify from "dompurify";
import { Tag, X } from "lucide-react";
import { OS_LEGAL_COLORS } from "../../../../assets/configurations/osLegalStyles";
import { hexToRgb } from "../../../../utils/transform";

/** Stable empty arrays to avoid re-render loops. */
const EMPTY_ANNOTATIONS: ServerSpanAnnotation[] = [];
const EMPTY_SEARCH_RESULTS: TextSearchSpanResult[] = [];

interface ChatSourceHighlight {
  start_index: number;
  end_index: number;
  sourceId: string;
  messageId: string;
}

const EMPTY_CHAT_SOURCES: ChatSourceHighlight[] = [];

/** CSS class prefix for annotation elements produced by the projector. */
const CSS_CLASS_PREFIX = "oc-annot-";

/** Synthetic label IDs for search results and chat source highlights. */
const SEARCH_RESULT_LABEL_ID = "__search_result__";
const CHAT_SOURCE_LABEL_ID = "__chat_source__";
const CHAT_SOURCE_SELECTED_LABEL_ID = "__chat_source_selected__";

/**
 * DOMPurify config that preserves docxodus formatting (styles, classes)
 * while blocking scripts, event handlers, and dangerous elements.
 */
const SANITIZE_CONFIG: DOMPurify.Config = {
  FORCE_BODY: true,
  ADD_ATTR: [
    "data-annotation-id",
    "data-label-id",
    "data-label",
    "class",
    "style",
  ],
  ADD_TAGS: ["style"],
};

/** Stable projection settings shared by projection and CSS generation. */
const PROJECTION_SETTINGS: ExternalAnnotationProjectionSettings = {
  cssClassPrefix: CSS_CLASS_PREFIX,
  labelMode: AnnotationLabelMode.None,
  includeMetadata: true,
  // Both backend (Docxodus microservice) and frontend (Docxodus WASM) use the same
  // library, so offsets should align. Validation is kept enabled as a safety net in
  // case the two sides drift to different versions.
  validateBeforeProjection: true,
};

interface DocxAnnotatorProps {
  /** Raw DOCX file bytes */
  docxBytes: Uint8Array;
  /** Plain text content extracted by the backend parser */
  docText: string;
  /** Annotations to project onto the document */
  annotations: ServerSpanAnnotation[];
  /** Search results to highlight */
  searchResults?: TextSearchSpanResult[];
  /** Chat source highlights */
  chatSources?: ChatSourceHighlight[];
  /** Currently selected chat source ID */
  selectedChatSourceId?: string;
  /** Labels visible in the current filter */
  visibleLabels: AnnotationLabelType[];
  /** All available annotation labels */
  availableLabels: AnnotationLabelType[];
  /** Currently selected label type ID for new annotations */
  selectedLabelTypeId: string | null;
  /** Whether the annotator is read-only */
  readOnly: boolean;
  /** Whether user input is allowed */
  allowInput: boolean;
  /** Callback to create a new annotation from text selection */
  getSpan: (span: {
    start: number;
    end: number;
    text: string;
  }) => ServerSpanAnnotation;
  /** CRUD callbacks */
  createAnnotation: (annotation: ServerSpanAnnotation) => void;
  updateAnnotation?: (annotation: ServerSpanAnnotation) => void;
  approveAnnotation?: (annotationId: string) => void;
  rejectAnnotation?: (annotationId: string) => void;
  deleteAnnotation: (annotationId: string) => void;
  /** Selection state */
  selectedAnnotations: string[];
  setSelectedAnnotations: (ids: string[]) => void;
  /** Whether to show structural annotations */
  showStructuralAnnotations: boolean;
  /** Ref registration callback for sidebar scroll-into-view */
  onAnnotationRefChange?: (
    annotationId: string,
    element: HTMLElement | null
  ) => void;
  /** Zoom level */
  zoomLevel?: number;
  /** Max dimensions */
  maxHeight?: string;
  maxWidth?: string;
}

/**
 * Build an ExternalAnnotationSet from server annotations, search results,
 * and chat source highlights.
 *
 * Label visibility filtering is NOT done here — all annotations matching the
 * structural filter are included, and visibility is toggled via CSS rules
 * produced by generateAnnotationVisibilityCss().
 *
 * Search results and chat sources are projected as synthetic annotations with
 * special label IDs, styled via CSS in customCss.
 */
function buildExternalAnnotationSet(
  docText: string,
  annotations: ServerSpanAnnotation[],
  showStructural: boolean,
  searchResults: TextSearchSpanResult[],
  chatSources: ChatSourceHighlight[],
  selectedChatSourceId?: string
): ExternalAnnotationSet {
  const filteredAnnotations = annotations.filter((ann) => {
    if (ann.structural && !showStructural) return false;
    return true;
  });

  const labelledText = filteredAnnotations.map((ann) => ({
    id: ann.id,
    annotationLabel: ann.annotationLabel?.id ?? "Unknown",
    rawText: ann.rawText,
    page: 0,
    annotationJson: ann.json
      ? { start: ann.json.start, end: ann.json.end, text: ann.rawText }
      : undefined,
    annotationType: ann.structural ? "structural" : "text",
    structural: ann.structural,
  }));

  // Project search results as synthetic annotations (only when no chat sources)
  if (chatSources.length === 0) {
    for (let i = 0; i < searchResults.length; i++) {
      const sr = searchResults[i];
      const text = docText.slice(sr.start_index, sr.end_index);
      labelledText.push({
        id: `__sr_${i}`,
        annotationLabel: SEARCH_RESULT_LABEL_ID,
        rawText: text,
        page: 0,
        annotationJson: { start: sr.start_index, end: sr.end_index, text },
        annotationType: "text",
        structural: false,
      });
    }
  }

  // Project chat sources as synthetic annotations
  for (const cs of chatSources) {
    const text = docText.slice(cs.start_index, cs.end_index);
    const isSelected = cs.sourceId === selectedChatSourceId;
    labelledText.push({
      id: `__cs_${cs.sourceId}`,
      annotationLabel: isSelected
        ? CHAT_SOURCE_SELECTED_LABEL_ID
        : CHAT_SOURCE_LABEL_ID,
      rawText: text,
      page: 0,
      annotationJson: { start: cs.start_index, end: cs.end_index, text },
      annotationType: "text",
      structural: false,
    });
  }

  const textLabels: Record<
    string,
    {
      id: string;
      text: string;
      color: string;
      description?: string;
      icon?: string;
      labelType?: string;
    }
  > = {};
  for (const ann of filteredAnnotations) {
    const label = ann.annotationLabel;
    if (label && label.id && !textLabels[label.id]) {
      textLabels[label.id] = {
        id: label.id,
        text: label.text ?? "",
        color: label.color ?? "#FFD700",
        icon: "",
        labelType: "text",
      };
    }
  }

  // Add synthetic labels for search results and chat sources
  if (chatSources.length === 0 && searchResults.length > 0) {
    textLabels[SEARCH_RESULT_LABEL_ID] = {
      id: SEARCH_RESULT_LABEL_ID,
      text: "Search Result",
      color: OS_LEGAL_COLORS.searchHighlight,
      labelType: "text",
    };
  }
  if (chatSources.length > 0) {
    textLabels[CHAT_SOURCE_LABEL_ID] = {
      id: CHAT_SOURCE_LABEL_ID,
      text: "Chat Source",
      color: OS_LEGAL_COLORS.chatSourceHighlight,
      labelType: "text",
    };
    textLabels[CHAT_SOURCE_SELECTED_LABEL_ID] = {
      id: CHAT_SOURCE_SELECTED_LABEL_ID,
      text: "Chat Source (Active)",
      color: OS_LEGAL_COLORS.chatSourceHighlightActive,
      labelType: "text",
    };
  }

  return {
    title: "",
    content: docText,
    pageCount: 1,
    pawlsFileContent: [],
    docLabels: [],
    labelledText: labelledText as ExternalAnnotationSet["labelledText"],
    textLabels: textLabels as ExternalAnnotationSet["textLabels"],
    docLabelDefinitions: {},
    documentId: "",
    documentHash: "",
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    version: "1.0",
  };
}

/**
 * Build the labels record for generateAnnotationCss() from all available
 * corpus labels. This ensures CSS rules exist for every possible label
 * before any annotation uses it.
 */
function buildLabelsRecord(
  availableLabels: AnnotationLabelType[]
): Record<string, AnnotationLabel> {
  const record: Record<string, AnnotationLabel> = {};
  for (const label of availableLabels) {
    record[label.id] = {
      id: label.id,
      text: label.text ?? "",
      color: label.color ?? "#FFD700",
      description: label.description ?? "",
      icon: label.icon ?? "",
      labelType: "text",
    };
  }
  return record;
}

const DocxAnnotator: React.FC<DocxAnnotatorProps> = ({
  docxBytes,
  docText,
  annotations = EMPTY_ANNOTATIONS,
  searchResults = EMPTY_SEARCH_RESULTS,
  chatSources = EMPTY_CHAT_SOURCES,
  selectedChatSourceId,
  visibleLabels,
  availableLabels,
  selectedLabelTypeId,
  readOnly,
  allowInput,
  getSpan,
  createAnnotation,
  deleteAnnotation,
  selectedAnnotations,
  setSelectedAnnotations,
  showStructuralAnnotations,
  onAnnotationRefChange,
  zoomLevel = 1,
  maxHeight = "100%",
  maxWidth = "100%",
}) => {
  // Cached base HTML from one-time DOCX conversion (sanitized)
  const [baseHtml, setBaseHtml] = useState<string>("");
  // Annotated HTML with all annotations projected (passed to PaginatedDocument)
  const [annotatedHtml, setAnnotatedHtml] = useState<string>("");
  // CSS from docxodus for annotation highlight styles
  const [annotationCss, setAnnotationCss] = useState<string>("");
  // CSS for toggling label visibility without re-projecting
  const [visibilityCss, setVisibilityCss] = useState<string>("");

  const [wasmReady, setWasmReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [converting, setConverting] = useState(false);
  const [paginationReady, setPaginationReady] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  // Context menu state for annotation creation
  const [menuPosition, setMenuPosition] = useState<{
    x: number;
    y: number;
  } | null>(null);
  const [pendingSelection, setPendingSelection] = useState<{
    text: string;
    start: number;
    end: number;
  } | null>(null);

  // ── Effect 1: Initialize Docxodus WASM ──────────────────────────────
  useEffect(() => {
    let cancelled = false;
    initDocxodus()
      .then(() => {
        if (!cancelled) setWasmReady(true);
      })
      .catch((err) => {
        if (!cancelled) setError(`Failed to initialize Docxodus WASM: ${err}`);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // ── Effect 2: Convert DOCX → base HTML (expensive, cached) ─────────
  // Only re-runs when docxBytes changes. The base HTML is sanitized once
  // here; subsequent projection operates on this safe foundation.
  useEffect(() => {
    if (!wasmReady || !docxBytes || docxBytes.length === 0) return;

    let cancelled = false;
    setConverting(true);

    convertDocxToHtml(docxBytes, {
      paginationMode: PaginationMode.Paginated,
    })
      .then((html) => {
        if (!cancelled) {
          // Sanitize while preserving docxodus formatting (see SANITIZE_CONFIG).
          // PaginatedDocument handles styles internally so no extraction needed.
          const sanitized = DOMPurify.sanitize(html, SANITIZE_CONFIG);
          setBaseHtml(sanitized);
          setAnnotatedHtml(sanitized);
          setPaginationReady(false);
          setConverting(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          console.error("DOCX conversion error:", err);
          setError(`DOCX conversion failed: ${err}`);
          setConverting(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [wasmReady, docxBytes]);

  // ── Effect 3: Project annotations onto base HTML (~56ms) ────────────
  // Re-runs when annotations change or structural toggle flips.
  // Label visibility is handled separately via CSS (Effect 5).
  useEffect(() => {
    if (!baseHtml || !wasmReady) return;
    let cancelled = false;

    const annotationSet = buildExternalAnnotationSet(
      docText,
      annotations,
      showStructuralAnnotations,
      searchResults,
      chatSources,
      selectedChatSourceId
    );

    if (annotationSet.labelledText.length === 0) {
      setAnnotatedHtml(baseHtml);
      return;
    }

    projectAnnotationsOntoHtml(baseHtml, annotationSet, PROJECTION_SETTINGS)
      .then((html) => {
        if (!cancelled) {
          setPaginationReady(false);
          setAnnotatedHtml(DOMPurify.sanitize(html, SANITIZE_CONFIG));
        }
      })
      .catch((err) => {
        if (!cancelled) {
          console.error("Annotation projection error:", err);
          setAnnotatedHtml(baseHtml);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [
    baseHtml,
    docText,
    annotations,
    showStructuralAnnotations,
    searchResults,
    chatSources,
    selectedChatSourceId,
    wasmReady,
  ]);

  // ── Effect 4: Generate annotation CSS from label definitions ────────
  useEffect(() => {
    if (!wasmReady) return;
    let cancelled = false;

    const labels = buildLabelsRecord(availableLabels);
    if (Object.keys(labels).length === 0) {
      setAnnotationCss("");
      return;
    }

    generateAnnotationCss(labels, PROJECTION_SETTINGS)
      .then((css) => {
        if (!cancelled) setAnnotationCss(css);
      })
      .catch((err) => {
        if (!cancelled) console.error("Annotation CSS generation error:", err);
      });

    return () => {
      cancelled = true;
    };
  }, [wasmReady, availableLabels]);

  // ── Effect 5: Generate visibility CSS (instant, CSS-only) ───────────
  // When label filters change, toggle annotation visibility via CSS rules
  // instead of re-projecting the entire HTML.
  useEffect(() => {
    if (!wasmReady) return;
    let cancelled = false;

    // Empty visibleLabels means "no filter active" — show all annotations.
    // Only compute hidden labels when a filter is explicitly set.
    if (visibleLabels.length === 0) {
      setVisibilityCss("");
      return;
    }

    const visibleLabelIds = new Set(visibleLabels.map((l) => l.id));
    const allLabelIds = new Set(
      annotations
        .map((a) => a.annotationLabel?.id)
        .filter((id): id is string => Boolean(id))
    );
    const hiddenLabelIds = [...allLabelIds].filter(
      (id) => !visibleLabelIds.has(id)
    );

    if (hiddenLabelIds.length === 0) {
      setVisibilityCss("");
      return;
    }

    generateAnnotationVisibilityCss(hiddenLabelIds, CSS_CLASS_PREFIX)
      .then((css) => {
        if (!cancelled) setVisibilityCss(css);
      })
      .catch((err) => {
        if (!cancelled) console.error("Visibility CSS generation error:", err);
      });

    return () => {
      cancelled = true;
    };
  }, [wasmReady, visibleLabels, annotations]);

  // ── Effect 6: Register annotation refs for sidebar scroll-into-view ──
  // After annotated HTML is rendered, query projected annotation elements
  // and report them via onAnnotationRefChange so the sidebar can scroll to them.
  const registeredRefsRef = useRef<Set<string>>(new Set());
  useEffect(() => {
    if (!onAnnotationRefChange || !annotatedHtml || !containerRef.current)
      return;

    // Wait a tick for dangerouslySetInnerHTML to flush to the DOM
    const timer = requestAnimationFrame(() => {
      const container = containerRef.current;
      if (!container) return;

      const currentIds = new Set<string>();
      const elements = container.querySelectorAll("[data-annotation-id]");
      elements.forEach((el) => {
        const id = el.getAttribute("data-annotation-id");
        // Skip synthetic search result / chat source annotations
        if (id && !id.startsWith("__sr_") && !id.startsWith("__cs_")) {
          if (!currentIds.has(id)) {
            currentIds.add(id);
            onAnnotationRefChange(id, el as HTMLElement);
          }
        }
      });

      // Unregister previously registered annotations that are no longer in the DOM
      for (const prevId of registeredRefsRef.current) {
        if (!currentIds.has(prevId)) {
          onAnnotationRefChange(prevId, null);
        }
      }
      registeredRefsRef.current = currentIds;
    });

    return () => cancelAnimationFrame(timer);
  }, [annotatedHtml, onAnnotationRefChange]);

  // ── Effect 7: Scroll to selected annotation ─────────────────────────
  // When selectedAnnotations changes, scroll the first selected annotation
  // into view (matching TXT/PDF behavior). Gated on paginationReady to
  // ensure PaginatedDocument has finished rendering the DOM elements.
  useEffect(() => {
    if (
      selectedAnnotations.length === 0 ||
      !paginationReady ||
      !containerRef.current
    )
      return;

    const targetId = selectedAnnotations[0];
    const targetEl = containerRef.current.querySelector(
      `[data-annotation-id="${CSS.escape(targetId)}"]`
    ) as HTMLElement | null;

    if (!targetEl) return;

    targetEl.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [selectedAnnotations, paginationReady]);

  // Handle text selection for new annotation creation.
  // Uses findTextOccurrences for text matching and DOM position for
  // disambiguation when the same text appears multiple times.
  const handleMouseUp = useCallback(
    (e: React.MouseEvent) => {
      try {
        if (readOnly || !allowInput || !selectedLabelTypeId) return;

        const selection = window.getSelection();
        if (!selection || selection.isCollapsed || !selection.toString().trim())
          return;

        // Ignore selections that originate outside the DOCX container
        if (!containerRef.current?.contains(selection.anchorNode)) return;

        // Get the raw selected text. For cross-page selections this may
        // include page number artifacts (e.g. "...text\n1\nmore text...").
        // Clean it by removing isolated numbers on their own lines
        // (PaginatedDocument page numbers).
        const rawText = selection.toString();
        const cleanedText = rawText
          .replace(/\n\d+\n/g, "\n") // Remove "1", "2" etc. between newlines
          .trim();

        if (!cleanedText) return;

        // Search for the cleaned text in docText
        let occurrences = findTextOccurrences(docText, cleanedText);

        // If no exact match (common for cross-page selections with whitespace
        // differences), try collapsing whitespace for a fuzzy match
        if (occurrences.length === 0) {
          const normalized = cleanedText.replace(/\s+/g, " ");
          occurrences = findTextOccurrences(
            docText.replace(/\s+/g, " "),
            normalized
          );
          // Map back to original docText offsets by searching from the
          // normalized match position
          if (occurrences.length > 0) {
            const approxStart = occurrences[0].start;
            // Find the actual position in docText near this offset
            const searchWindow = docText.substring(
              Math.max(0, approxStart - 50),
              approxStart + cleanedText.length + 50
            );
            const firstWords = cleanedText.substring(0, 30);
            const idx = searchWindow.indexOf(firstWords);
            if (idx >= 0) {
              const realStart = Math.max(0, approxStart - 50) + idx;
              // Find the end by matching the last few words
              const lastWords = cleanedText.substring(cleanedText.length - 30);
              const endSearch = docText.indexOf(
                lastWords,
                realStart + cleanedText.length - 60
              );
              if (endSearch >= 0) {
                occurrences = [
                  { start: realStart, end: endSearch + lastWords.length },
                ];
              }
            }
          }
        }

        if (occurrences.length === 0) return;

        let match = occurrences[0];

        // Disambiguate if multiple matches using DOM position
        if (occurrences.length > 1) {
          const contentEl = containerRef.current?.querySelector(
            ".docx-content"
          ) as HTMLElement | null;
          if (contentEl) {
            const anchorOffset = getGlobalOffsetFromDomPosition(
              contentEl,
              selection.anchorNode,
              selection.anchorOffset,
              ANNOTATION_LABEL_CLASS
            );
            if (anchorOffset !== null) {
              match = pickClosestOccurrence(occurrences, anchorOffset);
            }
          }
        }

        const menuPos = clampMenuPosition(e.clientX, e.clientY);
        setMenuPosition(menuPos);
        setPendingSelection({
          text: docText.substring(match.start, match.end),
          start: match.start,
          end: match.end,
        });
      } catch (err) {
        console.warn("Error handling text selection:", err);
      }
    },
    [readOnly, allowInput, selectedLabelTypeId, docText]
  );

  // Handle annotation creation from menu
  const handleCreateAnnotation = useCallback(() => {
    if (!pendingSelection) return;

    try {
      const newAnnotation = getSpan(pendingSelection);
      createAnnotation(newAnnotation);
    } catch (err) {
      console.warn("Failed to create annotation from selection:", err);
    }

    setMenuPosition(null);
    setPendingSelection(null);
    window.getSelection()?.removeAllRanges();
  }, [pendingSelection, getSpan, createAnnotation]);

  // Handle clicking on projected annotation spans in the HTML
  const handleClick = useCallback(
    (e: React.MouseEvent) => {
      const target = e.target as HTMLElement;

      const annotationEl = target.closest(
        "[data-annotation-id]"
      ) as HTMLElement | null;
      if (annotationEl) {
        const annotationId = annotationEl.getAttribute("data-annotation-id");
        // Ignore clicks on synthetic search result / chat source annotations
        if (
          annotationId &&
          !annotationId.startsWith("__sr_") &&
          !annotationId.startsWith("__cs_")
        ) {
          if (e.ctrlKey || e.metaKey) {
            setSelectedAnnotations(
              selectedAnnotations.includes(annotationId)
                ? selectedAnnotations.filter((id) => id !== annotationId)
                : [...selectedAnnotations, annotationId]
            );
          } else {
            setSelectedAnnotations([annotationId]);
          }
          return;
        }
      }

      if (!menuPosition) {
        setSelectedAnnotations([]);
      }
    },
    [selectedAnnotations, setSelectedAnnotations, menuPosition]
  );

  // Close menu on escape
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setMenuPosition(null);
        setPendingSelection(null);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // App-specific CSS for annotation highlights, labels, and hover effects.
  // Labels are rendered via CSS ::before pseudo-elements on the first span
  // of each annotation, avoiding DOM disruption from inline label elements.
  const customCss = useMemo(() => {
    const selectedStyles = selectedAnnotations
      .map(
        (id) => `
      [data-annotation-id="${CSS.escape(id)}"] {
        outline: 2px solid ${OS_LEGAL_COLORS.primaryBlue} !important;
        outline-offset: 1px;
        background-color: rgba(59, 130, 246, 0.15) !important;
      }
    `
      )
      .join("\n");

    // Build per-label ::before rules with the label's color.
    // Uses data-label-id to match and data-label for the text content.
    const labelColorMap = new Map<string, string>();
    for (const label of availableLabels) {
      labelColorMap.set(label.id, label.color || "cccccc");
    }

    const labelStyles = [...labelColorMap.entries()]
      .map(([labelId, color]) => {
        const rgb = hexToRgb(color);
        const bgColor = `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, 0.15)`;
        return `
      /* Highlight background for label ${CSS.escape(labelId)} */
      .${CSS_CLASS_PREFIX}highlight[data-label-id="${CSS.escape(labelId)}"] {
        background-color: ${bgColor};
        border-bottom: 2px solid #${color.replace("#", "")};
      }
      /* Label tag on first span of annotation */
      .${CSS_CLASS_PREFIX}single[data-label-id="${CSS.escape(
          labelId
        )}"]::before,
      .${CSS_CLASS_PREFIX}start[data-label-id="${CSS.escape(
          labelId
        )}"]::before {
        content: attr(data-label);
        position: absolute;
        top: -1.4em;
        left: 0;
        font-size: 0.65em;
        line-height: 1;
        padding: 1px 4px;
        border-radius: 3px;
        background-color: #${color.replace("#", "")};
        color: white;
        white-space: nowrap;
        pointer-events: auto;
        cursor: pointer;
        z-index: 10;
      }
      `;
      })
      .join("\n");

    return `
      /* Constrain docxodus content divs to container width so text-align
         and word-wrap work correctly (they default to content-sized). */
      .docx-content > div {
        max-width: 100%;
      }
      /* Annotation spans need relative positioning for ::before labels */
      .${CSS_CLASS_PREFIX}single,
      .${CSS_CLASS_PREFIX}start {
        position: relative;
      }
      [data-annotation-id] {
        cursor: pointer;
        transition: outline 0.15s ease, background-color 0.15s ease;
      }
      [data-annotation-id]:hover {
        outline: 1px solid ${OS_LEGAL_COLORS.borderHover};
        outline-offset: 1px;
      }
      /* Search result highlighting */
      [data-annotation-id^="__sr_"] {
        background-color: ${OS_LEGAL_COLORS.searchHighlight} !important;
        cursor: default;
      }
      [data-annotation-id^="__sr_"]::before { display: none; }
      /* Chat source highlighting */
      [data-annotation-id^="__cs_"] {
        background-color: ${OS_LEGAL_COLORS.chatSourceHighlight} !important;
        cursor: default;
      }
      [data-annotation-id^="__cs_"]::before { display: none; }
      [data-annotation-id^="__cs_"][data-label="${CHAT_SOURCE_SELECTED_LABEL_ID}"] {
        background-color: ${OS_LEGAL_COLORS.chatSourceHighlightActive} !important;
      }
      ${labelStyles}
      ${selectedStyles}
    `;
  }, [selectedAnnotations, availableLabels]);

  if (error) {
    return (
      <div
        style={{
          padding: "2rem",
          color: OS_LEGAL_COLORS.textSecondary,
          textAlign: "center",
        }}
      >
        <p>Unable to display this document. Please try reloading the page.</p>
      </div>
    );
  }

  if (!wasmReady || converting || !annotatedHtml) {
    return (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          height: "100%",
          color: OS_LEGAL_COLORS.textSecondary,
          fontSize: "0.875rem",
        }}
      >
        {!wasmReady
          ? "Initializing DOCX renderer..."
          : converting
          ? "Converting document..."
          : "Projecting annotations..."}
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      data-testid="docx-annotator"
      style={{
        maxHeight,
        maxWidth,
        overflow: "auto",
        position: "relative",
        fontSize: `${zoomLevel}em`,
      }}
      onMouseUp={handleMouseUp}
      onClick={handleClick}
    >
      <style>{annotationCss}</style>
      <style>{visibilityCss}</style>
      <style>{customCss}</style>
      <div className="docx-content">
        <PaginatedDocument
          html={annotatedHtml}
          scale={zoomLevel}
          showPageNumbers={true}
          pageGap={20}
          backgroundColor={OS_LEGAL_COLORS.background}
          onPaginationComplete={() => setPaginationReady(true)}
        />
      </div>

      {/* Annotation creation menu */}
      {menuPosition && pendingSelection && (
        <SelectionActionMenu
          ref={menuRef}
          onMouseDown={(e) => e.stopPropagation()}
          style={{
            position: "fixed",
            left: `${menuPosition.x}px`,
            top: `${menuPosition.y}px`,
            zIndex: 1000,
          }}
        >
          <ActionMenuItem onClick={handleCreateAnnotation}>
            <Tag size={14} />
            <span>Annotate Selection</span>
            <ShortcutHint>Enter</ShortcutHint>
          </ActionMenuItem>
          <MenuDivider />
          <ActionMenuItem
            onClick={() => {
              setMenuPosition(null);
              setPendingSelection(null);
              window.getSelection()?.removeAllRanges();
            }}
          >
            <X size={14} />
            <span>Cancel</span>
          </ActionMenuItem>
        </SelectionActionMenu>
      )}
    </div>
  );
};

export default React.memo(DocxAnnotator);
