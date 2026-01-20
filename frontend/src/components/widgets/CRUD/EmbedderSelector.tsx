import { useQuery } from "@apollo/client";
import { Header, Dropdown } from "semantic-ui-react";
import { Alert } from "@os-legal/ui";
import styled from "styled-components";
import {
  GetEmbeddersInput,
  GetEmbeddersOutput,
  GET_EMBEDDERS,
} from "../../../graphql/queries";
import { PipelineComponentType } from "../../../types/graphql-api";

// Mobile-responsive wrapper for EmbedderSelector
const MobileFriendlyWrapper = styled.div`
  width: 100%;

  @media (max-width: 768px) {
    /* Ensure dropdown has adequate touch target size */
    .ui.dropdown {
      min-height: 44px; /* iOS minimum touch target */
      font-size: 16px; /* Prevents iOS zoom on focus */
    }

    /* Make header text readable on mobile */
    h5.ui.header {
      font-size: 1rem;
      padding: 0.75rem 1rem;
    }

    /* Ensure dropdown options are large enough to tap */
    .ui.dropdown .menu > .item {
      padding: 0.875rem 1rem !important;
      min-height: 44px;
    }
  }
`;

const AttachedContainer = styled.div`
  padding: 1rem;
  background: #fff;
  border: 1px solid rgba(34, 36, 38, 0.15);
  border-top: none;
  border-radius: 0 0 0.28571429rem 0.28571429rem;
`;

interface EmbedderSelectorProps {
  read_only?: boolean;
  preferredEmbedder?: string;
  style?: Record<string, any>;
  onChange?: (values: any) => void;
  /** Open dropdown upward (useful when near bottom of container) */
  upward?: boolean;
  /** Enable scrolling within the dropdown menu */
  scrolling?: boolean;
}

/**
 * EmbedderSelector component displays a dropdown of available embedders
 * and allows the user to select a preferred embedder for a corpus.
 *
 * When an embedder is selected, it updates the preferredEmbedder property
 * with the className of the selected embedder.
 */
export const EmbedderSelector = ({
  onChange,
  read_only,
  style,
  preferredEmbedder,
  upward = false,
  scrolling = true,
}: EmbedderSelectorProps) => {
  // Use cache-first policy since embedders rarely change during a user session
  // (they are configured by admins and typically require app restart to add new ones).
  // This prevents slow loading when reopening the modal repeatedly.
  // Cache invalidation: The cache is refreshed on page reload, which is sufficient
  // for the rare case when new embedders are added to the system.
  const { loading, error, data } = useQuery<
    GetEmbeddersOutput,
    GetEmbeddersInput
  >(GET_EMBEDDERS, {
    fetchPolicy: "cache-first",
    nextFetchPolicy: "cache-first",
  });

  const handleChange = (_e: any, { value }: any) => {
    // If user has not actually changed the embedder, do nothing
    if (value === preferredEmbedder) return;

    // If user explicitly clears, value === undefined => preferredEmbedder null
    // Otherwise preferredEmbedder is the new value (the className)
    onChange?.({ preferredEmbedder: value ?? null });
  };

  const embedders = data?.pipelineComponents?.embedders || [];
  const hasEmbedders = embedders.length > 0;

  const options = embedders.map((embedder: PipelineComponentType) => ({
    key: embedder.className,
    text: embedder.title || embedder.name,
    value: embedder.className,
    content: (
      <Header
        image={embedder.author ? undefined : undefined} // Could add an icon based on author if needed
        content={embedder.title || embedder.name}
        subheader={`${embedder.description || ""} (${
          embedder.vectorSize || "Unknown"
        } dimensions)`}
      />
    ),
  }));

  return (
    <MobileFriendlyWrapper>
      <Header as="h5" attached="top">
        Preferred Embedder:
      </Header>
      <AttachedContainer>
        {error && (
          <Alert variant="error" title="Failed to load embedders">
            {error.message}
          </Alert>
        )}

        {!loading && !error && !hasEmbedders && (
          <Alert variant="info" title="No embedders available">
            There are currently no embedders configured in the system.
          </Alert>
        )}

        <Dropdown
          disabled={read_only || (!loading && !hasEmbedders)}
          selection
          clearable
          fluid
          upward={upward}
          scrolling={scrolling}
          options={options}
          style={{ ...style }}
          onChange={handleChange}
          placeholder={
            loading ? "Loading embedders..." : "Choose a preferred embedder"
          }
          value={preferredEmbedder}
          noResultsMessage="No embedders match your search"
          loading={loading}
        />
      </AttachedContainer>
    </MobileFriendlyWrapper>
  );
};
