import React, { useEffect, useState } from "react";
import {
  Container,
  Button,
  Divider,
  Header,
  Icon,
  Table,
  Confirm,
} from "semantic-ui-react";
import { useQuery, useReactiveVar, useMutation } from "@apollo/client";
import { toast } from "react-toastify";
import { useNavigate } from "react-router-dom";
import styled from "styled-components";
import { editingCorpus } from "../../graphql/cache";
import {
  GET_CORPUS_ACTIONS,
  GetCorpusActionsInput,
  GetCorpusActionsOutput,
} from "../../graphql/queries";
import {
  DELETE_CORPUS_ACTION,
  DeleteCorpusActionInput,
  DeleteCorpusActionOutput,
} from "../../graphql/mutations";
import { CreateCorpusActionModal } from "./CreateCorpusActionModal";
import { CorpusMetadataSettings } from "./CorpusMetadataSettings";
import { CorpusAgentSettings } from "./CorpusAgentSettings";
import {
  UPDATE_CORPUS,
  UpdateCorpusInputs,
  UpdateCorpusOutputs,
} from "../../graphql/mutations";
import { CorpusType } from "../../types/graphql-api";
import { PermissionTypes } from "../types";
import { getPermissions } from "../../utils/transform";

interface CorpusSettingsProps {
  corpus: {
    id: string;
    title: string;
    description: string;
    allowComments: boolean;
    preferredEmbedder?: string | null;
    slug?: string | null;
    creator?: {
      email: string;
      username?: string;
      slug?: string;
    };
    created?: string;
    modified?: string;
    isPublic?: boolean;
    myPermissions?: PermissionTypes[] | string[] | undefined;
    documents?: {
      totalCount: number;
    };
    annotations?: {
      totalCount: number;
    };
  };
}

const ActionCard = styled.div`
  background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
  border-radius: 16px;
  padding: 1.75rem;
  margin: 1.25rem 0;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.04), 0 1px 3px rgba(0, 0, 0, 0.08);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
  border: 1px solid #e5e7eb;
  overflow: hidden;

  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 10px 25px rgba(0, 0, 0, 0.08), 0 4px 10px rgba(0, 0, 0, 0.05);
    border-color: #ddd6fe;
  }

  &::before {
    content: "";
    position: absolute;
    left: -2rem;
    top: 50%;
    width: 1.5rem;
    height: 2px;
    background: linear-gradient(90deg, #a78bfa, #818cf8);
  }

  &::after {
    content: "";
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 3px;
    background: linear-gradient(180deg, #8b5cf6 0%, #6366f1 100%);
    opacity: 0;
    transition: opacity 0.3s ease;
  }

  &:hover::after {
    opacity: 1;
  }

  /* Fix Issue #7: Mobile responsive action cards */
  @media (max-width: 768px) {
    padding: 1.25rem;
    margin: 1rem 0;

    &::before {
      display: none; /* Hide connector line on mobile */
    }

    /* Disable hover transform on touch devices */
    @media (hover: none) {
      &:hover {
        transform: none;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.04), 0 1px 3px rgba(0, 0, 0, 0.08);
      }
    }
  }
`;

const TriggerBadge = styled.span<{ trigger: "add_document" | "edit_document" }>`
  background: ${(props) =>
    props.trigger === "add_document"
      ? "linear-gradient(135deg, #10b981 0%, #059669 100%)"
      : "linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)"};
  color: white;
  padding: 0.375rem 0.875rem;
  border-radius: 100px;
  font-size: 0.8125rem;
  font-weight: 600;
  letter-spacing: 0.025em;
  box-shadow: ${(props) =>
    props.trigger === "add_document"
      ? "0 4px 14px rgba(16, 185, 129, 0.35)"
      : "0 4px 14px rgba(59, 130, 246, 0.35)"};
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  transition: all 0.2s ease;

  &:hover {
    transform: translateY(-1px);
    box-shadow: ${(props) =>
      props.trigger === "add_document"
        ? "0 6px 20px rgba(16, 185, 129, 0.4)"
        : "0 6px 20px rgba(59, 130, 246, 0.4)"};
  }
`;

