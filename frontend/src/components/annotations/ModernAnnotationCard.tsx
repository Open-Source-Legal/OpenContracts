import React from "react";
import styled from "styled-components";
import { Avatar } from "@os-legal/ui";
import {
  OS_LEGAL_COLORS,
  accentAlpha,
} from "../../assets/configurations/osLegalStyles";
import {
  FileText,
  User,
  Bot,
  Settings,
  Tag,
  Clock,
  ExternalLink,
  Globe,
  Users,
  Lock,
  AlignLeft,
  Sparkles,
} from "lucide-react";

import { ServerAnnotationType } from "../../types/graphql-api";
import { sanitizeForTooltip } from "../../utils/textSanitization";
import { useAnnotationImages } from "../annotator/hooks/useAnnotationImages";
import { AnnotationImagePreview } from "../annotator/sidebar/AnnotationImagePreview";
import { ModalityBadge } from "../annotator/sidebar/ModalityBadge";

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

export type AnnotationSourceType = "human" | "agent" | "structural";
export type AnnotationVisibilityType = "public" | "shared" | "private";
export type AnnotationLabelTypeFilter = "doc" | "text";

export interface ModernAnnotationCardProps {
  annotation: ServerAnnotationType;
  onClick?: () => void;
  isSelected?: boolean;
  /** Similarity score from semantic search (0.0-1.0, higher is more similar) */
  similarityScore?: number;
}

// ═══════════════════════════════════════════════════════════════════════════════
// STYLED COMPONENTS
// ═══════════════════════════════════════════════════════════════════════════════

const CardContainer = styled.div<{ $isSelected?: boolean }>`
  background: white;
  border: 1px solid
    ${(props) =>
      props.$isSelected ? OS_LEGAL_COLORS.accent : OS_LEGAL_COLORS.border};
  border-radius: 12px;
  padding: 20px;
  transition: all 0.15s ease;
  cursor: pointer;

  ${(props) =>
    props.$isSelected &&
    `
    box-shadow: 0 0 0 2px ${OS_LEGAL_COLORS.accentMedium};
    background: ${OS_LEGAL_COLORS.accentSurface};
  `}

  &:hover {
    border-color: ${(props) =>
      props.$isSelected ? OS_LEGAL_COLORS.accent : OS_LEGAL_COLORS.borderHover};
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.04);
  }
`;

const CardHeader = styled.div`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
`;

const LabelContainer = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
`;

const LabelColor = styled.div<{ $color: string }>`
  width: 12px;
  height: 12px;
  border-radius: 3px;
  flex-shrink: 0;
  background-color: ${(props) => props.$color};
`;

const LabelName = styled.span`
  font-size: 15px;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

const BadgesContainer = styled.div`
  display: flex;
  align-items: center;
  gap: 6px;
`;

const SourceBadge = styled.div<{ $variant: AnnotationSourceType }>`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 6px;
  background: ${(props) => {
    switch (props.$variant) {
      case "human":
        return OS_LEGAL_COLORS.blueBorder;
      case "agent":
        return OS_LEGAL_COLORS.agentPurpleLight;
      case "structural":
        return OS_LEGAL_COLORS.structuralLight;
      default:
        return OS_LEGAL_COLORS.surfaceLight;
    }
  }};
  color: ${(props) => {
    switch (props.$variant) {
      case "human":
        return OS_LEGAL_COLORS.primaryBlueHover;
      case "agent":
        return OS_LEGAL_COLORS.agentPurple;
      case "structural":
        return OS_LEGAL_COLORS.folderIcon;
      default:
        return OS_LEGAL_COLORS.textSecondary;
    }
  }};
`;

const TypeBadge = styled.div<{ $type: "doc" | "text" }>`
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  border-radius: 4px;
  background: ${(props) =>
    props.$type === "doc"
      ? OS_LEGAL_COLORS.blueBorder
      : OS_LEGAL_COLORS.accentSurface};
  color: ${(props) =>
    props.$type === "doc"
      ? OS_LEGAL_COLORS.primaryBlueHover
      : OS_LEGAL_COLORS.accent};
`;

const SimilarityBadge = styled.div<{ $score: number }>`
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  font-size: 11px;
  font-weight: 600;
  border-radius: 4px;
  background: ${(props) => {
    // Color gradient based on score: green for high, yellow for medium, gray for low
    if (props.$score >= 0.8) return OS_LEGAL_COLORS.successSurface; // green
    if (props.$score >= 0.6) return OS_LEGAL_COLORS.yellowLight;
    return OS_LEGAL_COLORS.surfaceLight; // gray
  }};
  color: ${(props) => {
    if (props.$score >= 0.8) return OS_LEGAL_COLORS.successText; // green
    if (props.$score >= 0.6) return OS_LEGAL_COLORS.warningText; // yellow
    return OS_LEGAL_COLORS.textSecondary; // gray
  }};
`;

