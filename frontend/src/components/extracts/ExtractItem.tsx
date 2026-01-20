import { useMutation } from "@apollo/client";
import { toast } from "react-toastify";
import { Card, IconButton } from "@os-legal/ui";
import { Settings, Trash2, LayoutGrid, FileText, Table2 } from "lucide-react";
import { LoadingOverlay } from "../common/LoadingOverlay";
import {
  RequestDeleteExtractInputType,
  RequestDeleteExtractOutputType,
  REQUEST_DELETE_EXTRACT,
} from "../../graphql/mutations";
import { GetExtractsOutput, GET_EXTRACTS } from "../../graphql/queries";
import { ExtractType, CorpusType } from "../../types/graphql-api";

import _ from "lodash";
import { PermissionTypes } from "../types";
import { getPermissions } from "../../utils/transform";
import useWindowDimensions from "../hooks/WindowDimensionHook";
import { MOBILE_VIEW_BREAKPOINT } from "../../assets/configurations/constants";
import styled from "styled-components";

interface ExtractItemProps {
  extract: ExtractType;
  selected?: boolean;
  read_only?: boolean;
  corpus?: CorpusType | null | undefined;
  compact?: boolean;
  onSelect?: () => any | never;
}

const ExtractCard = styled(Card)<{ $selected?: boolean; $compact?: boolean }>`
  padding: 1.25rem !important;
  margin: 0 0 1rem 0 !important;
  width: 100% !important;
  min-width: 0 !important;
  background: ${(props) =>
    props.$selected
      ? "linear-gradient(165deg, rgba(34, 197, 94, 0.05), rgba(255, 255, 255, 0.6))"
      : "#ffffff"} !important;
  border: 1px solid ${(props) => (props.$selected ? "#22c55e" : "#e2e8f0")} !important;
  border-radius: 16px !important;
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1) !important;
  box-shadow: ${(props) =>
    props.$selected
      ? "0 8px 24px rgba(34, 197, 94, 0.08)"
      : "0 1px 3px rgba(0, 0, 0, 0.01)"} !important;

  &:hover {
    transform: translateY(-1px);
    box-shadow: 0 8px 28px rgba(0, 0, 0, 0.05) !important;
  }

  .content {
    padding: 0 !important;
    border: none !important;
  }
`;

const CardHeader = styled.div`
  display: flex;
  align-items: flex-start;
  gap: 1rem;
  margin-bottom: 1.25rem;

  .icon-wrapper {
    flex-shrink: 0;
    width: 40px;
    height: 40px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #f8fafc;
    border-radius: 10px;
    color: #64748b;
    transition: all 0.2s ease;

    i.icon {
      margin: 0 !important;
      font-size: 1.25rem !important;
    }
  }

  .text {
    flex: 1;
    min-width: 0;

    h3 {
      font-size: 1.125rem;
      font-weight: 600;
      color: #1e293b;
      margin: 0 0 0.375rem 0;
      word-break: break-word;
    }

    .date {
      font-size: 0.75rem;
      color: #64748b;
    }
  }
`;

const Description = styled.div`
  font-size: 0.875rem;
  color: #475569;
  line-height: 1.5;
  margin-bottom: 1.25rem;
`;

const MetadataBadges = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
`;

const MetadataBadge = styled.div`
  display: inline-flex;
  align-items: center;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  color: #64748b;
  border-radius: 8px;
  padding: 0.5rem 0.75rem;
  font-size: 0.75rem;
  font-weight: 500;
`;

const ActionBadge = styled.div`
  position: absolute;
  top: -0.5rem;
  right: 1rem;
  display: inline-flex;
  align-items: center;
  background: #22c55e;
  color: white;
  border-radius: 20px;
  padding: 0.375rem 0.75rem;
  font-size: 0.75rem;
  font-weight: 500;
  box-shadow: 0 4px 12px rgba(34, 197, 94, 0.15);