const ActionFlow = styled.div`
  padding-left: 2rem;
  border-left: 2px solid transparent;
  border-image: linear-gradient(180deg, #e0e7ff, #c7d2fe, #e0e7ff) 1;
  margin: 2rem 0;
  position: relative;

  &::before {
    content: "";
    position: absolute;
    left: -6px;
    top: 0;
    width: 10px;
    height: 10px;
    background: linear-gradient(135deg, #8b5cf6, #6366f1);
    border-radius: 50%;
    box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.2);
  }

  &::after {
    content: "";
    position: absolute;
    left: -6px;
    bottom: 0;
    width: 10px;
    height: 10px;
    background: linear-gradient(135deg, #8b5cf6, #6366f1);
    border-radius: 50%;
    box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.2);
  }
`;

const PageContainer = styled(Container)`
  padding: 2.5rem;
  max-width: 1200px !important;
  height: 100%;
  overflow-y: auto;
  overflow-x: hidden;
  background: linear-gradient(180deg, #fafbfc 0%, #f5f7fa 100%);

  &::-webkit-scrollbar {
    width: 10px;
  }

  &::-webkit-scrollbar-track {
    background: #f1f5f9;
    border-radius: 10px;
  }

  &::-webkit-scrollbar-thumb {
    background: linear-gradient(180deg, #cbd5e1, #94a3b8);
    border-radius: 10px;
    border: 2px solid #f1f5f9;

    &:hover {
      background: linear-gradient(180deg, #94a3b8, #64748b);
    }
  }

  /* Fix Issue #7: Mobile responsive styles */
  @media (max-width: 768px) {
    padding: 1.25rem;
  }
`;

