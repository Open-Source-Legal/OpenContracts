import React from "react";
import { useMutation } from "@apollo/client";
import styled from "styled-components";
import { toast } from "react-toastify";
import {
  AlertTriangle,
  CheckCircle2,
  FileSearch,
  FileText,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { Button } from "@os-legal/ui";
import {
  OS_LEGAL_COLORS,
  OS_LEGAL_TYPOGRAPHY,
} from "../../../../assets/configurations/osLegalStyles";
import {
  LegalReviewFinding,
  RUN_LEGAL_REVIEW,
  RunLegalReviewInputs,
  RunLegalReviewOutputs,
} from "../../../../graphql/mutations";
import {
  FlexColumnPanel,
  ScrollableFillPanel,
  SidebarHeader,
  SidebarHeaderContent,
  SidebarHeaderSubtitle,
  SidebarHeaderTitle,
} from "./styles";

interface LegalReviewPanelProps {
  readOnly: boolean;
  documentId: string;
  corpusId?: string;
}

const PanelBody = styled(ScrollableFillPanel)`
  padding: 16px;
  background: ${OS_LEGAL_COLORS.surface};
`;

const ActionBand = styled.div`
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 8px;
  padding: 14px;
  background: ${OS_LEGAL_COLORS.surfaceHover};
`;

const ActionHeader = styled.div`
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 12px;
`;

const ActionIcon = styled.div`
  width: 34px;
  height: 34px;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: ${OS_LEGAL_COLORS.accentSurface};
  color: ${OS_LEGAL_COLORS.accent};
  flex: 0 0 auto;
`;

const ActionTitle = styled.h3`
  margin: 0;
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 14px;
  font-weight: 650;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

const ActionText = styled.p`
  margin: 3px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

const ReviewButton = styled(Button)`
  width: 100%;
  justify-content: center;
`;

const StatusText = styled.div<{ $tone?: "error" | "success" | "neutral" }>`
  margin-top: 10px;
  font-size: 12px;
  line-height: 1.5;
  color: ${(props) =>
    props.$tone === "error"
      ? OS_LEGAL_COLORS.dangerText
      : props.$tone === "success"
      ? OS_LEGAL_COLORS.successText
      : OS_LEGAL_COLORS.textSecondary};
`;

const SectionTitle = styled.h4`
  margin: 18px 0 10px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: ${OS_LEGAL_COLORS.textMuted};
`;

const Checklist = styled.div`
  display: grid;
  gap: 8px;
`;

const ChecklistItem = styled.div`
  display: flex;
  align-items: flex-start;
  gap: 9px;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 8px;
  padding: 10px;
  background: ${OS_LEGAL_COLORS.surface};
`;

const ChecklistIcon = styled.span<{ $tone: "risk" | "source" | "draft" }>`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 6px;
  color: ${(props) =>
    props.$tone === "risk"
      ? OS_LEGAL_COLORS.warningText
      : props.$tone === "source"
      ? OS_LEGAL_COLORS.primaryBlue
      : OS_LEGAL_COLORS.success};
  background: ${(props) =>
    props.$tone === "risk"
      ? OS_LEGAL_COLORS.warningSurface
      : props.$tone === "source"
      ? OS_LEGAL_COLORS.blueSurface
      : OS_LEGAL_COLORS.successSurface};
  flex: 0 0 auto;
`;

const ChecklistCopy = styled.div`
  min-width: 0;
`;

const ChecklistLabel = styled.div`
  font-size: 13px;
  font-weight: 650;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

const ChecklistDescription = styled.div`
  margin-top: 2px;
  font-size: 12px;
  line-height: 1.45;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

const EmptyResult = styled.div`
  margin-top: 14px;
  border: 1px dashed ${OS_LEGAL_COLORS.border};
  border-radius: 8px;
  padding: 14px;
  text-align: center;
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-size: 12px;
  line-height: 1.5;
  background: ${OS_LEGAL_COLORS.surfaceHover};
`;

const SummaryCard = styled.div`
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 8px;
  padding: 12px;
  background: ${OS_LEGAL_COLORS.surface};
  color: ${OS_LEGAL_COLORS.textPrimary};
  font-size: 13px;
  line-height: 1.5;
`;

const FindingList = styled.div`
  display: grid;
  gap: 10px;
`;

const FindingCard = styled.div`
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 8px;
  padding: 12px;
  background: ${OS_LEGAL_COLORS.surface};
`;

const FindingHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
`;

const FindingTitle = styled.div`
  font-size: 13px;
  font-weight: 650;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

const RiskBadge = styled.span<{ $risk: LegalReviewFinding["riskLevel"] }>`
  padding: 3px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  color: ${(props) =>
    props.$risk === "critical" || props.$risk === "high"
      ? OS_LEGAL_COLORS.dangerText
      : props.$risk === "medium"
      ? OS_LEGAL_COLORS.warningText
      : OS_LEGAL_COLORS.successText};
  background: ${(props) =>
    props.$risk === "critical" || props.$risk === "high"
      ? OS_LEGAL_COLORS.dangerSurface
      : props.$risk === "medium"
      ? OS_LEGAL_COLORS.warningSurface
      : OS_LEGAL_COLORS.successSurface};
  flex: 0 0 auto;
`;

const FindingCopy = styled.div`
  display: grid;
  gap: 7px;
  font-size: 12px;
  line-height: 1.5;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

const Quote = styled.blockquote`
  margin: 2px 0 0;
  padding: 8px 10px;
  border-left: 3px solid ${OS_LEGAL_COLORS.accent};
  background: ${OS_LEGAL_COLORS.accentSurface};
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

const riskLabels: Record<LegalReviewFinding["riskLevel"], string> = {
  low: "Niedrig",
  medium: "Mittel",
  high: "Hoch",
  critical: "Kritisch",
};

export const LegalReviewPanel: React.FC<LegalReviewPanelProps> = ({
  readOnly,
  documentId,
  corpusId,
}) => {
  const [reviewResult, setReviewResult] = React.useState<
    RunLegalReviewOutputs["runLegalReview"] | null
  >(null);

  const [runLegalReview, { loading }] = useMutation<
    RunLegalReviewOutputs,
    RunLegalReviewInputs
  >(RUN_LEGAL_REVIEW, {
    onCompleted: (data) => {
      setReviewResult(data.runLegalReview);
      if (data.runLegalReview.ok) {
        toast.success("Vertragsprüfung abgeschlossen");
      } else {
        toast.error(
          data.runLegalReview.message || "Vertragsprüfung fehlgeschlagen"
        );
      }
    },
    onError: (error) => {
      setReviewResult({
        ok: false,
        message: error.message,
        summary: "",
        findings: [],
        sourceAnnotationIds: [],
      });
      toast.error("Vertragsprüfung fehlgeschlagen");
    },
  });

  const disabledReason = readOnly
    ? "In dieser Ansicht können keine neuen Prüfungen gestartet werden."
    : !corpusId
    ? "Füge das Dokument zuerst einer Akte hinzu, um eine Prüfung zu starten."
    : undefined;

  const canRunReview = !readOnly && !!corpusId && !loading;
  const findings = reviewResult?.findings ?? [];

  const handleRunReview = () => {
    if (!corpusId) return;
    runLegalReview({
      variables: {
        documentId,
        corpusId,
      },
    });
  };

  return (
    <FlexColumnPanel>
      <SidebarHeader>
        <ShieldCheck size={20} style={{ color: OS_LEGAL_COLORS.accent }} />
        <SidebarHeaderContent>
          <SidebarHeaderTitle>Vertragsprüfung</SidebarHeaderTitle>
          <SidebarHeaderSubtitle>
            Risiken, Fundstellen und Empfehlungen
          </SidebarHeaderSubtitle>
        </SidebarHeaderContent>
      </SidebarHeader>

      <PanelBody>
        <ActionBand>
          <ActionHeader>
            <ActionIcon>
              <Sparkles size={18} />
            </ActionIcon>
            <div>
              <ActionTitle>Vertragsreview</ActionTitle>
              <ActionText>
                Prüft Risiken, Fundstellen und Empfehlungen für dieses Dokument.
              </ActionText>
            </div>
          </ActionHeader>
          <ReviewButton
            variant="primary"
            disabled={!canRunReview}
            loading={loading}
            title={disabledReason}
            onClick={handleRunReview}
          >
            {loading ? "Prüfung läuft" : "Prüfung starten"}
          </ReviewButton>
          {disabledReason && (
            <StatusText $tone="neutral">{disabledReason}</StatusText>
          )}
          {reviewResult && !reviewResult.ok && (
            <StatusText $tone="error">{reviewResult.message}</StatusText>
          )}
        </ActionBand>

        <SectionTitle>Prüfpunkte</SectionTitle>
        <Checklist>
          <ChecklistItem>
            <ChecklistIcon $tone="risk">
              <AlertTriangle size={15} />
            </ChecklistIcon>
            <ChecklistCopy>
              <ChecklistLabel>Risikoklauseln erkennen</ChecklistLabel>
              <ChecklistDescription>
                Haftung, Laufzeit, Kündigung, Vertragsstrafen, Pflichten.
              </ChecklistDescription>
            </ChecklistCopy>
          </ChecklistItem>
          <ChecklistItem>
            <ChecklistIcon $tone="source">
              <FileSearch size={15} />
            </ChecklistIcon>
            <ChecklistCopy>
              <ChecklistLabel>Fundstellen belegen</ChecklistLabel>
              <ChecklistDescription>
                Zitierbare Textstellen, Seitenbezug, Quellenanker.
              </ChecklistDescription>
            </ChecklistCopy>
          </ChecklistItem>
          <ChecklistItem>
            <ChecklistIcon $tone="draft">
              <FileText size={15} />
            </ChecklistIcon>
            <ChecklistCopy>
              <ChecklistLabel>Review-Notiz erzeugen</ChecklistLabel>
              <ChecklistDescription>
                Aktennotiz, Prüfliste, Exportvorbereitung.
              </ChecklistDescription>
            </ChecklistCopy>
          </ChecklistItem>
        </Checklist>

        <SectionTitle>Prüfergebnisse</SectionTitle>
        {reviewResult?.ok && reviewResult.summary && (
          <SummaryCard>{reviewResult.summary}</SummaryCard>
        )}
        {findings.length > 0 ? (
          <FindingList>
            {findings.map((finding, index) => (
              <FindingCard key={`${finding.clauseType}-${index}`}>
                <FindingHeader>
                  <FindingTitle>{finding.clauseType || "Finding"}</FindingTitle>
                  <RiskBadge $risk={finding.riskLevel}>
                    {riskLabels[finding.riskLevel] ?? finding.riskLevel}
                  </RiskBadge>
                </FindingHeader>
                <FindingCopy>
                  <div>{finding.issue}</div>
                  <div>
                    <strong>Empfehlung:</strong> {finding.recommendation}
                  </div>
                  {finding.quote && <Quote>{finding.quote}</Quote>}
                </FindingCopy>
              </FindingCard>
            ))}
          </FindingList>
        ) : (
          <EmptyResult>
            <CheckCircle2 size={18} />
            <div>Keine Prüfergebnisse vorhanden.</div>
          </EmptyResult>
        )}
      </PanelBody>
    </FlexColumnPanel>
  );
};
