import React, { useState } from "react";
import { Chip } from "@os-legal/ui";
import styled from "styled-components";
import { useNavigate } from "react-router-dom";
import {
  ChevronDown,
  Clock,
  Loader2,
  Check,
  X,
  FastForward,
  Pause,
  Play,
} from "lucide-react";
import { CorpusActionExecutionNode } from "../../graphql/queries";
import { getDocumentUrl } from "../../utils/navigationUtils";

import type { LucideIcon } from "lucide-react";

/**
 * Status configuration
 */
const STATUS_CONFIG: Record<
  string,
  {
    color: string;
    bgColor: string;
    Icon: LucideIcon;
    isSpinner?: boolean;
    label: string;
  }
> = {
  queued: {
    color: "#d97706",
    bgColor: "#fef3c7",
    Icon: Clock,
    label: "Queued",
  },
  running: {
    color: "#2563eb",
    bgColor: "#dbeafe",
    Icon: Loader2,
    isSpinner: true,
    label: "Running",
  },
  completed: {
    color: "#059669",
    bgColor: "#d1fae5",
    Icon: Check,
    label: "Completed",
  },
  failed: {
    color: "#dc2626",
    bgColor: "#fee2e2",
    Icon: X,
    label: "Failed",
  },
  skipped: {
    color: "#6b7280",
    bgColor: "#f3f4f6",
    Icon: FastForward,
    label: "Skipped",
  },
};

const TYPE_LABELS: Record<string, string> = {
  fieldset: "Fieldset",
  analyzer: "Analyzer",
  agent: "Agent",
};

/**
 * Format duration
 */
function formatDuration(seconds: number | null): string {
  if (seconds === null) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return secs > 0 ? `${minutes}m ${secs}s` : `${minutes}m`;
}

/**
 * Format relative time
 */
