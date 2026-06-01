import React from "react";
import styled from "styled-components";
import {
  FileText,
  Table2,
  BarChart3,
  Download,
  XCircle,
  Sparkles,
  Ban,
  LucideIcon,
} from "lucide-react";
import type { JobNotification } from "../../hooks/useJobNotifications";
import type { NotificationType } from "../../hooks/useNotificationWebSocket";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";

// Semantic status colors for job toasts, sourced from the design tokens so we
// don't scatter raw hex literals (no-magic-numbers). The IconContainer appends
// a "20" alpha suffix, so each must be a 6-digit hex.
const STATUS_SUCCESS = OS_LEGAL_COLORS.success;
const STATUS_FAILED = OS_LEGAL_COLORS.danger;
const STATUS_INFO = OS_LEGAL_COLORS.primaryBlue;
const STATUS_NEUTRAL = OS_LEGAL_COLORS.textMuted;

const ToastContainer = styled.div<{ $clickable?: boolean }>`
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: ${({ $clickable }) => ($clickable ? "pointer" : "default")};
`;

const IconContainer = styled.div<{ $color: string }>`
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: ${({ $color }) => $color}20;
  display: flex;
  align-items: center;
  justify-content: center;
  color: ${({ $color }) => $color};

  svg {
    width: 18px;
    height: 18px;
  }
`;

const Content = styled.div`
  flex: 1;
  min-width: 0;
`;

const Title = styled.div`
  font-weight: 600;
  font-size: 14px;
  color: #1f2937;
  margin-bottom: 2px;
`;

const Message = styled.div`
  font-size: 13px;
  color: #6b7280;
  line-height: 1.3;
`;

interface JobNotificationConfig {
  icon: LucideIcon;
  color: string;
  title: string;
  getMessage: (data: Record<string, unknown>) => string;
}

const JOB_NOTIFICATION_CONFIG: Record<string, JobNotificationConfig> = {
  DOCUMENT_PROCESSED: {
    icon: FileText,
    color: STATUS_SUCCESS,
    title: "Document Ready",
    getMessage: (data) =>
      `"${(data.documentTitle as string) || "Document"}" finished processing`,
  },
  EXTRACT_COMPLETE: {
    icon: Table2,
    color: STATUS_INFO,
    title: "Extract Complete",
    getMessage: (data) =>
      `"${(data.extractName as string) || "Extract"}" completed (${
        data.documentCount || 0
      } docs)`,
  },
  ANALYSIS_COMPLETE: {
    icon: BarChart3,
    color: STATUS_SUCCESS,
    title: "Analysis Complete",
    getMessage: (data) =>
      `"${(data.analyzerName as string) || "Analysis"}" finished successfully`,
  },
  ANALYSIS_FAILED: {
    icon: XCircle,
    color: STATUS_FAILED,
    title: "Analysis Failed",
    getMessage: (data) =>
      `"${(data.analyzerName as string) || "Analysis"}" encountered an error`,
  },
  EXPORT_COMPLETE: {
    icon: Download,
    color: STATUS_SUCCESS,
    title: "Export Ready",
    getMessage: (data) =>
      `"${
        (data.exportName as string) || (data.corpusName as string) || "Export"
      }" is ready for download`,
  },
  RESEARCH_REPORT_COMPLETE: {
    icon: Sparkles,
    color: STATUS_SUCCESS,
    title: "Research Complete",
    getMessage: (data) =>
      `"${(data.title as string) || "Research"}" is ready to read`,
  },
  RESEARCH_REPORT_FAILED: {
    icon: XCircle,
    color: STATUS_FAILED,
    title: "Research Failed",
    getMessage: (data) =>
      `"${(data.title as string) || "Research"}" could not be completed`,
  },
  RESEARCH_REPORT_CANCELLED: {
    icon: Ban,
    color: STATUS_NEUTRAL,
    title: "Research Cancelled",
    getMessage: (data) =>
      `"${(data.title as string) || "Research"}" was cancelled`,
  },
};

export interface JobNotificationToastProps {
  notification: JobNotification;
  /** Optional click handler — e.g. deep-link a research toast to its report. */
  onClick?: () => void;
}

/**
 * Toast component for job completion notifications.
 * Issue #624: Real-time notifications for job completion.
 */
export function JobNotificationToast({
  notification,
  onClick,
}: JobNotificationToastProps) {
  const config =
    JOB_NOTIFICATION_CONFIG[notification.type] ||
    JOB_NOTIFICATION_CONFIG.DOCUMENT_PROCESSED;

  const Icon = config.icon;

  return (
    <ToastContainer $clickable={Boolean(onClick)} onClick={onClick}>
      <IconContainer $color={config.color}>
        <Icon />
      </IconContainer>
      <Content>
        <Title>{config.title}</Title>
        <Message>{config.getMessage(notification.data)}</Message>
      </Content>
    </ToastContainer>
  );
}