const CorpusHeader = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 3rem;
  padding: 2rem;
  background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
  border-radius: 16px;
  border: 1px solid #e2e8f0;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.04);
  position: relative;
  overflow: hidden;

  &::before {
    content: "";
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 4px;
    background: linear-gradient(90deg, #6366f1 0%, #8b5cf6 50%, #ec4899 100%);
  }

  /* Fix Issue #7: Stack header on mobile */
  @media (max-width: 768px) {
    flex-direction: column;
    gap: 1rem;
    margin-bottom: 2rem;
    padding: 1.5rem;
  }
`;

const TitleArea = styled.div`
  flex: 1;
`;

const CorpusTitle = styled.h1`
  font-size: 2.25rem;
  font-weight: 700;
  background: linear-gradient(135deg, #1e293b 0%, #475569 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  margin: 0 0 0.75rem 0;
  letter-spacing: -0.03em;
  line-height: 1.2;

  /* Fix Issue #7: Smaller title on mobile */
  @media (max-width: 768px) {
    font-size: 1.75rem;
  }
`;

const CorpusDescription = styled.p`
  color: #64748b;
  font-size: 1.0625rem;
  margin: 0;
  max-width: 600px;
  line-height: 1.6;
  font-weight: 400;
`;

const EditButton = styled(Button)`
  &&& {
    background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
    color: white;
    border: none;
    padding: 0.875rem 1.5rem;
    font-weight: 600;
    border-radius: 12px;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    box-shadow: 0 4px 14px rgba(99, 102, 241, 0.25);
    margin-left: 1rem;
    position: relative;
    overflow: hidden;

    &::before {
      content: "";
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: linear-gradient(135deg, #818cf8 0%, #a78bfa 100%);
      opacity: 0;
      transition: opacity 0.3s ease;
    }

    &:hover {
      transform: translateY(-2px);
      box-shadow: 0 6px 20px rgba(99, 102, 241, 0.35);

      &::before {
        opacity: 1;
      }
    }

    &:active {
      transform: translateY(0);
    }

    .icon {
      margin-right: 0.5rem !important;
      position: relative;
      z-index: 1;
    }

    span {
      position: relative;
      z-index: 1;
    }

    /* Fix Issue #7: Full width button on mobile */
    @media (max-width: 768px) {
      margin-left: 0;
      width: 100%;
      justify-content: center;
    }
  }
`;

const InfoSection = styled.div`
  margin-bottom: 3.5rem;
  background: white;
  border-radius: 16px;
  border: 1px solid #e2e8f0;
  overflow: hidden;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.04), 0 1px 3px rgba(0, 0, 0, 0.08);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

  &:hover {
    box-shadow: 0 10px 25px rgba(0, 0, 0, 0.08), 0 4px 10px rgba(0, 0, 0, 0.05);
    transform: translateY(-1px);
  }

  @media (max-width: 768px) {
    margin-bottom: 2rem;
    border-radius: 12px;
  }
`;

const SectionHeader = styled.div`
  padding: 1.5rem 1.75rem;
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  border-bottom: 2px solid #e2e8f0;
  display: flex;
  align-items: center;
  justify-content: space-between;
`;

const SectionTitle = styled.h2`
  font-size: 1.125rem;
  font-weight: 700;
  color: #1e293b;
  margin: 0;
  display: flex;
  align-items: center;
  letter-spacing: -0.02em;

  &:before {
    content: "";
    width: 4px;
    height: 1.25rem;
    background: linear-gradient(180deg, #6366f1 0%, #8b5cf6 100%);
    margin-right: 0.875rem;
    border-radius: 100px;
    box-shadow: 0 2px 8px rgba(99, 102, 241, 0.3);
  }
`;

const MetadataContent = styled.div`
  padding: 2rem;

  @media (max-width: 768px) {
    padding: 1.5rem;
  }
`;

const MetadataGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 2.5rem;

  @media (max-width: 768px) {
    grid-template-columns: repeat(2, 1fr);
    gap: 2rem;
  }

  @media (max-width: 480px) {
    grid-template-columns: 1fr;
    gap: 1.5rem;
  }
`;

const MetadataItem = styled.div`
  position: relative;
  padding-left: 1rem;

  &::before {
    content: "";
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 3px;
    background: linear-gradient(180deg, #e0e7ff 0%, #c7d2fe 100%);
    border-radius: 100px;
    opacity: 0;
    transition: opacity 0.3s ease;
  }

  &:hover::before {
    opacity: 1;
  }

  .label {
    font-size: 0.8125rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #94a3b8;
    margin-bottom: 0.625rem;
    font-weight: 600;
    transition: color 0.2s ease;
  }

  &:hover .label {
    color: #64748b;
  }

  .value {
    font-size: 1.0625rem;
    color: #0f172a;
    font-weight: 600;
    line-height: 1.4;
  }

  .badge {
    display: inline-flex;
    align-items: center;
    border-radius: 100px;
    padding: 0.375rem 0.875rem;
    font-size: 0.875rem;
    font-weight: 600;
    transition: all 0.2s ease;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);

    &.private {
      background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
      color: #475569;
      border: 1px solid #e2e8f0;
    }

    &.public {
      background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
      color: #15803d;
      border: 1px solid #bbf7d0;
    }

    &:hover {
      transform: translateY(-1px);
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
    }

    .icon {
      margin-right: 0.375rem;
      font-size: 0.8125rem;
    }
  }
`;

const ActionHeader = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.5rem 1.75rem;
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  border-bottom: 2px solid #e2e8f0;
`;

const ActionContent = styled.div`
  padding: 2rem;

  @media (max-width: 768px) {
    padding: 1.5rem;
  }
`;

const AddActionButton = styled(Button)`
  &&& {
    background: linear-gradient(135deg, #10b981 0%, #059669 100%);
    color: white;
    border: none;
    padding: 0.75rem 1.25rem;
    font-weight: 600;
    border-radius: 10px;
    box-shadow: 0 4px 14px rgba(16, 185, 129, 0.25);
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    position: relative;
    overflow: hidden;

    &::before {
      content: "";
      position: absolute;
      top: 50%;
      left: 50%;
      width: 0;
      height: 0;
      border-radius: 50%;
      background: rgba(255, 255, 255, 0.2);
      transform: translate(-50%, -50%);
      transition: width 0.4s ease, height 0.4s ease;
    }

    &:hover {
      transform: translateY(-2px);
      box-shadow: 0 6px 20px rgba(16, 185, 129, 0.35);

      &::before {
        width: 300px;
        height: 300px;
      }
    }

    &:active {
      transform: translateY(0);
    }

    .icon {
      margin-right: 0.5rem !important;
      position: relative;
      z-index: 1;
    }

    span {
      position: relative;
      z-index: 1;
    }
  }
`;

const ActionNote = styled.div`
  font-size: 1rem;
  color: #475569;
  margin-bottom: 2.5rem;
  line-height: 1.7;
  padding: 1.25rem;
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  position: relative;
  padding-left: 3rem;

  &::before {
    content: "💡";
    position: absolute;
    left: 1.25rem;
    top: 1.25rem;
    font-size: 1.25rem;
  }

  strong {
    color: #0f172a;
    font-weight: 700;
    background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }

  .highlight {
    color: #6366f1;
    font-weight: 600;
    position: relative;

    &::after {
      content: "";
      position: absolute;
      bottom: -2px;
      left: 0;
      right: 0;
      height: 2px;
      background: linear-gradient(90deg, #6366f1 0%, #8b5cf6 100%);
      opacity: 0.3;
    }
  }
`;

/**
 * Component for managing corpus settings and actions
 * Only visible to users with update permissions
 */
const SettingsContainer = styled.div`
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  overflow: hidden;
  position: relative;
`;

export const CorpusSettings: React.FC<CorpusSettingsProps> = ({ corpus }) => {
  const navigate = useNavigate();

  // Check if myPermissions is already processed (array of PermissionTypes) or raw
  const permissions =
    Array.isArray(corpus.myPermissions) &&
    corpus.myPermissions.length > 0 &&
    typeof corpus.myPermissions[0] === "string" &&
    corpus.myPermissions[0].includes("CAN_")
      ? (corpus.myPermissions as PermissionTypes[]) // Already processed
      : getPermissions(corpus.myPermissions || []); // Need to process

  const canUpdate = permissions.includes(PermissionTypes.CAN_UPDATE);
  const canPermission = permissions.includes(PermissionTypes.CAN_PERMISSION);
  const [slugDraft, setSlugDraft] = useState<string>("");
  const [publicDraft, setPublicDraft] = useState<boolean>(
    Boolean(corpus.isPublic)
  );
  const [originalSlug, setOriginalSlug] = useState<string>("");

  useEffect(() => {
    setSlugDraft(corpus.slug || "");
    setOriginalSlug(corpus.slug || "");
    setPublicDraft(Boolean(corpus.isPublic));
  }, [corpus]);

  const [updateCorpusMutation, { loading: updatingVisibility }] = useMutation<
    UpdateCorpusOutputs,
    UpdateCorpusInputs
  >(UPDATE_CORPUS, {
    onCompleted: (data) => {
      if (data.updateCorpus?.ok) {
        toast.success("Updated corpus settings");

        // If slug was updated, navigate to the new URL
        if (slugDraft && slugDraft !== originalSlug && corpus.creator?.slug) {
          const newUrl = `/c/${corpus.creator.slug}/${slugDraft}`;
          navigate(newUrl, { replace: true });
        }
      } else {
        toast.error(data.updateCorpus?.message || "Failed to update corpus");
      }
    },
    onError: (err) => toast.error(err.message),
  });
  const [isModalOpen, setIsModalOpen] = React.useState(false);
  const [actionToDelete, setActionToDelete] = React.useState<string | null>(
    null
  );

  const { data: actionsData, refetch: refetchActions } = useQuery<
    GetCorpusActionsOutput,
    GetCorpusActionsInput
  >(GET_CORPUS_ACTIONS, {
    variables: { corpusId: corpus.id },
    fetchPolicy: "network-only",
  });

  // Refetch actions when component mounts
  useEffect(() => {
    refetchActions();
  }, []);

  const [deleteCorpusAction] = useMutation<
    DeleteCorpusActionOutput,
    DeleteCorpusActionInput
  >(DELETE_CORPUS_ACTION, {
    onCompleted: (data) => {
      if (data.deleteCorpusAction.ok) {
        toast.success("Action deleted successfully");
        refetchActions();
      } else {
        toast.error(
          `Failed to delete action: ${data.deleteCorpusAction.message}`
        );
      }
    },
    onError: (error) => {
      toast.error(`Error deleting action: ${error.message}`);
    },
  });

  const handleDelete = async (id: string) => {
    try {
      await deleteCorpusAction({
        variables: { id },
      });
    } catch (error) {
      // Error handled by onError callback
    } finally {
      setActionToDelete(null);
    }
  };

  return (
    <SettingsContainer>
      <PageContainer>
        <CorpusHeader>
          <TitleArea>
            <CorpusTitle>{corpus.title}</CorpusTitle>
            <CorpusDescription>
              {corpus.description || "No description provided."}
            </CorpusDescription>
          </TitleArea>
          <EditButton
            icon
            labelPosition="left"
            onClick={() => editingCorpus(corpus as unknown as CorpusType)}
          >
            <Icon name="edit outline" />
            Edit
          </EditButton>
        </CorpusHeader>

        <InfoSection>
          <SectionHeader>
            <SectionTitle>Corpus Information</SectionTitle>
          </SectionHeader>

          <MetadataContent>
            <MetadataGrid>
              <MetadataItem>
                <div className="label">Created by</div>
                <div className="value">
                  {corpus.creator?.email || "Unknown"}
                </div>
              </MetadataItem>

              <MetadataItem>
                <div className="label">Preferred Embedder</div>
                <div className="value">
                  {corpus.preferredEmbedder || "Default"}
                </div>
              </MetadataItem>

              <MetadataItem>
                <div className="label">Created</div>
                <div className="value">
                  {corpus.created
                    ? new Date(corpus.created).toLocaleDateString(undefined, {
                        year: "numeric",
                        month: "short",
                        day: "numeric",
                      })
                    : "Unknown"}
                </div>
              </MetadataItem>

              <MetadataItem>
                <div className="label">Last Updated</div>
                <div className="value">
                  {corpus.modified
                    ? new Date(corpus.modified).toLocaleDateString(undefined, {
                        year: "numeric",
                        month: "short",
                        day: "numeric",
                      })
                    : "Unknown"}
                </div>
              </MetadataItem>

              <MetadataItem>
                <div className="label">Visibility</div>
                <div className="value">
                  <span
                    className={`badge ${
                      corpus.isPublic ? "public" : "private"
                    }`}
                  >
                    <Icon
                      name={corpus.isPublic ? "unlock" : "lock"}
                      size="small"
                    />
                    {corpus.isPublic ? "Public" : "Private"}
                  </span>
                </div>
              </MetadataItem>

              {corpus.allowComments && (
                <MetadataItem>
                  <div className="label">Comments</div>
                  <div className="value">
                    <span className="badge public">
                      <Icon name="comments" size="small" />
                      Enabled
                    </span>
                  </div>
                </MetadataItem>
              )}
            </MetadataGrid>
          </MetadataContent>
        </InfoSection>

        <InfoSection>
          <SectionHeader>
            <SectionTitle>Visibility & Slug</SectionTitle>
          </SectionHeader>
          <MetadataContent>
            {!canUpdate && !canPermission && (
              <div
                style={{
                  background:
                    "linear-gradient(135deg, #fef3c7 0%, #fed7aa 100%)",
                  border: "1px solid #fbbf24",
                  borderRadius: "10px",
                  padding: "1rem 1.25rem",
                  marginBottom: "1.5rem",
                  fontSize: "0.9375rem",
                  color: "#92400e",
                  display: "flex",
                  alignItems: "center",
                  gap: "0.75rem",
                  boxShadow: "0 2px 8px rgba(251, 191, 36, 0.15)",
                }}
              >
                <span style={{ fontSize: "1.25rem" }}>⚠️</span>
                <span>
                  You don't have permission to update these settings. Contact
                  the corpus owner for access.
                </span>
              </div>
            )}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: "2rem",
                alignItems: "end",
              }}
            >
              <div>
                <div
                  style={{
                    fontSize: "0.875rem",
                    textTransform: "uppercase",
                    letterSpacing: "0.08em",
                    color: !canPermission ? "#cbd5e1" : "#64748b",
                    marginBottom: "0.75rem",
                    fontWeight: 600,
                    display: "flex",
                    alignItems: "center",
                    gap: "0.5rem",
                  }}
                >
                  Public visibility
                  {!canPermission && (
                    <span
                      style={{
                        fontSize: "0.75rem",
                        background: "#f1f5f9",
                        padding: "0.125rem 0.375rem",
                        borderRadius: "4px",
                        fontWeight: 500,
                        textTransform: "none",
                      }}
                    >
                      No permission
                    </span>
                  )}
                </div>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "0.875rem",
                    padding: "0.875rem 1rem",
                    background: !canPermission
                      ? "linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%)"
                      : "linear-gradient(135deg, #ffffff 0%, #fafbfc 100%)",
                    border: "2px solid",
                    borderColor: !canPermission ? "#e2e8f0" : "#cbd5e1",
                    borderRadius: "10px",
                    transition: "all 0.3s ease",
                  }}
                >
                  <label
                    htmlFor="corpus-is-public-checkbox"
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.75rem",
                      cursor: !canPermission ? "not-allowed" : "pointer",
                      width: "100%",
                    }}
                  >
                    <input
                      id="corpus-is-public-checkbox"
                      type="checkbox"
                      checked={publicDraft}
                      disabled={!canPermission}
                      onChange={(e) => setPublicDraft(e.target.checked)}
                      style={{
                        width: "20px",
                        height: "20px",
                        cursor: !canPermission ? "not-allowed" : "pointer",
                        opacity: !canPermission ? 0.5 : 1,
                        accentColor: "#6366f1",
                      }}
                    />
                    <span
                      style={{
                        fontSize: "0.9375rem",
                        fontWeight: 600,
                        color: !canPermission ? "#94a3b8" : "#1e293b",
                      }}
                    >
                      {publicDraft ? "Public" : "Private"}
                    </span>
                  </label>
                </div>
              </div>
              <div>
                <div
                  style={{
                    fontSize: "0.875rem",
                    textTransform: "uppercase",
                    letterSpacing: "0.08em",
                    color: !canUpdate ? "#cbd5e1" : "#64748b",
                    marginBottom: "0.75rem",
                    fontWeight: 600,
                    display: "flex",
                    alignItems: "center",
                    gap: "0.5rem",
                  }}
                >
                  Slug
                  {!canUpdate && (
                    <span
                      style={{
                        fontSize: "0.75rem",
                        background: "#f1f5f9",
                        padding: "0.125rem 0.375rem",
                        borderRadius: "4px",
                        fontWeight: 500,
                        textTransform: "none",
                      }}
                    >
                      No permission
                    </span>
                  )}
                </div>
                <input
                  id="corpus-slug-input"
                  type="text"
                  placeholder="Repo slug (case-sensitive)"
                  value={slugDraft}
                  disabled={!canUpdate}
                  onChange={(e) => setSlugDraft(e.target.value)}
                  style={{
                    width: "100%",
                    padding: "0.875rem 1rem",
                    border: "2px solid",
                    borderColor: !canUpdate ? "#e2e8f0" : "#cbd5e1",
                    borderRadius: "10px",
                    background: !canUpdate
                      ? "linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%)"
                      : "white",
                    cursor: !canUpdate ? "not-allowed" : "text",
                    opacity: !canUpdate ? 0.7 : 1,
                    fontSize: "0.9375rem",
                    fontWeight: 500,
                    color: "#1e293b",
                    transition: "all 0.3s ease",
                    outline: "none",
                    ...(canUpdate && {
                      "&:focus": {
                        borderColor: "#6366f1",
                        boxShadow: "0 0 0 3px rgba(99, 102, 241, 0.1)",
                      },
                    }),
                  }}
                />
              </div>
              <div style={{ gridColumn: "1 / span 2", marginTop: "1rem" }}>
                <Button
                  primary
                  loading={updatingVisibility}
                  disabled={!canUpdate && !canPermission}
                  onClick={() => {
                    const vars: UpdateCorpusInputs = { id: corpus.id } as any;
                    if (canPermission) vars.isPublic = publicDraft;
                    if (canUpdate) vars.slug = slugDraft || undefined;
                    updateCorpusMutation({ variables: vars });
                  }}
                  style={{
                    background:
                      !canUpdate && !canPermission
                        ? "#e2e8f0"
                        : "linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)",
                    color: !canUpdate && !canPermission ? "#94a3b8" : "white",
                    border: "none",
                    padding: "0.875rem 2rem",
                    borderRadius: "10px",
                    fontWeight: 600,
                    fontSize: "0.9375rem",
                    cursor:
                      !canUpdate && !canPermission ? "not-allowed" : "pointer",
                    boxShadow:
                      !canUpdate && !canPermission
                        ? "none"
                        : "0 4px 14px rgba(99, 102, 241, 0.25)",
                    transition: "all 0.3s ease",
                    ...(canUpdate || canPermission
                      ? {
                          "&:hover": {
                            transform: "translateY(-2px)",
                            boxShadow: "0 6px 20px rgba(99, 102, 241, 0.35)",
                          },
                        }
                      : {}),
                  }}
                >
                  <Icon name="save" /> Save Changes
                </Button>
              </div>
            </div>
          </MetadataContent>
        </InfoSection>

        <InfoSection>
          <ActionHeader>
            <SectionTitle>Corpus Actions</SectionTitle>
            <AddActionButton onClick={() => setIsModalOpen(true)}>
              <Icon name="plus" />
              Add Action
            </AddActionButton>
          </ActionHeader>

          <ActionContent>
            <ActionNote>
              This system allows you to <strong>automate actions</strong> when
              documents are
              <span className="highlight"> added</span> or{" "}
              <span className="highlight"> edited</span> in a corpus, either
              running extractions via <strong>fieldsets</strong> or analyses via{" "}
              <strong>analyzers</strong>.
            </ActionNote>

            <ActionFlow>
              {actionsData?.corpusActions?.edges.map(({ node: action }) => (
                <ActionCard key={action.id}>
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "flex-start",
                    }}
                  >
                    <div>
                      <div
                        style={{
                          display: "flex",
                          gap: "1rem",
                          alignItems: "center",
                          marginBottom: "0.5rem",
                        }}
                      >
                        <h3
                          style={{
                            margin: 0,
                            color: "#111827",
                            fontSize: "1.25rem",
                            fontWeight: 600,
                          }}
                        >
                          {action.name}
                        </h3>
                        <TriggerBadge
                          trigger={
                            action.trigger as "add_document" | "edit_document"
                          }
                        >
                          {action.trigger === "add_document"
                            ? "📥 On Add"
                            : "✏️ On Edit"}
                        </TriggerBadge>
                      </div>

                      <div
                        style={{
                          display: "flex",
                          gap: "2rem",
                          color: "rgba(0,0,0,0.75)",
                          marginTop: "1rem",
                          fontSize: "0.95rem",
                        }}
                      >
                        <div>
                          <Icon name="code" />
                          {action.fieldset
                            ? `Fieldset: ${action.fieldset.name}`
                            : `Analyzer: ${action.analyzer?.name}`}
                        </div>
                        <div>
                          <Icon name="user" />
                          {action.creator.username}
                        </div>
                        <div>
                          <Icon name="calendar" />
                          {new Date(action.created).toLocaleDateString()}
                        </div>
                      </div>
                    </div>

                    <div
                      style={{
                        display: "flex",
                        gap: "0.5rem",
                        alignItems: "center",
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "0.5rem",
                          padding: "0.5rem 1rem",
                          borderRadius: "6px",
                          background: action.disabled ? "#fef2f2" : "#f0fdf4",
                          color: action.disabled ? "#dc2626" : "#16a34a",
                          fontWeight: 600,
                          boxShadow: "0 1px 2px rgba(0,0,0,0.05)",
                        }}
                      >
                        <Icon
                          name={
                            action.disabled ? "pause circle" : "play circle"
                          }
                        />
                        {action.disabled ? "Disabled" : "Active"}
                      </div>

                      <Button
                        icon
                        negative
                        size="tiny"
                        onClick={() => setActionToDelete(action.id)}
                      >
                        <Icon name="trash" />
                      </Button>
                    </div>
                  </div>
                </ActionCard>
              ))}
            </ActionFlow>
          </ActionContent>
        </InfoSection>

        <InfoSection>
          <SectionHeader>
            <SectionTitle>Metadata Fields</SectionTitle>
          </SectionHeader>
          <MetadataContent>
            <CorpusMetadataSettings corpusId={corpus.id} />
          </MetadataContent>
        </InfoSection>

        <InfoSection>
          <SectionHeader>
            <SectionTitle>Agent Instructions</SectionTitle>
          </SectionHeader>
          <MetadataContent>
            <CorpusAgentSettings
              corpusId={corpus.id}
              corpusAgentInstructions={(corpus as any).corpusAgentInstructions}
              documentAgentInstructions={
                (corpus as any).documentAgentInstructions
              }
              canUpdate={canUpdate}
            />
          </MetadataContent>
        </InfoSection>

        <CreateCorpusActionModal
          corpusId={corpus.id}
          open={isModalOpen}
          onClose={() => setIsModalOpen(false)}
          onSuccess={() => {
            setIsModalOpen(false);
            refetchActions();
          }}
        />

        <Confirm
          open={!!actionToDelete}
          onCancel={() => setActionToDelete(null)}
          onConfirm={() => actionToDelete && handleDelete(actionToDelete)}
          content="Are you sure you want to delete this action? This cannot be undone."
          confirmButton="Delete"
          cancelButton="Cancel"
        />
      </PageContainer>
    </SettingsContainer>
  );
};
