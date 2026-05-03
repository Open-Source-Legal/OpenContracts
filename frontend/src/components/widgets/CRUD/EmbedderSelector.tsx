import { useQuery } from "@apollo/client";
import { Dropdown } from "@os-legal/ui";
import styled from "styled-components";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";
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
    /* Add padding for better mobile spacing */
    > div:last-child {
      padding: 1rem;
    }
  }
`;

interface EmbedderSelectorProps {
  read_only?: boolean;
  preferredEmbedder?: string;
  style?: Record<string, any>;
  onChange?: (values: any) => void;
  /** Open dropdown upward (useful when near bottom of container) */
  upward?: boolean;
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

  const handleChange = (value: string | null) => {
    // If user has not actually changed the embedder, do nothing
    if (value === preferredEmbedder) return;

    // If user explicitly clears, value === null => preferredEmbedder null
    // Otherwise preferredEmbedder is the new value (the className)
    onChange?.({ preferredEmbedder: value ?? null });
  };

  // Superusers receive every registered embedder from the backend regardless
  // of PipelineSettings.enabled_components, so filter the disabled ones out
  // client-side to match what the rest of the system will actually accept.
  const embedders = (data?.pipelineComponents?.embedders || []).filter(
    (embedder: PipelineComponentType) => embedder.enabled !== false
  );
  const hasEmbedders = embedders.length > 0;

  const options = embedders.map((embedder: PipelineComponentType) => ({
    value: embedder.className || "",
    label: embedder.title || embedder.name || "",
    description: `${embedder.description || ""} (${
      embedder.vectorSize || "Unknown"
    } dimensions)`,
  }));

  return (
    <MobileFriendlyWrapper>
      <h5
        style={{
          margin: 0,
          padding: "0.75rem 1rem",
          background: OS_LEGAL_COLORS.gray50,
          border: "1px solid rgba(34,36,38,.15)",
          borderBottom: "none",
          borderRadius: "4px 4px 0 0",
          fontSize: "0.9rem",
          fontWeight: 600,
        }}
      >
        Preferred Embedder:
      </h5>
      <div
        style={{
          padding: "1rem",
          border: "1px solid rgba(34,36,38,.15)",
          borderRadius: "0 0 4px 4px",
        }}
      >
        {error && (
          <div
            style={{
              background: OS_LEGAL_COLORS.dangerSurface,
              color: OS_LEGAL_COLORS.dangerText,
              border: `1px solid ${OS_LEGAL_COLORS.dangerBorder}`,
              borderRadius: "4px",
              padding: "0.75rem 1rem",
              marginBottom: "0.75rem",
              fontSize: "0.85rem",
            }}
          >
            <div style={{ fontWeight: 700 }}>Failed to load embedders</div>
            <p style={{ margin: "0.25rem 0 0" }}>{error.message}</p>
          </div>
        )}

        {!loading && !error && !hasEmbedders && (
          <div
            style={{
              background: OS_LEGAL_COLORS.infoSurface,
              color: OS_LEGAL_COLORS.infoText,
              border: `1px solid ${OS_LEGAL_COLORS.infoBorder}`,
              borderRadius: "4px",
              padding: "0.75rem 1rem",
              marginBottom: "0.75rem",
              fontSize: "0.85rem",
            }}
          >
            <div style={{ fontWeight: 700 }}>No embedders available</div>
            <p style={{ margin: "0.25rem 0 0" }}>
              There are currently no embedders configured in the system.
            </p>
          </div>
        )}

        <Dropdown
          mode="select"
          disabled={read_only || (!loading && !hasEmbedders)}
          clearable
          fluid
          upward={upward}
          options={options}
          style={{ ...style }}
          onChange={(value) => handleChange(value as string | null)}
          placeholder={
            loading ? "Loading embedders..." : "Choose a preferred embedder"
          }
          value={preferredEmbedder ?? null}
          loading={loading}
        />
      </div>
    </MobileFriendlyWrapper>
  );
};
