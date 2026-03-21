/**
 * DocxAnnotatorWrapper Component
 *
 * A wrapper component that manages state for DocxAnnotator to minimize rerenders
 * of the parent DocumentViewer component. Mirrors TxtAnnotatorWrapper's pattern.
 */

import React, { useCallback, useMemo } from "react";
import { useSetAtom } from "jotai";
import {
  useApproveAnnotation,
  useCreateAnnotation,
  useDeleteAnnotation,
  usePdfAnnotations,
  useRejectAnnotation,
  useUpdateAnnotation,
} from "../../hooks/AnnotationHooks";
import { ServerSpanAnnotation } from "../../types/annotations";
import {
  useDocText,
  useDocxBytes,
  useTextSearchState,
} from "../../context/DocumentAtom";
import DocxAnnotator from "../../renderers/docx/DocxAnnotator";
import { TextSearchSpanResult } from "../../../types";
import {
  useAnnotationControls,
  useAnnotationDisplay,
  useAnnotationSelection,
  useZoomLevel,
} from "../../context/UISettingsAtom";
import { useCorpusState } from "../../context/CorpusAtom";
import { useChatSourceState } from "../../context/ChatSourceAtom";
import {
  registerRefAtom,
  unregisterRefAtom,
} from "../../context/AnnotationRefsAtoms";
import { useReactiveVar } from "@apollo/client";
import { highlightedTextBlock } from "../../../../graphql/cache";
import {
  decodeTextBlock,
  TextSpanBlock,
} from "../../../../utils/textBlockEncoding";
import { useClearTextBlockOnInteraction } from "../../hooks/useClearTextBlockOnInteraction";
import { TEXT_BLOCK_DEEPLINK_ID } from "../../../../assets/configurations/constants";

interface DocxAnnotatorWrapperProps {
  readOnly: boolean;
  allowInput: boolean;
}

const DocxAnnotatorWrapper: React.FC<DocxAnnotatorWrapperProps> = ({
  readOnly,
  allowInput,
}) => {
  const { docText } = useDocText();
  const { docxBytes } = useDocxBytes();
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

  const dispatchRegister = useSetAtom(registerRefAtom);
  const dispatchUnregister = useSetAtom(unregisterRefAtom);

  const handleAnnotationRefChange = useCallback(
    (annotationId: string, element: HTMLElement | null) => {
      if (element) {
        const ref = { current: element };
        dispatchRegister({ type: "annotation", ref, id: annotationId });
      } else {
        dispatchUnregister({ type: "annotation", id: annotationId });
      }
    },
    [dispatchRegister, dispatchUnregister]
  );

  const { messages, selectedMessageId, selectedSourceIndex } =
    useChatSourceState();

  useClearTextBlockOnInteraction(selectedAnnotations, selectedMessageId);

  const textBlockParam = useReactiveVar(highlightedTextBlock);
  const textBlockSpan = React.useMemo(() => {
    if (!textBlockParam) return null;
    const decoded = decodeTextBlock(textBlockParam);
    if (!decoded || decoded.type !== "span") return null;
    return decoded as TextSpanBlock;
  }, [textBlockParam]);

  const chatSourceMatches = React.useMemo(() => {
    const allSources: {
      start_index: number;
      end_index: number;
      sourceId: string;
      messageId: string;
    }[] = [];

    for (const msg of messages) {
      for (const src of msg.sources) {
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

    if (textBlockSpan) {
      allSources.push({
        start_index: textBlockSpan.start,
        end_index: textBlockSpan.end,
        sourceId: TEXT_BLOCK_DEEPLINK_ID,
        messageId: TEXT_BLOCK_DEEPLINK_ID,
      });
    }

    return allSources;
  }, [messages, textBlockSpan]);

  const getSpan = useCallback(
    (span: { start: number; end: number; text: string }) => {
      const selectedLabel = spanLabels.find(
        (label) => label.id === activeSpanLabel?.id
      );
      if (!selectedLabel) throw new Error("Selected label not found");

      return new ServerSpanAnnotation(
        0,
        selectedLabel,
        span.text,
        false,
        { start: span.start, end: span.end },
        [],
        false,
        false
      );
    },
    [spanLabels, activeSpanLabel]
  );

  const filteredAnnotations = useMemo(
    () =>
      pdfAnnotations.annotations.filter(
        (annot): annot is ServerSpanAnnotation =>
          annot instanceof ServerSpanAnnotation
      ),
    [pdfAnnotations.annotations]
  );

  const filteredSearchResults = useMemo(
    () =>
      textSearchMatches?.filter(
        (match): match is TextSearchSpanResult => "start_index" in match
      ) ?? [],
    [textSearchMatches]
  );

  if (!docxBytes || docxBytes.length === 0) {
    return (
      <div
        data-testid="docx-annotator-wrapper-loading"
        style={{ padding: "1rem", textAlign: "center" }}
      >
        Loading DOCX data...
      </div>
    );
  }

  return (
    <div data-testid="docx-annotator-wrapper">
      <DocxAnnotator
        docxBytes={docxBytes}
        docText={docText}
        annotations={filteredAnnotations}
        searchResults={filteredSearchResults}
        chatSources={chatSourceMatches}
        selectedChatSourceId={
          textBlockSpan
            ? TEXT_BLOCK_DEEPLINK_ID
            : selectedMessageId && selectedSourceIndex !== null
            ? `${selectedMessageId}.${selectedSourceIndex}`
            : undefined
        }
        getSpan={getSpan}
        visibleLabels={spanLabelsToView ?? []}
        availableLabels={spanLabels}
        selectedLabelTypeId={activeSpanLabel?.id ?? null}
        readOnly={readOnly}
        allowInput={allowInput}
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
        onAnnotationRefChange={handleAnnotationRefChange}
        zoomLevel={zoomLevel}
      />
    </div>
  );
};

export default React.memo(DocxAnnotatorWrapper);
