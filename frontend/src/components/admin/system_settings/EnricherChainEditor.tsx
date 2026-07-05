import React, { memo, useMemo, useCallback, useState } from "react";
import { Button, IconButton, Spinner } from "@os-legal/ui";
import { ListOrdered, ArrowUp, ArrowDown, X, Plus } from "lucide-react";
import {
  PipelineComponentType,
  SupportedMimeTypeType,
} from "../../../types/graphql-api";
import { getComponentDisplayName } from "../PipelineIcons";
import { PreferredEnrichersMap } from "./types";
import { appendToChain, isComponentAvailable, reorderChain } from "./utils";
import {
  Section,
  SectionHeader,
  SectionTitle,
  EmptyValue,
  ComponentName,
  DefaultEmbedderPath,
  FiletypeRow,
  EnricherMimeBlock,
  EnricherMimeHeader,
  EnricherOrderedList,
  EnricherListItem,
  EnricherOrderBadge,
  EnricherItemInfo,
  EnricherItemActions,
  EnricherAddRow,
  StyledSelect,
} from "./styles";

// ============================================================================
// Types
// ============================================================================

interface EnricherChainEditorProps {
  /** All registered enrichers, keyed for lookup by className. */
  enrichers: (PipelineComponentType & { className: string })[];
  supportedMimeTypes: SupportedMimeTypeType[];
  mimeTypesLoading?: boolean;
  enabledComponents: string[];
  /** Mapping of MIME type -> ordered list of enricher class paths. */
  preferredEnrichers: PreferredEnrichersMap;
  updating: boolean;
  /** Persists the FULL updated chain for a single MIME type. */
  onAssignEnrichers: (mimeType: string, enricherPaths: string[]) => void;
}

// ============================================================================
// Component
// ============================================================================

/**
 * Per-MIME-type editor for the `preferred_enrichers` enrichment chain
 * (issue #2118). Unlike Parser/Thumbnailer (a single class path per MIME
 * type, rendered via `STAGE_CONFIG`/`<select>`), enrichers run as an ORDERED
 * LIST — so this is a dedicated component rather than an extra `StageType`
 * entry: each row needs add/remove/reorder controls, not just a dropdown.
 */
