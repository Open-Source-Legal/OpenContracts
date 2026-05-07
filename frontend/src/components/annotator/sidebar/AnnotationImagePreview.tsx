import React, { useState } from "react";
import styled, { keyframes } from "styled-components";
import { Loader, Image as ImageIcon } from "lucide-react";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";

interface ContainerProps {
  $compact?: boolean;
}

const PreviewContainer = styled.div<ContainerProps>`
  margin: 0.75rem 0;
  display: flex;
  flex-wrap: wrap;
  gap: ${(props) => (props.$compact ? "0.5rem" : "0.75rem")};
`;

interface ThumbnailProps {
  $compact?: boolean;
}

const ThumbnailWrapper = styled.div<ThumbnailProps>`
  position: relative;
  width: ${(props) => (props.$compact ? "56px" : "100%")};
  height: ${(props) => (props.$compact ? "56px" : "auto")};
  min-height: ${(props) => (props.$compact ? "56px" : "120px")};
  max-height: ${(props) => (props.$compact ? "56px" : "200px")};
  border-radius: 8px;
  overflow: hidden;
  border: 2px solid ${OS_LEGAL_COLORS.border};
  cursor: pointer;
  transition: all 0.2s ease;
  background: ${OS_LEGAL_COLORS.surfaceLight};

  &:hover {
    border-color: ${OS_LEGAL_COLORS.primaryBlue};
    box-shadow: 0 4px 12px rgba(59, 130, 246, 0.2);
  }
`;

interface ThumbnailImageProps {
  $compact?: boolean;
  $loaded?: boolean;
}

const Thumbnail = styled.img<ThumbnailImageProps>`
  width: 100%;
  height: 100%;
  object-fit: ${(props) => (props.$compact ? "cover" : "contain")};
  display: block;
  opacity: ${(props) => (props.$loaded ? 1 : 0)};
  transition: opacity 0.3s ease;
`;

// Shimmer animation for loading placeholder
const shimmer = keyframes`
  0% {
    background-position: -200% 0;
  }
  100% {
    background-position: 200% 0;
  }
`;

const ImagePlaceholder = styled.div<ThumbnailProps>`
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 0.5rem;
  background: linear-gradient(
    90deg,
    ${OS_LEGAL_COLORS.surfaceLight} 0%,
    ${OS_LEGAL_COLORS.border} 20%,
    ${OS_LEGAL_COLORS.surfaceHover} 40%,
    ${OS_LEGAL_COLORS.border} 60%,
    ${OS_LEGAL_COLORS.surfaceLight} 100%
  );
  background-size: 200% 100%;
  animation: ${shimmer} 1.5s ease-in-out infinite;
  color: ${OS_LEGAL_COLORS.textMuted};
`;

const LoadingState = styled.div<ThumbnailProps>`
  display: flex;
  align-items: center;
  justify-content: center;
  width: ${(props) => (props.$compact ? "56px" : "100%")};
  height: ${(props) => (props.$compact ? "56px" : "120px")};
  background: ${OS_LEGAL_COLORS.surfaceLight};
  border-radius: 8px;
  border: 2px solid ${OS_LEGAL_COLORS.border};
  color: ${OS_LEGAL_COLORS.textMuted};
`;

const ErrorState = styled(LoadingState)`
  flex-direction: column;
  gap: 0.25rem;
  font-size: 0.75rem;
`;

const NoThumbnailState = styled(LoadingState)`
  flex-direction: column;
  gap: 0.25rem;
  font-size: 0.75rem;
  color: ${OS_LEGAL_COLORS.textMuted};
  background: ${OS_LEGAL_COLORS.surfaceHover};
  border-style: dashed;
`;

const ImageCount = styled.span`
  position: absolute;
  bottom: 6px;
  right: 6px;
  background: rgba(0, 0, 0, 0.6);
  color: white;
  font-size: 0.7rem;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 500;
  z-index: 1;
`;

