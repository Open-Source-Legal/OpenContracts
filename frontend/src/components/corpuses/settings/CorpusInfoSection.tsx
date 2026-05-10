/**
 * CorpusInfoSection - Metadata grid showing corpus information
 */
import React from "react";
import styled from "styled-components";
import { Lock, Unlock, MessageSquare, Scale, ExternalLink } from "lucide-react";
import { LICENSE_OPTIONS } from "../../../assets/configurations/constants";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";
import { getCreatorDisplay } from "../../../utils/userDisplay";
import {
  SettingsCard,
  SettingsCardHeader,
  SettingsCardTitle,
  SettingsCardContent,
  MetadataGrid,
  MetadataItem,
  StatusBadge,
} from "../styles/corpusSettingsStyles";

const LicenseBadge = styled.span`
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.375rem 0.75rem;
  border-radius: 100px;
  font-size: 0.875rem;
  font-weight: 500;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  color: ${OS_LEGAL_COLORS.textSecondary};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  text-decoration: none;
  transition: background 0.15s ease;

  &[href]:hover {
    background: ${OS_LEGAL_COLORS.surfaceLight};
    cursor: pointer;
  }
`;

interface CorpusInfoSectionProps {
  corpus: {
    // ``email`` is redacted to ``null`` for non-self viewers; the
    // privacy contract guarantees only ``id`` and ``slug``.
    creator?: {
      id?: string | null;
      slug?: string | null;
      email?: string | null;
    };
    preferredEmbedder?: string | null;
    created?: string;
    modified?: string;
    isPublic?: boolean;
    allowComments?: boolean;
    license?: string | null;
    licenseLink?: string | null;
  };
}

export const CorpusInfoSection: React.FC<CorpusInfoSectionProps> = ({
  corpus,
}) => {
  const formatDate = (dateString: string | undefined) => {
    if (!dateString) return "Unknown";
    return new Date(dateString).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  };

  return (
    <SettingsCard>
      <SettingsCardHeader>
        <SettingsCardTitle>Corpus Information</SettingsCardTitle>
      </SettingsCardHeader>

      <SettingsCardContent>
        <MetadataGrid>
          <MetadataItem>
            <div className="label">Created by</div>
            <div className="value">{getCreatorDisplay(corpus.creator)}</div>
          </MetadataItem>

          <MetadataItem>
            <div className="label">Preferred Embedder</div>
            <div className="value">{corpus.preferredEmbedder || "Default"}</div>
          </MetadataItem>

          <MetadataItem>
            <div className="label">Created</div>
            <div className="value">{formatDate(corpus.created)}</div>
          </MetadataItem>

          <MetadataItem>
            <div className="label">Last Updated</div>
            <div className="value">{formatDate(corpus.modified)}</div>
          </MetadataItem>

          <MetadataItem>
            <div className="label">Visibility</div>
            <div className="value">
              <StatusBadge variant={corpus.isPublic ? "public" : "private"}>
                {corpus.isPublic ? <Unlock size={14} /> : <Lock size={14} />}
                {corpus.isPublic ? "Public" : "Private"}
              </StatusBadge>
            </div>
          </MetadataItem>

          {corpus.allowComments && (
            <MetadataItem>
              <div className="label">Comments</div>
              <div className="value">
                <StatusBadge variant="public">
                  <MessageSquare size={14} />
                  Enabled
                </StatusBadge>
              </div>
            </MetadataItem>
          )}

          {corpus.license && (
            <MetadataItem>
              <div className="label">License</div>
              <div className="value">
                <LicenseBadge
                  as={corpus.licenseLink ? "a" : "span"}
                  href={corpus.licenseLink || undefined}
                  target={corpus.licenseLink ? "_blank" : undefined}
                  rel={corpus.licenseLink ? "noopener noreferrer" : undefined}
                >
                  <Scale size={14} />
                  {LICENSE_OPTIONS.find((o) => o.value === corpus.license)
                    ?.label || corpus.license}
                  {corpus.licenseLink && <ExternalLink size={12} />}
                </LicenseBadge>
              </div>
            </MetadataItem>
          )}
        </MetadataGrid>
      </SettingsCardContent>
    </SettingsCard>
  );
};