const LabelsetTag = styled.div`
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  font-size: 11px;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.textSecondary};
  background: ${OS_LEGAL_COLORS.surfaceLight};
  border-radius: 4px;
  margin-bottom: 12px;
`;

const TaggedText = styled.p`
  font-size: 14px;
  line-height: 1.6;
  color: ${OS_LEGAL_COLORS.textTertiary};
  margin-bottom: 16px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
`;

const HighlightedText = styled.span`
  background: linear-gradient(
    to bottom,
    transparent 60%,
    ${accentAlpha(0.15)} 60%
  );
`;

const DocLabelPlaceholder = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  border-radius: 8px;
  margin-bottom: 16px;
  font-size: 13px;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

const CardFooter = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 16px;
  border-top: 1px solid ${OS_LEGAL_COLORS.surfaceLight};
  flex-wrap: wrap;
  gap: 12px;
`;

const DocumentLink = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: ${OS_LEGAL_COLORS.textSecondary};
  text-decoration: none;
  transition: color 0.15s ease;

  &:hover {
    color: ${OS_LEGAL_COLORS.accent};
  }
`;

const DocumentIcon = styled.span`
  color: ${OS_LEGAL_COLORS.textMuted};
  display: flex;
  align-items: center;
`;

const DocumentName = styled.span`
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;

  @media (max-width: 768px) {
    max-width: 120px;
  }
`;

const MetaContainer = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
`;

const CreatorInfo = styled.div`
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

const TimeInfo = styled.div`
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: ${OS_LEGAL_COLORS.textMuted};
`;

const VisibilityIndicator = styled.div<{
  $visibility: AnnotationVisibilityType;
}>`
  display: flex;
  align-items: center;
  justify-content: center;
  color: ${(props) => {
    switch (props.$visibility) {
      case "public":
        return OS_LEGAL_COLORS.greenDark;
      case "shared":
        return OS_LEGAL_COLORS.primaryBlueHover;
      case "private":
        return OS_LEGAL_COLORS.textSecondary;
      default:
        return OS_LEGAL_COLORS.textMuted;
    }
  }};
`;

// ═══════════════════════════════════════════════════════════════════════════════
// HELPER FUNCTIONS
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Determine the source type of an annotation (human, agent, or structural)
 */
export function getAnnotationSource(
  annotation: ServerAnnotationType
): AnnotationSourceType {
  if (annotation.structural) {
    return "structural";
  }

  // Check if it was created by an analyzer (analysis) or a corpus action (agent)
  if (annotation.analysis) {
    const analyzerId =
      annotation.analysis?.analyzer?.analyzerId?.toLowerCase() || "";
    // "manually" in analyzer ID indicates human annotation
    if (analyzerId.includes("manually")) {
      return "human";
    }
    return "agent";
  }

  if (annotation.corpusAction) {
    return "agent";
  }

  // No analysis or corpus action means manually created
  return "human";
}

/**
 * Determine visibility based on annotation properties
 */
export function getAnnotationVisibility(
  annotation: ServerAnnotationType,
  currentUserEmail?: string
): AnnotationVisibilityType {
  if (annotation.isPublic) {
    return "public";
  }

  const isOwner = annotation.creator?.email === currentUserEmail;
  if (isOwner) {
    return "private";
  }

  return "shared";
}

/**
 * Get the label type (doc or text) from annotation
 */
export function getAnnotationLabelType(
  annotation: ServerAnnotationType
): AnnotationLabelTypeFilter {
  // DOC_TYPE_LABEL indicates document-level annotation
  if (annotation.annotationType === "DOC_TYPE_LABEL") {
    return "doc";
  }
  return "text";
}

/**
 * Get initials from a name for avatar fallback
 */
