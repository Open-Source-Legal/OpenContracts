/**
 * TxtAnnotatorWrapper Component
 *
 * A wrapper component that manages state for TxtAnnotator to minimize rerenders
 * of the parent DocumentViewer component.
 */

import React, { useState, useCallback } from "react";
import {
  useApproveAnnotation,
  useCreateAnnotation,
  useDeleteAnnotation,
  usePdfAnnotations,
  useRejectAnnotation,
  useUpdateAnnotation,
} from "../../hooks/AnnotationHooks";
import { ServerSpanAnnotation } from "../../types/annotations";
import { useDocText, useTextSearchState } from "../../context/DocumentAtom";
import TxtAnnotator from "../../renderers/txt/TxtAnnotator";
import { TextSearchSpanResult } from "../../../types";
import {
  useAnnotationControls,
  useAnnotationDisplay,
  useAnnotationSelection,
  useZoomLevel,
} from "../../context/UISettingsAtom";
import { useCorpusState } from "../../context/CorpusAtom";
import { useChatSourceState } from "../../context/ChatSourceAtom";

interface TxtAnnotatorWrapperProps {
  readOnly: boolean;
  allowInput: boolean;
}

export const TxtAnnotatorWrapper: React.FC<TxtAnnotatorWrapperProps> = ({
  readOnly,
  allowInput,
}) => {
  // Internal state management
  const { docText } = useDocText();
  const { pdfAnnotations } = usePdfAnnotations();

  const { selectedAnnotations, setSelectedAnnotations } =
    useAnnotationSelection();

  const { spanLabelsToView, activeSpanLabel } = useAnnotationControls();

  const { textSearchMatches } = useTextSearchState();
  const { spanLabels } = useCorpusState();
  const { zoomLevel } = useZoomLevel();

  const { showStructural } = useAnnotationDisplay();

  const handleCreateAnnotation = useCreateAnnotation();
  const handleDeleteAnnotation = useDeleteAnnotation();
  const handleUpdateAnnotation = useUpdateAnnotation();
  const handleApproveAnnotation = useApproveAnnotation();
  const handleRejectAnnotation = useRejectAnnotation();

  const { messages, selectedMessageId, selectedSourceIndex } =
    useChatSourceState();

  const chatSourceMatches = React.useMemo(() => {
    const allSources: {
      start_index: number;
      end_index: number;
      sourceId: string;
      messageId: string;
    }[] = [];

    for (const msg of messages) {
      for (const src of msg.sources) {
        // If this is a text-based source, we have numeric startIndex/endIndex
        if (
          src.isTextBased &&
          typeof src.startIndex === "number" &&
          typeof src.endIndex === "number"
        ) {
          allSources.push({
            start_index: src.startIndex,
            end_index: src.endIndex,
            sourceId: src.id,
            messageId: msg.messageId,
          });
        }
      }
    }

    return allSources;
  }, [messages]);

  console.log("chatSourceMatches", chatSourceMatches);

  // Memoized getSpan callback
  const getSpan = useCallback(
    (span: { start: number; end: number; text: string }) => {
      const selectedLabel = spanLabels.find(
        (label) => label.id === activeSpanLabel?.id
      );
      if (!selectedLabel) throw new Error("Selected label not found");

      return new ServerSpanAnnotation(
        0, // Page number (assuming single page)
        selectedLabel,
        span.text,
        false, // structural
        { start: span.start, end: span.end }, // json
        [], // myPermissions
        false, // approved
        false // rejected
      );
    },
    [spanLabels, activeSpanLabel]
  );

  // Filter annotations to only include ServerSpanAnnotations
  const filteredAnnotations = pdfAnnotations.annotations.filter(
    (annot): annot is ServerSpanAnnotation =>
      annot instanceof ServerSpanAnnotation
  );

  // Filter search results
  const filteredSearchResults =
    textSearchMatches?.filter(
      (match): match is TextSearchSpanResult => "start_index" in match
    ) ?? [];

  return (
    <div data-testid="txt-annotator-wrapper">
      <TxtAnnotator
        text={docText}
        annotations={filteredAnnotations}
        searchResults={filteredSearchResults}
        chatSources={chatSourceMatches}
        selectedChatSourceId={
          selectedMessageId && selectedSourceIndex
            ? `${selectedMessageId}.${selectedSourceIndex}`
            : undefined
        }
        getSpan={getSpan}
        visibleLabels={spanLabelsToView}
        availableLabels={spanLabels}
        selectedLabelTypeId={activeSpanLabel?.id ?? null}
        read_only={readOnly}
        allowInput={allowInput}
        zoom_level={zoomLevel}
        createAnnotation={handleCreateAnnotation}
        updateAnnotation={handleUpdateAnnotation}
        approveAnnotation={handleApproveAnnotation}
        rejectAnnotation={handleRejectAnnotation}
        deleteAnnotation={handleDeleteAnnotation}
        maxHeight="100%"
        maxWidth="100%"
        selectedAnnotations={selectedAnnotations}
        setSelectedAnnotations={setSelectedAnnotations}
        showStructuralAnnotations={showStructural}
      />
    </div>
  );
};

export default React.memo(TxtAnnotatorWrapper);