function formatRelativeTime(isoString: string | null): string {
  if (!isoString) return "—";
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return "Just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

const Row = styled.div<{ $expanded: boolean }>`
  background: ${(props) => (props.$expanded ? "#fafbfc" : "white")};
  border: 1px solid ${(props) => (props.$expanded ? "#e2e8f0" : "#f1f5f9")};
  border-radius: 8px;
  margin-bottom: 6px;
  transition: all 0.15s ease;
  overflow: hidden;

  &:hover {
    border-color: #e2e8f0;
    background: #fafbfc;
  }
`;

const RowHeader = styled.div`
  display: flex;
  align-items: center;
  padding: 12px 16px;
  cursor: pointer;
  gap: 16px;

  @media (max-width: 768px) {
    flex-wrap: wrap;
    gap: 8px;
    padding: 10px 12px;
  }
`;

const StatusDot = styled.div<{ $color: string; $bgColor: string }>`
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: ${(props) => props.$color};
  flex-shrink: 0;
`;

const ActionName = styled.div`
  font-weight: 500;
  color: #1e293b;
  font-size: 0.9rem;
  flex: 1;
  min-width: 120px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;

  @media (max-width: 768px) {
    flex-basis: calc(100% - 40px);
    order: 1;
  }
`;

const DocumentName = styled.div`
  color: #64748b;
  font-size: 0.8125rem;
  flex: 1.5;
  min-width: 150px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;

  @media (max-width: 768px) {
    flex-basis: 100%;
    order: 3;
  }
`;

const TypeBadge = styled.span`
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: #64748b;
  background: #f1f5f9;
  padding: 3px 8px;
  border-radius: 4px;
  flex-shrink: 0;

  @media (max-width: 768px) {
    order: 2;
  }
`;

const TimeInfo = styled.div`
  font-size: 0.8rem;
  color: #94a3b8;
  min-width: 70px;
  text-align: right;
  flex-shrink: 0;

  @media (max-width: 768px) {
    order: 4;
    text-align: left;
    min-width: auto;
  }
`;

const ExpandIcon = styled.div<{ $expanded: boolean }>`
  color: #94a3b8;
  transition: transform 0.2s ease;
  transform: rotate(${(props) => (props.$expanded ? "180deg" : "0deg")});
  flex-shrink: 0;

  @media (max-width: 768px) {
    order: 5;
    margin-left: auto;
  }
`;

const ExpandedContent = styled.div`
  padding: 0 16px 16px 16px;
  border-top: 1px solid #f1f5f9;
`;

const DetailGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 16px;
  padding: 12px 0;
`;

const DetailItem = styled.div`
  .label {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #94a3b8;
    margin-bottom: 4px;
  }
  .value {
    font-size: 0.85rem;
    color: #334155;
  }
`;

const ErrorBox = styled.div`
  margin-top: 12px;
  padding: 10px 12px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 6px;
  font-size: 0.8rem;
  color: #991b1b;
  font-family: ui-monospace, monospace;
`;

const DocumentLink = styled.button`
  background: none;
  border: none;
  color: #6366f1;
  cursor: pointer;
  padding: 0;
  font-size: inherit;
  text-decoration: none;

  &:hover {
    text-decoration: underline;
  }
`;

interface ActionExecutionRowProps {
  execution: CorpusActionExecutionNode;
}

export const ActionExecutionRow: React.FC<ActionExecutionRowProps> = ({
  execution,
}) => {
  const [expanded, setExpanded] = useState(false);
  const navigate = useNavigate();

  // Normalize status to lowercase for lookup
  const statusKey = (execution.status || "queued").toLowerCase();
  const status = STATUS_CONFIG[statusKey] || STATUS_CONFIG.queued;

  // Normalize type to lowercase for lookup
  const typeKey = (execution.actionType || "").toLowerCase();
  const typeLabel = TYPE_LABELS[typeKey] || execution.actionType || "Action";

  const handleDocumentClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (execution.document) {
      const url = getDocumentUrl(
        execution.document,
        execution.corpus,
        undefined
      );
      if (url !== "#") navigate(url);
    }
  };

  // Determine what target to display (document or conversation)
  const targetName = execution.document?.title || execution.conversation?.title;
  const isThreadAction = !execution.document && execution.conversation;

  return (
    <Row $expanded={expanded}>
      <RowHeader
        onClick={() => setExpanded(!expanded)}
        role="button"
        aria-expanded={expanded}
        tabIndex={0}
        onKeyDown={(e) => e.key === "Enter" && setExpanded(!expanded)}
      >
        <StatusDot $color={status.color} $bgColor={status.bgColor} />
        <ActionName title={execution.corpusAction.name}>
          {execution.corpusAction.name}
        </ActionName>
        <DocumentName title={targetName || "Unknown"}>
          {execution.document?.title ? (
            <DocumentLink onClick={handleDocumentClick}>
              {execution.document.title}
            </DocumentLink>
          ) : execution.conversation?.title ? (
            <span style={{ color: "#6366f1" }}>
              🗨️ {execution.conversation.title}
            </span>
          ) : (
            <span style={{ color: "#94a3b8" }}>
              {execution.conversation ? "🗨️ Thread" : "N/A"}
            </span>
          )}
        </DocumentName>
        <TypeBadge>{typeLabel}</TypeBadge>
        <TimeInfo>{formatRelativeTime(execution.queuedAt)}</TimeInfo>
        <ExpandIcon $expanded={expanded}>
          <ChevronDown size={12} />
        </ExpandIcon>
      </RowHeader>

      {expanded && (
        <ExpandedContent>
          <DetailGrid>
            <DetailItem>
              <div className="label">Status</div>
              <div className="value">
                <Chip
                  size="sm"
                  style={{
                    background: status.bgColor,
                    color: status.color,
                    fontWeight: 500,
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "4px",
                  }}
                >
                  <status.Icon
                    size={12}
                    className={status.isSpinner ? "animate-spin" : undefined}
                  />
                  {status.label}
                </Chip>
              </div>
            </DetailItem>
            <DetailItem>
              <div className="label">Queued</div>
              <div className="value">
                {new Date(execution.queuedAt).toLocaleString(undefined, {
                  month: "short",
                  day: "numeric",
                  hour: "numeric",
                  minute: "2-digit",
                })}
              </div>
            </DetailItem>
            {execution.startedAt && (
              <DetailItem>
                <div className="label">Started</div>
                <div className="value">
                  {new Date(execution.startedAt).toLocaleString(undefined, {
                    month: "short",
                    day: "numeric",
                    hour: "numeric",
                    minute: "2-digit",
                  })}
                </div>
              </DetailItem>
            )}
            {execution.durationSeconds !== null && (
              <DetailItem>
                <div className="label">Duration</div>
                <div className="value">
                  {formatDuration(execution.durationSeconds)}
                </div>
              </DetailItem>
            )}
            <DetailItem>
              <div className="label">Trigger</div>
              <div className="value">
                {execution.trigger.replace(/_/g, " ")}
              </div>
            </DetailItem>
            <DetailItem>
              <div className="label">Created by</div>
              <div className="value">{execution.creator.username}</div>
            </DetailItem>
          </DetailGrid>

          {execution.status === "failed" && execution.errorMessage && (
            <ErrorBox>{execution.errorMessage}</ErrorBox>
          )}
        </ExpandedContent>
      )}
    </Row>
  );
};
