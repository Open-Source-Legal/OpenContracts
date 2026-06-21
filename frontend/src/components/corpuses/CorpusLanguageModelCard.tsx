/**
 * CorpusLanguageModelCard — per-corpus LLM ("provider:model") selector.
 *
 * Self-contained settings card extracted from CorpusSettings so its save flow
 * (provider query, mutation, optimistic cache write, rollback) is independently
 * testable. Lets a corpus editor set Corpus.preferred_llm or leave it empty to
 * inherit the install-wide PipelineSettings.default_llm.
 */
import React, { useEffect, useState } from "react";
import { useMutation, useQuery } from "@apollo/client";
import { toast } from "react-toastify";
import { Button } from "@os-legal/ui";

import {
  GET_LLM_PROVIDERS,
  LlmProvidersQueryResult,
  GET_SYSTEM_DEFAULT_LLM,
  SystemDefaultLlmQueryResult,
} from "../../graphql/queries";
import {
  UPDATE_CORPUS,
  UpdateCorpusInputs,
  UpdateCorpusOutputs,
} from "../../graphql/mutations";
import { LlmModelPicker } from "../common/LlmModelPicker";
import {
  SettingsCard,
  SettingsCardHeader,
  SettingsCardTitle,
  SettingsCardContent,
  InfoNote,
} from "./styles/corpusSettingsStyles";

interface CorpusLanguageModelCardProps {
  corpusId: string;
  initialPreferredLlm?: string | null;
  canUpdate: boolean;
}

export const CorpusLanguageModelCard: React.FC<
  CorpusLanguageModelCardProps
> = ({ corpusId, initialPreferredLlm, canUpdate }) => {
  // Per-corpus preferred LLM ("provider:model" spec; "" = inherit the
  // install-wide PipelineSettings.default_llm).
  const [llmDraft, setLlmDraft] = useState<string>(initialPreferredLlm || "");
  const [originalLlm, setOriginalLlm] = useState<string>(
    initialPreferredLlm || ""
  );

  useEffect(() => {
    setLlmDraft(initialPreferredLlm || "");
    setOriginalLlm(initialPreferredLlm || "");
  }, [initialPreferredLlm]);

  // The provider list only powers the interactive model chips, so skip it for
  // read-only viewers; the inherited-default hint still loads via the tiny
  // default-LLM query below. Both resolvers are @login_required and request
  // only non-secret fields, so any corpus editor (not just superusers) can load
  // them.
  const { data: llmProvidersData } = useQuery<LlmProvidersQueryResult>(
    GET_LLM_PROVIDERS,
    { skip: !canUpdate }
  );
  const { data: systemDefaultLlmData } = useQuery<SystemDefaultLlmQueryResult>(
    GET_SYSTEM_DEFAULT_LLM
  );
  // Drop providers an admin has disabled in System Settings so users aren't
  // offered models they can't actually use for this corpus. null/undefined
  // means "not explicitly disabled", so only an explicit `false` is filtered.
  const llmProviders = (
    llmProvidersData?.pipelineComponents?.llmProviders ?? []
  ).filter((p) => p.enabled !== false);
  const systemDefaultLlm =
    systemDefaultLlmData?.pipelineSettings?.defaultLlm ?? "";

  const [updateCorpusLlm, { loading: updatingLlm }] = useMutation<
    UpdateCorpusOutputs,
    UpdateCorpusInputs
  >(UPDATE_CORPUS);

  // Send the empty string to clear (backend normalises "" → NULL = inherit).
  const handleLlmSave = () => {
    // Snapshot the submitted and rollback values up front so the success/error
    // handlers and the cache write all act on what was actually sent — never a
    // draft the user might mutate while the save is in flight.
    const submittedValue = llmDraft.trim();
    const rollbackValue = originalLlm;
    updateCorpusLlm({
      variables: {
        id: corpusId,
        preferredLlm: submittedValue,
      },
      onCompleted: (data) => {
        if (data.updateCorpus?.ok) {
          toast.success("Updated corpus language model");
          setOriginalLlm(submittedValue);
        } else {
          setLlmDraft(rollbackValue);
          toast.error(
            data.updateCorpus?.message || "Failed to update language model"
          );
        }
      },
      onError: (err) => {
        setLlmDraft(rollbackValue);
        toast.error(err.message);
      },
      update: (cache, { data }) => {
        if (data?.updateCorpus?.ok && corpusId) {
          const cacheId = cache.identify({
            __typename: "CorpusType",
            id: corpusId,
          });
          if (cacheId) {
            cache.modify({
              id: cacheId,
              fields: {
                preferredLlm: () => submittedValue || null,
              },
            });
          }
        }
      },
    });
  };

  return (
    <SettingsCard id="corpus-language-model-section">
      <SettingsCardHeader>
        <SettingsCardTitle>Language Model</SettingsCardTitle>
      </SettingsCardHeader>
      <SettingsCardContent>
        <InfoNote>
          Choose which <strong>LLM</strong> this corpus's agents use. Leave it
          empty to <span className="highlight">inherit</span> the system-wide
          default. A per-agent setting still overrides this value, and an
          explicit per-call model wins over everything.
        </InfoNote>
        <LlmModelPicker
          id={`corpus-llm-${corpusId}`}
          value={llmDraft}
          onChange={setLlmDraft}
          providers={llmProviders}
          disabled={!canUpdate || updatingLlm}
          showApiKeyBadge
          inheritedSpec={systemDefaultLlm || null}
          inheritedLabel="Inherited system default"
          placeholder="e.g., anthropic:claude-opus-4-6"
          helperText={'pydantic-ai model spec in "provider:model" form.'}
        />
        {canUpdate && (
          <div style={{ marginTop: "1rem", display: "flex", gap: "0.5rem" }}>
            <Button
              variant="primary"
              onClick={handleLlmSave}
              loading={updatingLlm}
              disabled={llmDraft.trim() === originalLlm.trim()}
            >
              Save
            </Button>
            {llmDraft.trim() !== "" && (
              <Button
                variant="secondary"
                onClick={() => setLlmDraft("")}
                disabled={updatingLlm}
              >
                Clear (use default)
              </Button>
            )}
          </div>
        )}
      </SettingsCardContent>
    </SettingsCard>
  );
};

export default CorpusLanguageModelCard;