export const EnricherChainEditor = memo<EnricherChainEditorProps>(
  ({
    enrichers,
    supportedMimeTypes,
    mimeTypesLoading,
    enabledComponents,
    preferredEnrichers,
    updating,
    onAssignEnrichers,
  }) => {
    // Pending "about to add" selection per MIME type, keyed by mimetype.
    // Local to the editor — cleared once the Add button commits it via
    // onAssignEnrichers.
    const [pendingSelection, setPendingSelection] = useState<
      Record<string, string>
    >({});

    const enricherByClassName = useMemo(() => {
      const map = new Map<
        string,
        PipelineComponentType & { className: string }
      >();
      for (const enricher of enrichers) {
        map.set(enricher.className, enricher);
      }
      return map;
    }, [enrichers]);

    const getChain = useCallback(
      (mimeType: string): string[] =>
        (preferredEnrichers[mimeType] || []).filter(Boolean),
      [preferredEnrichers]
    );

    const handleMove = useCallback(
      (mimeType: string, index: number, direction: -1 | 1) => {
        const chain = getChain(mimeType);
        onAssignEnrichers(mimeType, reorderChain(chain, index, direction));
      },
      [getChain, onAssignEnrichers]
    );

    const handleRemove = useCallback(
      (mimeType: string, index: number) => {
        const chain = getChain(mimeType).filter((_, i) => i !== index);
        onAssignEnrichers(mimeType, chain);
      },
      [getChain, onAssignEnrichers]
    );

    const handleAdd = useCallback(
      (mimeType: string) => {
        const chain = getChain(mimeType);
        onAssignEnrichers(
          mimeType,
          appendToChain(chain, pendingSelection[mimeType])
        );
        setPendingSelection((prev) => ({ ...prev, [mimeType]: "" }));
      },
      [getChain, onAssignEnrichers, pendingSelection]
    );

    return (
      <Section data-testid="enricher-chain-editor">
        <SectionHeader>
          <SectionTitle>
            <ListOrdered />
            Enrichment Chains
          </SectionTitle>
        </SectionHeader>

        {mimeTypesLoading && supportedMimeTypes.length === 0 ? (
          <FiletypeRow>
            <div
              style={{
                gridColumn: "1 / -1",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "0.5rem",
                padding: "1rem",
              }}
            >
              <Spinner size="sm" />
              <span>Loading file types...</span>
            </div>
          </FiletypeRow>
        ) : null}

        {supportedMimeTypes.map((mime) => {
          const shortLabel = mime.fileType.toUpperCase();
          const chain = getChain(mime.mimetype);
          const available = enrichers.filter(
            (enricher) =>
              isComponentAvailable(enricher, shortLabel, enabledComponents) &&
              !chain.includes(enricher.className)
          );

          return (
            <EnricherMimeBlock key={mime.mimetype}>
              <EnricherMimeHeader>{mime.label}</EnricherMimeHeader>

              {chain.length === 0 ? (
                <EmptyValue>No enrichers configured</EmptyValue>
              ) : (
                <EnricherOrderedList>
                  {chain.map((className, index) => {
                    const enricher = enricherByClassName.get(className);
                    return (
                      <EnricherListItem key={`${className}-${index}`}>
                        <EnricherOrderBadge>{index + 1}</EnricherOrderBadge>
                        <EnricherItemInfo>
                          <ComponentName>
                            {getComponentDisplayName(
                              className,
                              enricher?.title || undefined
                            )}
                          </ComponentName>
                          <DefaultEmbedderPath>{className}</DefaultEmbedderPath>
                        </EnricherItemInfo>
                        <EnricherItemActions>
                          <IconButton
                            aria-label={`Move ${mime.label} enricher ${
                              index + 1
                            } up`}
                            variant="ghost"
                            size="sm"
                            disabled={updating || index === 0}
                            onClick={() => handleMove(mime.mimetype, index, -1)}
                          >
                            <ArrowUp />
                          </IconButton>
                          <IconButton
                            aria-label={`Move ${mime.label} enricher ${
                              index + 1
                            } down`}
                            variant="ghost"
                            size="sm"
                            disabled={updating || index === chain.length - 1}
                            onClick={() => handleMove(mime.mimetype, index, 1)}
                          >
                            <ArrowDown />
                          </IconButton>
                          <IconButton
                            aria-label={`Remove ${mime.label} enricher ${
                              index + 1
                            }`}
                            variant="ghost"
                            size="sm"
                            disabled={updating}
                            onClick={() => handleRemove(mime.mimetype, index)}
                          >
                            <X />
                          </IconButton>
                        </EnricherItemActions>
                      </EnricherListItem>
                    );
                  })}
                </EnricherOrderedList>
              )}

              <EnricherAddRow>
                <StyledSelect
                  aria-label={`Add enricher for ${mime.label} files`}
                  style={{ flex: 1 }}
                  disabled={updating || available.length === 0}
                  value={pendingSelection[mime.mimetype] || ""}
                  onChange={(e) =>
                    setPendingSelection((prev) => ({
                      ...prev,
                      [mime.mimetype]: e.target.value,
                    }))
                  }
                >
                  <option value="">
                    {available.length === 0
                      ? "No more enrichers available"
                      : "-- Select enricher --"}
                  </option>
                  {available.map((enricher) => (
                    <option key={enricher.className} value={enricher.className}>
                      {getComponentDisplayName(
                        enricher.className,
                        enricher.title || undefined
                      )}
                    </option>
                  ))}
                </StyledSelect>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={updating || !pendingSelection[mime.mimetype]}
                  onClick={() => handleAdd(mime.mimetype)}
                  aria-label={`Add enricher to ${mime.label} chain`}
                >
                  <Plus style={{ width: 14, height: 14, marginRight: 4 }} />
                  Add
                </Button>
              </EnricherAddRow>
            </EnricherMimeBlock>
          );
        })}
      </Section>
    );
  }
);

EnricherChainEditor.displayName = "EnricherChainEditor";