interface ImageData {
  base64_data: string;
  format: string;
  data_url: string;
  page_index: number;
  token_index: number;
}

interface AnnotationImagePreviewProps {
  images: ImageData[] | null;
  loading: boolean;
  error: boolean;
  /**
   * True when the request completed successfully but no thumbnail is available.
   * Renders a neutral placeholder instead of the alarming "Failed" error state.
   */
  hasFetchedEmpty?: boolean;
  compact?: boolean;
  onImageClick?: (image: ImageData) => void;
}

interface ImageWithPlaceholderProps {
  image: ImageData;
  compact: boolean;
  onClick?: () => void;
  alt: string;
  imageCount?: number;
}

/**
 * Individual image with loading placeholder and optional count badge
 */
const ImageWithPlaceholder: React.FC<ImageWithPlaceholderProps> = ({
  image,
  compact,
  onClick,
  alt,
  imageCount,
}) => {
  const [loaded, setLoaded] = useState(false);

  return (
    <ThumbnailWrapper
      $compact={compact}
      onClick={onClick}
      title={`Page ${image.page_index + 1}`}
    >
      {!loaded && (
        <ImagePlaceholder $compact={compact}>
          <ImageIcon size={compact ? 16 : 24} />
        </ImagePlaceholder>
      )}
      <Thumbnail
        $compact={compact}
        $loaded={loaded}
        src={image.data_url}
        alt={alt}
        loading="lazy"
        onLoad={() => setLoaded(true)}
      />
      {imageCount && <ImageCount>{imageCount} images</ImageCount>}
    </ThumbnailWrapper>
  );
};

export const AnnotationImagePreview: React.FC<AnnotationImagePreviewProps> = ({
  images,
  loading,
  error,
  hasFetchedEmpty = false,
  compact = false,
  onImageClick,
}) => {
  if (loading) {
    return (
      <PreviewContainer $compact={compact}>
        <LoadingState $compact={compact}>
          <Loader size={compact ? 16 : 20} className="spinner" />
        </LoadingState>
      </PreviewContainer>
    );
  }

  if (error) {
    return (
      <PreviewContainer $compact={compact}>
        <ErrorState $compact={compact}>
          <ImageIcon size={compact ? 16 : 20} />
          {!compact && <span>Failed</span>}
        </ErrorState>
      </PreviewContainer>
    );
  }

  // Pre-fetch state (effect hasn't run yet): render nothing so we don't flash
  // the "No thumbnail" placeholder before the loading spinner appears.
  if (images === null) {
    return null;
  }

  // Fetch succeeded but no thumbnail available — show a neutral placeholder so
  // the card still indicates this is an image annotation rather than rendering
  // nothing (or worse, the old "Failed" state from issue #1560).
  if (hasFetchedEmpty || images.length === 0) {
    return (
      <PreviewContainer $compact={compact}>
        <NoThumbnailState
          $compact={compact}
          title="No thumbnail generated for this annotation"
        >
          <ImageIcon size={compact ? 16 : 20} />
          {!compact && <span>No thumbnail</span>}
        </NoThumbnailState>
      </PreviewContainer>
    );
  }

  // For featured mode (non-compact), show first image large with count badge
  // For compact mode, show all as small thumbnails
  if (!compact) {
    const firstImage = images[0];
    return (
      <PreviewContainer $compact={false}>
        <ImageWithPlaceholder
          image={firstImage}
          compact={false}
          onClick={() => onImageClick?.(firstImage)}
          alt="Annotation image"
          imageCount={images.length > 1 ? images.length : undefined}
        />
      </PreviewContainer>
    );
  }

  // Compact mode - show all as small thumbnails
  return (
    <PreviewContainer $compact={true}>
      {images.map((image, index) => (
        <ImageWithPlaceholder
          key={`${image.page_index}-${image.token_index}`}
          image={image}
          compact={true}
          onClick={() => onImageClick?.(image)}
          alt={`Annotation image ${index + 1}`}
        />
      ))}
    </PreviewContainer>
  );
};
