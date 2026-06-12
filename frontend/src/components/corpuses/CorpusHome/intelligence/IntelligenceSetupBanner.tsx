import React, { useCallback, useState } from "react";
import { useMutation, useQuery } from "@apollo/client";
import styled, { keyframes } from "styled-components";
import { Loader2, Sparkles } from "lucide-react";
import { toast } from "react-toastify";

import { OS_LEGAL_COLORS } from "../../../../assets/configurations/osLegalStyles";
import {
  GET_CORPUS_INTELLIGENCE_SETUP_STATUS,
  GetCorpusIntelligenceSetupStatusInputType,
  GetCorpusIntelligenceSetupStatusOutputType,
} from "../../../../graphql/queries";
import {
  SETUP_CORPUS_INTELLIGENCE,
  SetupCorpusIntelligenceInputs,
  SetupCorpusIntelligenceOutputs,
} from "../../../../graphql/mutations";

/**
 * IntelligenceSetupBanner — the one-click "set up collection intelligence"
 * entry point.
 *
 * Renders a slim call-to-action when the corpus is missing pieces of the
 * default intelligence bundle (reference-web action, document descriptions,
 * document summaries) and nothing at all once the bundle is installed —
 * a fully set-up corpus shouldn't advertise setup. Mounted inside
 * ``IntelligencePanel`` so every surface that shows the at-a-glance panel
 * (intelligence overview and the ``insight-panel`` CAML embed) gets it.
 *
 * The mutation is idempotent server-side: it installs whatever is missing,
 * starts the first reference weave, and batch-runs the description/summary
 * agents over every document already in the corpus.
 */

interface IntelligenceSetupBannerProps {
  corpusId: string;
  testId?: string;
}

const spin = keyframes`
  to { transform: rotate(360deg); }
`;

const Banner = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.75rem;
  padding: 0.85rem 1.25rem;
  background: linear-gradient(
    100deg,
    rgba(37, 99, 235, 0.06),
    rgba(201, 164, 92, 0.08)
  );
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 14px;
`;

const BannerText = styled.div`
  display: flex;
  align-items: center;
  gap: 0.6rem;
  font-size: 0.8125rem;
  color: ${OS_LEGAL_COLORS.textSecondary};

  svg {
    flex-shrink: 0;
    width: 16px;
    height: 16px;
    color: ${OS_LEGAL_COLORS.primaryBlue};
  }

  strong {
    color: ${OS_LEGAL_COLORS.textPrimary};
    font-weight: 600;
  }
`;

const SetupButton = styled.button`
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  padding: 0.5rem 1rem;
  border: none;
  border-radius: 10px;
  background: ${OS_LEGAL_COLORS.primaryBlue};
  color: white;
  font-size: 0.8125rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s ease;

  &:hover {
    background: ${OS_LEGAL_COLORS.primaryBlueHover};
  }

  &:disabled {
    opacity: 0.7;
    cursor: default;
  }

  svg {
    width: 14px;
    height: 14px;
  }

  .spinning {
    animation: ${spin} 1.1s linear infinite;
  }
`;

export const IntelligenceSetupBanner: React.FC<
  IntelligenceSetupBannerProps
> = ({ corpusId, testId = "intelligence-setup-banner" }) => {
  const [submitting, setSubmitting] = useState(false);

  const { data, refetch } = useQuery<
    GetCorpusIntelligenceSetupStatusOutputType,
    GetCorpusIntelligenceSetupStatusInputType
  >(GET_CORPUS_INTELLIGENCE_SETUP_STATUS, { variables: { corpusId } });

  const [setupIntelligence] = useMutation<
    SetupCorpusIntelligenceOutputs,
    SetupCorpusIntelligenceInputs
  >(SETUP_CORPUS_INTELLIGENCE);

  const handleSetup = useCallback(async () => {
    setSubmitting(true);
    try {
      const { data: result } = await setupIntelligence({
        variables: { corpusId },
      });
      const payload = result?.setupCorpusIntelligence;
      if (!payload?.ok) {
        toast.error(
          payload?.message || "Couldn't set up collection intelligence."
        );
        return;
      }
      const templates = payload.summary?.templates ?? [];
      const queued = templates.reduce((sum, t) => sum + t.queuedCount, 0);
      const remaining = templates.reduce(
        (sum, t) => sum + (t.remainingCount ?? 0),
        0
      );
      const templateErrors = templates
        .filter((t) => t.error)
        .map((t) => `${t.templateName}: ${t.error}`);
      if (queued > 0) {
        toast.success(
          `Setting up — ${queued} document enrichment ${
            queued === 1 ? "run" : "runs"
          } queued${
            payload.summary?.referenceAnalysisStarted
              ? ", reference web weaving"
              : ""
          }${
            remaining > 0
              ? `; ${remaining} more deferred past the per-run cap — re-run later to continue`
              : ""
          }.`
        );
      } else if (templateErrors.length > 0) {
        // ok=True but nothing queued and a template carried an error — don't
        // claim it's fully set up; surface the actual failures.
        toast.warning(
          "Collection intelligence installed, but some document runs " +
            `couldn't be queued — ${templateErrors.join("; ")}`
        );
      } else {
        toast.success("Collection intelligence is set up.");
      }
      // Status flips to fully-set-up as soon as the actions exist, which
      // hides the banner — the per-surface panels (summary coverage,
      // governance graph) show the enrichment landing as it completes.
      await refetch();
    } catch {
      toast.error("Couldn't set up collection intelligence.");
    } finally {
      setSubmitting(false);
    }
  }, [corpusId, refetch, setupIntelligence]);

  const status = data?.corpusIntelligenceSetupStatus;
  // Silent while loading, on error, once fully set up, and for viewers who
  // can't run setup (canSetup mirrors the mutation's CRUD gate — rendering
  // the CTA for them would offer a guaranteed-to-fail click). The banner
  // only exists to offer setup, never to report state.
  if (!status || status.isFullySetUp || !status.canSetup) return null;

  return (
    <Banner data-testid={testId}>
      <BannerText>
        <Sparkles />
        <span>
          <strong>Set up collection intelligence</strong> — map the reference
          web, then describe and summarize every document automatically.
        </span>
      </BannerText>
      <SetupButton
        onClick={handleSetup}
        disabled={submitting}
        data-testid={`${testId}-button`}
      >
        {submitting ? <Loader2 className="spinning" /> : <Sparkles />}
        Set up
      </SetupButton>
    </Banner>
  );
};
