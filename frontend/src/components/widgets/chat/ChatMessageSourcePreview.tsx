import React, { useState } from "react";
import { AnimatePresence } from "framer-motion";
import { useAtomValue } from "jotai";
import { Pin, ChevronUp, ChevronDown, Plus } from "lucide-react";

import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";
import { isSpanBasedFileType } from "../../../utils/files";
import { chatSourcesAtom } from "../../annotator/context/ChatSourceAtom";
import { useSelectedDocument } from "../../annotator/context/DocumentAtom";
import {
  ServerTokenAnnotation,
  ServerSpanAnnotation,
} from "../../annotator/types/annotations";
import {
  MultipageAnnotationJson,
  BoundingBox,
  SpanAnnotationJson,
} from "../../types";
import { AnnotationLabelType } from "../../../types/graphql-api";

import {
  AnnotateButton,
  ExpandButton,
  LabelButton,
  LabelMenu,
  SourceChip,
  SourceHeader,
  SourceList,
  SourcePreviewContainer,
  SourcePreviewContent,
  SourcePreviewHeader,
  SourcePreviewTitle,
  SourceText,
  SourceTitle,
} from "./ChatMessageSourcePreview.styles";

interface SourceItemProps {
  messageId: string;
  text: string;
  index: number;
  isSelected: boolean;
  onClick: (e: React.MouseEvent<HTMLDivElement>) => void;
  availableLabels: AnnotationLabelType[];
  createAnnotation: (a: ServerTokenAnnotation | ServerSpanAnnotation) => void;
}

const SourceItem: React.FC<SourceItemProps> = ({
  messageId,
  text,
  index,
  isSelected,
  onClick,
  availableLabels,
  createAnnotation,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [labelMenuOpen, setLabelMenuOpen] = useState(false);

  const chatStateValue = useAtomValue(chatSourcesAtom);
  const { selectedDocument } = useSelectedDocument();

  // UI handlers
  const toggleExpand = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    setIsExpanded(!isExpanded);
  };

  const handleAnnotateClick = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    setLabelMenuOpen((prev) => !prev);
  };

  const handleLabelSelect = (label: AnnotationLabelType) => {
    const msg = chatStateValue.messages.find((m) => m.messageId === messageId);
    if (!msg) return setLabelMenuOpen(false);
    const sourceData = msg.sources[index];
    if (!sourceData) return setLabelMenuOpen(false);

    try {
      if (isSpanBasedFileType(selectedDocument?.fileType)) {
        if (
          sourceData.startIndex === undefined ||
          sourceData.endIndex === undefined
        )
          return setLabelMenuOpen(false);
        const spanJson: SpanAnnotationJson = {
          start: sourceData.startIndex,
          end: sourceData.endIndex,
        };
        const newAnnot = new ServerSpanAnnotation(
          sourceData.page ?? 0,
          label,
          sourceData.rawText,
          false,
          spanJson,
          [],
          false,
          false,
          false
        );
        createAnnotation(newAnnot);
      } else {
        const mpJson: MultipageAnnotationJson = {};
        Object.entries(sourceData.boundsByPage).forEach(([pStr, bounds]) => {
          const pNum = parseInt(pStr, 10);
          mpJson[pNum] = {
            bounds: bounds as BoundingBox,
            tokensJsons: sourceData.tokensByPage[pNum] || [],
            rawText: sourceData.rawText,
          };
        });
        const firstPage = Number(Object.keys(mpJson)[0] || 0);
        const newAnnot = new ServerTokenAnnotation(
          firstPage,
          label,
          sourceData.rawText,
          false,
          mpJson,
          [],
          false,
          false,
          false
        );
        createAnnotation(newAnnot);
      }
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error("Failed to create annotation from source", err);
    } finally {
      setLabelMenuOpen(false);
    }
  };

  return (
    <SourceChip
      $isSelected={isSelected}
      onClick={onClick}
      className="source-chip"
      data-testid="source-chip"
    >
      <SourceHeader>
        <SourceTitle $isSelected={isSelected}>
          <Pin size={12} /> Source {index + 1}
        </SourceTitle>
        <div style={{ display: "flex", gap: "0.25rem" }}>
          <AnnotateButton
            title="Annotate"
            onClick={handleAnnotateClick}
            aria-haspopup="menu"
            aria-expanded={labelMenuOpen}
          >
            <Plus size={14} /> Annotate
          </AnnotateButton>
          <ExpandButton
            $isExpanded={isExpanded}
            onClick={toggleExpand}
            title={isExpanded ? "Show less" : "Show more"}
          >
            {isExpanded ? "Show less" : "Show more"}
            <ChevronDown />
          </ExpandButton>
        </div>
      </SourceHeader>
      {labelMenuOpen && (
        <LabelMenu role="menu" aria-label="Choose label for new annotation">
          {availableLabels.map((lab) => (
            <LabelButton
              key={lab.id}
              role="menuitem"
              onClick={() => handleLabelSelect(lab)}
            >
              <span
                style={{
                  marginRight: 6,
                  width: 8,
                  height: 8,
                  background: lab.color || OS_LEGAL_COLORS.primaryBlueHover,
                  display: "inline-block",
                  borderRadius: 4,
                }}
              />
              {lab.text}
            </LabelButton>
          ))}
        </LabelMenu>
      )}
      <SourceText
        $isExpanded={isExpanded}
        initial={false}
        animate={{ height: isExpanded ? "auto" : "3em" }}
        transition={{ duration: 0.2 }}
      >
        {text}
      </SourceText>
    </SourceChip>
  );
};

export interface SourcePreviewProps {
  messageId: string;
  sources: Array<{ text: string; onClick?: () => void }>;
  selectedIndex?: number;
  onSourceSelect: (index: number) => void;
  availableLabels: AnnotationLabelType[];
  createAnnotation: (a: ServerTokenAnnotation | ServerSpanAnnotation) => void;
}

export const SourcePreview: React.FC<SourcePreviewProps> = ({
  messageId,
  sources,
  selectedIndex,
  onSourceSelect,
  availableLabels,
  createAnnotation,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);

  const handleHeaderClick = (e: React.MouseEvent<HTMLDivElement>) => {
    e.stopPropagation();
    setIsExpanded(!isExpanded);
  };

  return (
    <SourcePreviewContainer
      className="source-preview-container"
      onClick={(e: React.MouseEvent<HTMLDivElement>) => e.stopPropagation()}
    >
      <SourcePreviewHeader onClick={handleHeaderClick}>
        <SourcePreviewTitle>
          <Pin size={14} />
          {sources.length} {sources.length === 1 ? "Source" : "Sources"}
        </SourcePreviewTitle>
        {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </SourcePreviewHeader>
      <AnimatePresence>
        {isExpanded && (
          <SourcePreviewContent
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            <SourceList>
              {sources.map((source, index) => (
                <SourceItem
                  key={`${messageId}-source-${index}`}
                  messageId={messageId}
                  text={source.text}
                  index={index}
                  isSelected={selectedIndex === index}
                  onClick={(e: React.MouseEvent<HTMLDivElement>) => {
                    e.stopPropagation();
                    onSourceSelect(index);
                    source.onClick?.();
                  }}
                  availableLabels={availableLabels}
                  createAnnotation={createAnnotation}
                />
              ))}
            </SourceList>
          </SourcePreviewContent>
        )}
      </AnimatePresence>
    </SourcePreviewContainer>
  );
};