function getInitials(name: string): string {
  const parts = name.split(/[\s._@-]+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) {
    return parts[0].substring(0, 2).toUpperCase();
  }
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/**
 * Format the created date as relative time
 */
function formatRelativeTime(dateString?: string): string {
  if (!dateString) return "";

  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 60) {
    return `${diffMins} ${diffMins === 1 ? "min" : "mins"} ago`;
  } else if (diffHours < 24) {
    return `${diffHours} ${diffHours === 1 ? "hour" : "hours"} ago`;
  } else if (diffDays < 7) {
    return `${diffDays} ${diffDays === 1 ? "day" : "days"} ago`;
  } else {
    return date.toLocaleDateString();
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// SUBCOMPONENTS
// ═══════════════════════════════════════════════════════════════════════════════

const SourceBadgeComponent: React.FC<{ source: AnnotationSourceType }> = ({
  source,
}) => {
  const config = {
    human: { icon: <User size={14} />, title: "Human annotated" },
    agent: { icon: <Bot size={14} />, title: "AI annotated" },
    structural: { icon: <Settings size={14} />, title: "Structural" },
  };

  const { icon, title } = config[source];

  return (
    <SourceBadge $variant={source} title={title}>
      {icon}
    </SourceBadge>
  );
};

const VisibilityIconComponent: React.FC<{
  visibility: AnnotationVisibilityType;
}> = ({ visibility }) => {
  const config = {
    public: { icon: <Globe size={14} />, title: "Public" },
    shared: { icon: <Users size={14} />, title: "Shared" },
    private: { icon: <Lock size={14} />, title: "Private" },
  };

  const { icon, title } = config[visibility];

  return (
    <VisibilityIndicator $visibility={visibility} title={title}>
      {icon}
    </VisibilityIndicator>
  );
};

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export const ModernAnnotationCard: React.FC<ModernAnnotationCardProps> = ({
  annotation,
  onClick,
  isSelected = false,
  similarityScore,
}) => {
  const source = getAnnotationSource(annotation);
  const labelType = getAnnotationLabelType(annotation);
  const visibility = getAnnotationVisibility(annotation);

  // Get content modalities for image display
  const contentModalities = annotation.contentModalities || [];
  const hasImageModality = contentModalities.includes("IMAGE");
  const hasTextModality = contentModalities.includes("TEXT");

  // Fetch images if annotation has IMAGE modality
  const {
    images,
    loading: imagesLoading,
    error: imagesError,
    hasFetchedEmpty: imagesEmpty,
  } = useAnnotationImages(annotation.id, contentModalities);

  const labelColor =
    annotation.annotationLabel?.color || OS_LEGAL_COLORS.textMuted;
  const labelName = annotation.annotationLabel?.text || "Unknown Label";
  const creatorName =
    annotation.creator?.email?.split("@")[0] ||
    annotation.creator?.username ||
    "Unknown";
  const documentName = annotation.document?.title || "Unknown Document";

  // Get labelset name from the corpus if available
  const labelsetName = annotation.corpus?.labelSet?.title || "Annotations";

  const hasText = annotation.rawText && annotation.rawText.trim() !== "";

  return (
    <CardContainer $isSelected={isSelected} onClick={onClick}>
      <CardHeader>
        <LabelContainer>
          <LabelColor $color={labelColor} />
          <LabelName>{labelName}</LabelName>
        </LabelContainer>
        <BadgesContainer>
          {similarityScore !== undefined && (
            <SimilarityBadge
              $score={similarityScore}
              title={`${Math.round(similarityScore * 100)}% semantic match`}
            >
              <Sparkles size={12} />
              {Math.round(similarityScore * 100)}%
            </SimilarityBadge>
          )}
          <SourceBadgeComponent source={source} />
          <ModalityBadge modalities={contentModalities} />
          <TypeBadge $type={labelType}>
            {labelType === "doc" ? (
              <>
                <FileText size={12} /> Doc
              </>
            ) : (
              <>
                <AlignLeft size={12} /> Text
              </>
            )}
          </TypeBadge>
        </BadgesContainer>
      </CardHeader>

      <LabelsetTag>
        <Tag size={12} /> {labelsetName}
      </LabelsetTag>

      {/* Content display based on modality */}
      {(() => {
        // IMAGE modality - show featured image first
        if (hasImageModality) {
          return (
            <>
              <AnnotationImagePreview
                images={images}
                loading={imagesLoading}
                error={imagesError}
                hasFetchedEmpty={imagesEmpty}
                compact={false}
              />
              {/* Show text below image if mixed content */}
              {hasTextModality && hasText && (
                <TaggedText style={{ marginTop: "0.5rem" }}>
                  <HighlightedText>
                    {sanitizeForTooltip(
                      annotation.rawText!.length > 100
                        ? `${annotation.rawText!.substring(0, 100)}...`
                        : annotation.rawText!
                    )}
                  </HighlightedText>
                </TaggedText>
              )}
            </>
          );
        }

        // TEXT only modality or doc label
        if (labelType === "text" && hasText) {
          return (
            <TaggedText>
              <HighlightedText>
                {sanitizeForTooltip(
                  annotation.rawText!.length > 150
                    ? `${annotation.rawText!.substring(0, 150)}...`
                    : annotation.rawText!
                )}
              </HighlightedText>
            </TaggedText>
          );
        }

        // Doc label placeholder
        return (
          <DocLabelPlaceholder>
            <FileText size={16} color={OS_LEGAL_COLORS.primaryBlueHover} />
            Applies to entire document
          </DocLabelPlaceholder>
        );
      })()}

      <CardFooter>
        <DocumentLink>
          <DocumentIcon>
            <FileText size={14} />
          </DocumentIcon>
          <DocumentName title={documentName}>{documentName}</DocumentName>
          <ExternalLink size={12} />
        </DocumentLink>
        <MetaContainer>
          <CreatorInfo>
            <Avatar fallback={getInitials(creatorName)} size="xs" />
            {creatorName}
          </CreatorInfo>
          {annotation.created && (
            <TimeInfo>
              <Clock size={12} />
              {formatRelativeTime(annotation.created)}
            </TimeInfo>
          )}
          <VisibilityIconComponent visibility={visibility} />
        </MetaContainer>
      </CardFooter>
    </CardContainer>
  );
};

export default ModernAnnotationCard;