`;

const DeleteButton = styled(IconButton)`
  position: absolute !important;
  top: 1rem !important;
  right: 1rem !important;
  padding: 0.5rem !important;
  width: 32px !important;
  height: 32px !important;
  background: rgba(239, 68, 68, 0.1) !important;
  color: #ef4444 !important;
  border: 1px solid rgba(239, 68, 68, 0.2) !important;
  box-shadow: none !important;
  transition: all 0.2s ease !important;

  &:hover {
    background: rgba(239, 68, 68, 0.15) !important;
    transform: scale(1.05);
  }
`;

export const ExtractItem: React.FC<ExtractItemProps> = ({
  extract,
  selected,
  read_only,
  corpus: selectedCorpus,
  onSelect,
  compact,
}) => {
  const { width } = useWindowDimensions();
  const use_mobile_layout = width <= MOBILE_VIEW_BREAKPOINT;

  const [requestDeleteExtract] = useMutation<
    RequestDeleteExtractOutputType,
    RequestDeleteExtractInputType
  >(REQUEST_DELETE_EXTRACT, {
    variables: {
      id: extract.id,
    },
    onCompleted: (data) => {
      toast.success("Extract deleting...");
    },
    onError: (data) => {
      toast.error("Could not delete extract...");
    },
    update: (cache, { data: delete_extract_data }) => {
      if (!selectedCorpus?.id) return;

      try {
        const cache_data: GetExtractsOutput | null = cache.readQuery({
          query: GET_EXTRACTS,
          variables: { corpusId: selectedCorpus.id },
        });

        if (cache_data?.extracts?.edges) {
          const new_cache_data = _.cloneDeep(cache_data);
          new_cache_data.extracts.edges = new_cache_data.extracts.edges.filter(
            (edge) => edge.node.id !== extract.id
          );

          cache.writeQuery({
            query: GET_EXTRACTS,
            variables: { corpusId: selectedCorpus.id },
            data: new_cache_data,
          });
        }
      } catch (error) {
        console.warn("Failed to update cache after extract deletion:", error);
      }
    },
  });

  const my_permissions = getPermissions(
    extract.myPermissions ? extract.myPermissions : []
  );
  const can_delete = my_permissions.includes(PermissionTypes.CAN_REMOVE);

  return (
    <ExtractCard
      $selected={selected}
      $compact={compact}
      onClick={onSelect && extract.finished ? onSelect : undefined}
    >
      <LoadingOverlay
        active={!extract.finished}
        inverted
        content="Processing..."
      />

      {extract.corpusAction && (
        <ActionBadge>
          <Settings size={12} style={{ marginRight: "0.375rem" }} />{" "}
          {extract.corpusAction.name}
        </ActionBadge>
      )}

      {!read_only && can_delete && (
        <DeleteButton
          variant="danger"
          aria-label="Delete extract"
          onClick={(e: { stopPropagation: () => void }) => {
            e.stopPropagation();
            requestDeleteExtract();
          }}
        >
          <Trash2 size={14} />
        </DeleteButton>
      )}

      <CardHeader>
        <div className="icon-wrapper">
          <LayoutGrid size={20} />
        </div>
        <div className="text">
          <h3>{extract.name}</h3>
          <span className="date">
            Created {new Date(extract.created).toLocaleDateString()}
          </span>
        </div>
      </CardHeader>

      {!compact && (
        <Description>
          {extract.fieldset?.description || "No description available"}
        </Description>
      )}

      <MetadataBadges>
        <MetadataBadge>
          <FileText size={12} style={{ marginRight: "0.375rem" }} />
          {extract.fullDocumentList?.length || 0} Documents
        </MetadataBadge>
        <MetadataBadge>
          <Table2 size={12} style={{ marginRight: "0.375rem" }} />
          {extract.fieldset?.fullColumnList?.length || 0} Columns
        </MetadataBadge>
      </MetadataBadges>
    </ExtractCard>
  );
};
