/**
 * Wires OpenContracts' annotator state (Jotai atoms and Apollo reactive
 * vars) to the props of `@os-legal/react-contract-annotate`'s PDF and DOCX
 * viewers. The library draws the document and reports what the user does;
 * everything it reports is written back to OpenContracts' own state here,
 * which stays the single source of truth for every other panel.
 *
 * - Annotations, relations, and highlights (search hits, chat sources, the
 *   `?tb=` text block) come from OpenContracts' state.
 * - Selection, zoom, and the active highlight are controlled.
 * - Display filters pass straight through; the library applies the same
 *   rules `useVisibleAnnotations` does.
 * - A text selection opens `AnnotationSelectionMenu`. Edit and Delete sit
 *   beside each annotation's label, gated by its permissions.
 */
import React, { useCallback, useMemo, useState } from "react";
import { useReactiveVar } from "@apollo/client";
import { Provider as JotaiProvider, useSetAtom, useStore } from "jotai";
import { Pencil, Trash2 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import type {
  AnnotationAction,
  AnnotationDraft,
  AnnotatorCommonProps,
  AnnotatorHandle,
  Highlight,
  LabelDisplay,
  SelectionMenuContext,
} from "@os-legal/react-contract-annotate/core";

import {
  OC_URL_LABEL,
  OC_URL_LABEL_COLOR,
  PENDING_OC_URL_LABEL_ID,
  TEXT_BLOCK_DEEPLINK_ID,
  Z_INDEX,
} from "../../../assets/configurations/constants";
import { highlightedTextBlock } from "../../../graphql/cache";
import {
  AnnotationLabelType,
  LabelDisplayBehavior,
  LabelType,
} from "../../../types/graphql-api";
import { decodeTextBlock } from "../../../utils/textBlockEncoding";
import { PermissionTypes } from "../../types";
import { CreateUrlAnnotationModal } from "../components/modals/CreateUrlAnnotationModal";
import { EditLabelModal } from "../components/modals/EditLabelModal";
import { annotatorHandleAtom } from "../context/AnnotatorHandleAtom";
import { useChatSourceState } from "../context/ChatSourceAtom";
import {
  useSetViewStateError,
  useTextSearchState,
} from "../context/DocumentAtom";
import {
  useAnnotationControls,
  useAnnotationDisplay,
  useAnnotationSelection,
  useZoomLevel,
} from "../context/UISettingsAtom";
import {
  useDeleteAnnotation,
  useUpdateAnnotation,
} from "../hooks/AnnotationHooks";
import { useAllAnnotations } from "../hooks/useAllAnnotations";
import { useAllRelations } from "../hooks/useAllRelations";
import { useClearTextBlockOnInteraction } from "../hooks/useClearTextBlockOnInteraction";
import {
  ServerSpanAnnotation,
  ServerTokenAnnotation,
} from "../types/annotations";
import { isUrlAnnotation, openAnnotationUrl } from "../utils/urlAnnotation";
import { AnnotationSelectionMenu } from "./AnnotationSelectionMenu";
import {
  chatSourceHighlight,
  chatSourceHighlightId,
  draftToAnnotation,
  OcAnnotation,
  parseHighlightId,
  searchHighlight,
  searchHighlightId,
  textBlockHighlight,
  toViewerAnnotation,
  toViewerLabel,
  toViewerRelation,
  ViewerFormat,
} from "./convert";

export interface ViewerBindingsOptions {
  format: ViewerFormat;
  /** The document may not be annotated (Copy Text / Copy Link still work). */
  readOnly: boolean;
  /** Persists an annotation the user made from a selection. */
  createAnnotation: (annotation: OcAnnotation) => Promise<void>;
  /** Persists an OC_URL link annotation; omitted where links can't be made. */
  createUrlAnnotation?: (
    annotation: ServerTokenAnnotation,
    url: string
  ) => Promise<void>;
}

export interface ViewerBindings {
  /** The props every format takes, for `PdfAnnotator` / `DocxAnnotator`. */
  props: AnnotatorCommonProps<OcAnnotation>;
  /** The viewer's `ref`: publishes its handle to `annotatorHandleAtom`. */
  handleRef: (handle: AnnotatorHandle | null) => void;
  /** Dialogs opened from the viewer; render them beside it. */
  dialogs: React.ReactNode;
}

/** Links embedded in a PDF open in a new tab when they use one of these. */
const NATIVE_LINK_PROTOCOLS = ["http:", "https:", "mailto:"];

const VIEWER_STYLE = {
  "--rca-z-menu": String(Z_INDEX.CONTEXT_MENU),
} as React.CSSProperties;

function toLabelDisplay(
  hideLabels: boolean,
  showLabels: LabelDisplayBehavior
): LabelDisplay {
  if (hideLabels || showLabels === LabelDisplayBehavior.HIDE) return "hide";
  return showLabels === LabelDisplayBehavior.ALWAYS ? "always" : "hover";
}

function canChange(annotation: OcAnnotation, permission: PermissionTypes) {
  return (
    annotation.myPermissions.includes(permission) &&
    !annotation.annotationLabel.readonly
  );
}

function openNativeLink(url: string): void {
  try {
    if (NATIVE_LINK_PROTOCOLS.includes(new URL(url).protocol)) {
      window.open(url, "_blank", "noopener,noreferrer");
    }
  } catch {
    // Not an absolute URL: nothing to open.
  }
}

/** The placeholder label of a link annotation the server has not seen yet. */
const PENDING_URL_LABEL = {
  id: PENDING_OC_URL_LABEL_ID,
  text: OC_URL_LABEL,
  color: OC_URL_LABEL_COLOR,
  labelType: LabelType.TokenLabel,
} as AnnotationLabelType;

export function useViewerBindings({
  format,
  readOnly,
  createAnnotation,
  createUrlAnnotation,
}: ViewerBindingsOptions): ViewerBindings {
  const navigate = useNavigate();
  // The library renders its slots inside its own Jotai Provider (a private
  // store per viewer), which would shadow OpenContracts' store for every
  // atom hook in slot content; the selection menu is handed ours back.
  const hostStore = useStore();
  const setHandle = useSetAtom(annotatorHandleAtom);
  const setViewStateError = useSetViewStateError();

  const allAnnotations = useAllAnnotations();
  const allRelations = useAllRelations();
  const { selectedAnnotations, setSelectedAnnotations, selectedRelations } =
    useAnnotationSelection();
  const { zoomLevel, setZoomLevel } = useZoomLevel();
  const {
    showStructural,
    showStructuralRelationships,
    showSelectedOnly,
    showBoundingBoxes,
    showLabels,
    hideLabels,
  } = useAnnotationDisplay();
  const { spanLabelsToView, activeSpanLabel } = useAnnotationControls();
  const {
    textSearchMatches,
    selectedTextSearchMatchIndex,
    setSelectedTextSearchMatchIndex,
  } = useTextSearchState();
  const {
    messages,
    selectedMessageId,
    selectedSourceIndex,
    setChatSourceState,
  } = useChatSourceState();
  const textBlockParam = useReactiveVar(highlightedTextBlock);

  const deleteAnnotation = useDeleteAnnotation();
  const updateAnnotation = useUpdateAnnotation();

  useClearTextBlockOnInteraction(selectedAnnotations, selectedMessageId);

  /* ---------------- data ------------------------------------------- */

  const annotations = useMemo(
    () =>
      allAnnotations
        .filter((a) =>
          format === "pdf"
            ? a instanceof ServerTokenAnnotation
            : a instanceof ServerSpanAnnotation
        )
        .map(toViewerAnnotation),
    [allAnnotations, format]
  );

  const relations = useMemo(
    () => allRelations.map(toViewerRelation),
    [allRelations]
  );

  const selectedMessage = useMemo(
    () => messages.find((m) => m.messageId === selectedMessageId),
    [messages, selectedMessageId]
  );

  const textBlock = useMemo(() => {
    const block = textBlockParam ? decodeTextBlock(textBlockParam) : null;
    return block ? textBlockHighlight(block, format) : null;
  }, [textBlockParam, format]);

  const highlights = useMemo<Highlight[]>(() => {
    // A selected chat message shows its sources alone (or the one source
    // picked), without search hits or the text block.
    if (selectedMessage) {
      const total = selectedMessage.sources.length;
      return selectedMessage.sources.flatMap((source, index) => {
        if (selectedSourceIndex !== null && selectedSourceIndex !== index) {
          return [];
        }
        const highlight = chatSourceHighlight(
          source,
          selectedMessage.messageId,
          index,
          total,
          format
        );
        return highlight ? [highlight] : [];
      });
    }
    // PDF paints only the search hit being looked at; DOCX paints them all.
    const matches = textSearchMatches.filter((m) =>
      format === "pdf" ? "tokens" in m : "start_index" in m
    );
    const shown =
      format === "pdf"
        ? matches.filter((m) => m.id === selectedTextSearchMatchIndex)
        : matches;
    const out = shown.map((m) => searchHighlight(m, textSearchMatches.length));
    if (textBlock) out.push(textBlock);
    return out;
  }, [
    selectedMessage,
    selectedSourceIndex,
    textSearchMatches,
    selectedTextSearchMatchIndex,
    textBlock,
    format,
  ]);

  // The highlight the viewer scrolls to: the picked chat source (the first
  // one when none is picked), else the current search hit, else the text
  // block.
  const activeHighlightId = useMemo(() => {
    const ids = new Set(highlights.map((h) => h.id));
    const candidates = [
      selectedMessage
        ? chatSourceHighlightId(
            selectedMessage.messageId,
            selectedSourceIndex ?? 0
          )
        : null,
      searchHighlightId(selectedTextSearchMatchIndex),
      TEXT_BLOCK_DEEPLINK_ID,
    ];
    return candidates.find((id) => id !== null && ids.has(id)) ?? null;
  }, [
    highlights,
    selectedMessage,
    selectedSourceIndex,
    selectedTextSearchMatchIndex,
  ]);

  // A click on a search hit or chat source makes it the current one.
  const onActiveHighlightChange = useCallback(
    (id: string | null) => {
      const ref = parseHighlightId(id);
      if (ref?.kind === "search") {
        setSelectedTextSearchMatchIndex(ref.matchId);
      } else if (ref?.kind === "chatSource") {
        setChatSourceState((prev) => ({
          ...prev,
          selectedSourceIndex: ref.sourceIndex,
        }));
      }
    },
    [setSelectedTextSearchMatchIndex, setChatSourceState]
  );

  /* ---------------- selection and display -------------------------- */

  const selectedRelationIds = useMemo(
    () => selectedRelations.map((r) => r.id),
    [selectedRelations]
  );

  const visibleLabelIds = useMemo(
    () =>
      spanLabelsToView && spanLabelsToView.length > 0
        ? spanLabelsToView.map((l) => l.id)
        : null,
    [spanLabelsToView]
  );

  const activeLabel = useMemo(
    () => (activeSpanLabel ? toViewerLabel(activeSpanLabel) : null),
    [activeSpanLabel]
  );

  // A plain click on a PDF annotation toggles it in the selection, as in
  // OpenContracts' own renderer; the library toggles on a modifier-click by
  // itself, and a plain click on a link opens the link instead. On DOCX
  // the library's click model (click selects, Ctrl/Cmd-click toggles) is
  // OpenContracts' already.
  const onAnnotationClick = useCallback<
    NonNullable<AnnotatorCommonProps<OcAnnotation>["onAnnotationClick"]>
  >(
    (annotation, event) => {
      if (format !== "pdf") return;
      if (event.shiftKey || event.ctrlKey || event.metaKey) return;
      if (annotation.meta && isUrlAnnotation(annotation.meta)) return;
      setSelectedAnnotations(
        selectedAnnotations.includes(annotation.id)
          ? selectedAnnotations.filter((id) => id !== annotation.id)
          : [...selectedAnnotations, annotation.id]
      );
    },
    [format, selectedAnnotations, setSelectedAnnotations]
  );

  const onOpenLink = useCallback<
    NonNullable<AnnotatorCommonProps<OcAnnotation>["onOpenLink"]>
  >(
    (url, source) => {
      if (source === "native") openNativeLink(url);
      else if (source.meta) openAnnotationUrl(source.meta, navigate);
    },
    [navigate]
  );

  /* ---------------- creating --------------------------------------- */

  const onCreateAnnotation = useCallback(
    async (draft: AnnotationDraft) => {
      if (!activeSpanLabel) return;
      await createAnnotation(draftToAnnotation(draft, activeSpanLabel, format));
    },
    [activeSpanLabel, createAnnotation, format]
  );

  // "Add link…": the selection stays painted while the URL is asked for.
  const [linkSelection, setLinkSelection] =
    useState<SelectionMenuContext | null>(null);

  const closeLinkDialog = useCallback(() => {
    linkSelection?.clear();
    setLinkSelection(null);
  }, [linkSelection]);

  const confirmLink = useCallback(
    async (url: string) => {
      if (linkSelection && createUrlAnnotation) {
        const annotation = draftToAnnotation(
          linkSelection.pending,
          PENDING_URL_LABEL,
          "pdf"
        ) as ServerTokenAnnotation;
        await createUrlAnnotation(annotation, url);
      }
      closeLinkDialog();
    },
    [linkSelection, createUrlAnnotation, closeLinkDialog]
  );

  const canCreateLinks = format === "pdf" && Boolean(createUrlAnnotation);

  const renderSelectionMenu = useCallback(
    (ctx: SelectionMenuContext) =>
      linkSelection ? null : (
        <JotaiProvider store={hostStore}>
          <AnnotationSelectionMenu
            ctx={ctx}
            format={format}
            readOnly={readOnly}
            onStartCreateLink={canCreateLinks ? setLinkSelection : undefined}
          />
        </JotaiProvider>
      ),
    [linkSelection, format, readOnly, canCreateLinks, hostStore]
  );

  /* ---------------- controls beside a label ------------------------ */

  const [editing, setEditing] = useState<OcAnnotation | null>(null);

  const annotationActions = useMemo<AnnotationAction<OcAnnotation>[]>(
    () => [
      {
        id: "edit",
        label: "Edit Annotation",
        icon: <Pencil size={14} />,
        isVisible: (a) =>
          Boolean(a.meta) && canChange(a.meta!, PermissionTypes.CAN_UPDATE),
        onClick: (a) => a.meta && setEditing(a.meta),
      },
      {
        id: "delete",
        label: "Delete Annotation",
        icon: <Trash2 size={14} />,
        isVisible: (a) =>
          Boolean(a.meta) && canChange(a.meta!, PermissionTypes.CAN_REMOVE),
        onClick: (a) => {
          void deleteAnnotation(a.id);
        },
      },
    ],
    [deleteAnnotation]
  );

  const dialogs = (
    <>
      {linkSelection && (
        <CreateUrlAnnotationModal
          visible
          selectedText={linkSelection.pending.rawText}
          onCancel={closeLinkDialog}
          onConfirm={(url) => void confirmLink(url)}
        />
      )}
      {editing && editing.annotationLabel.text === OC_URL_LABEL && (
        <CreateUrlAnnotationModal
          visible
          selectedText={editing.rawText}
          initialUrl={editing.linkUrl ?? ""}
          onCancel={() => setEditing(null)}
          onConfirm={(url) => {
            updateAnnotation(editing.update({ linkUrl: url }));
            setEditing(null);
          }}
        />
      )}
      {editing && editing.annotationLabel.text !== OC_URL_LABEL && (
        <EditLabelModal
          annotation={editing}
          visible
          onHide={() => setEditing(null)}
        />
      )}
    </>
  );

  const props: AnnotatorCommonProps<OcAnnotation> = {
    annotations,
    relations,
    highlights,
    selectedAnnotationIds: selectedAnnotations,
    onSelectionChange: setSelectedAnnotations,
    zoom: zoomLevel,
    onZoomChange: setZoomLevel,
    activeHighlightId,
    onActiveHighlightChange,
    selectedRelationIds,
    showStructural,
    showStructuralRelationships,
    // A selected chat message narrows the PDF to the selected annotations.
    showSelectedOnly:
      showSelectedOnly || (format === "pdf" && Boolean(selectedMessage)),
    showBoundingBoxes,
    labelDisplay: toLabelDisplay(hideLabels, showLabels),
    visibleLabelIds,
    readOnly,
    activeLabel,
    onCreateAnnotation,
    onAnnotationClick,
    onOpenLink,
    annotationActions,
    renderSelectionMenu,
    onError: setViewStateError,
    style: VIEWER_STYLE,
  };

  return { props, handleRef: setHandle, dialogs };
}
