import React, { useEffect, useRef, useState } from "react";
import { Modal } from "semantic-ui-react";
import { Button } from "@os-legal/ui";
import { Spinner } from "@os-legal/ui";
import {
  Eye,
  Trash2,
  FileText,
  Clock,
  CheckCircle2,
  AlertTriangle,
  Play,
} from "lucide-react";
import { ExtractType, PageInfo } from "../../../types/graphql-api";
import { FetchMoreOnVisible } from "../../widgets/infinite_scroll/FetchMoreOnVisible";
import { useMutation } from "@apollo/client";
import { REQUEST_START_EXTRACT } from "../../../graphql/mutations";

interface ExtractListProps {
  items: ExtractType[] | undefined;
  pageInfo: PageInfo | undefined;
  loading: boolean;
  style?: Record<string, any>;
  fetchMore: (args?: any) => void | any;
  onDelete: (args?: any) => void | any;
  onSelectRow?: (item: ExtractType) => void;
  selectedId?: string;
}

const styles = {
  container: {
    flex: 1,
    width: "100%",
    overflowY: "auto" as const,
    background: "white",
    borderRadius: "12px",
    boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
  },
  table: {
    width: "100%",
    borderCollapse: "separate" as const,
    borderSpacing: "0",
    fontSize: "0.9rem",
    isolation: "isolate" as const,
  },
  headerRow: {
    position: "sticky" as const,
    top: 0,
    background: "white",
    zIndex: 10,
    boxShadow: "0 1px 2px rgba(0,0,0,0.03)",
  },
  headerCell: {
    padding: "1rem",
    fontWeight: 600,
    color: "#1a202c",
    textAlign: "left" as const,
    borderBottom: "2px solid #f1f5f9",
    whiteSpace: "nowrap" as const,
    transition: "background-color 0.2s",
  },
  row: {
    position: "relative" as const,
    transition: "all 0.2s cubic-bezier(0.4, 0, 0.2, 1)",
    cursor: "pointer",
    backgroundColor: "white",
  },
  rowHovered: {
    backgroundColor: "#f8fafc",
    transform: "translateY(-1px)",
    boxShadow: "0 4px 12px rgba(0, 0, 0, 0.05)",
    zIndex: 2,
  },
  selectedRow: {
    backgroundColor: "#f0f9ff",
    transform: "translateY(-2px)",
    boxShadow: "0 8px 16px rgba(59, 130, 246, 0.08)",
    zIndex: 3,
  },
  cell: {
    padding: "0.875rem 1rem",
    color: "#475569",
    borderBottom: "1px solid #f1f5f9",
    maxWidth: "300px",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap" as const,
    transition: "all 0.2s cubic-bezier(0.4, 0, 0.2, 1)",
    backgroundColor: "inherit",
  },
  nameCell: {
    color: "#1a202c",
    fontWeight: 500,
    display: "flex",
    alignItems: "center",
    gap: "0.5rem",
  },
  status: {
    display: "inline-flex",
    alignItems: "center",
    gap: "0.375rem",
    padding: "0.25rem 0.625rem",
    borderRadius: "9999px",
    fontSize: "0.75rem",
    fontWeight: 500,
    textTransform: "uppercase",
    letterSpacing: "0.05em",
  },
  actions: {
    display: "flex",
    justifyContent: "flex-end",
    gap: "0.5rem",
    opacity: 0.4,
    transition: "opacity 0.2s ease",
  },
  actionIcon: {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    width: "24px",
    height: "24px",
    padding: "0",
    border: "none",
    borderRadius: "50%",
    cursor: "pointer",
    background: "transparent",
    color: "#64748b",
    transition: "all 0.2s ease",
    "&:hover": {
      transform: "translateY(-1px)",
    },
    "&.view": {
      "&:hover": {
        color: "#3b82f6",
      },
    },
    "&.delete": {
      "&:hover": {
        color: "#ef4444",
      },
    },
    "&.play": {
      "&:hover": {
        color: "#059669",
      },
    },
  } as React.CSSProperties,
  loadingOverlay: {
    position: "absolute" as const,
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    background: "rgba(255,255,255,0.8)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 20,
  },
  emptyState: {
    padding: "3rem",
    textAlign: "center" as const,
    color: "#64748b",
  },
  icon: {
    width: "14px",
    height: "14px",
    strokeWidth: 2,
  },
  statusIcon: {
    width: "14px",
    height: "14px",
    strokeWidth: 2.5,
  },
};

export function ExtractList({
  items,
  pageInfo,
  loading,
  style,
  fetchMore,
  onDelete,
  onSelectRow,
  selectedId,
}: ExtractListProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [deleteModalOpen, setDeleteModalOpen] = useState<boolean>(false);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);

  const [startExtract] = useMutation(REQUEST_START_EXTRACT, {
    onCompleted: (data) => {
      // Update the local instance with the new status
      if (items) {
        const updatedItems = items.map((item) =>
          item.id === data.startExtract.obj.id
            ? { ...item, ...data.startExtract.obj }
            : item
        );
        // This will trigger a re-render with the updated status
        items.splice(0, items.length, ...updatedItems);
      }
    },
  });

  const handleStartExtract = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    startExtract({ variables: { extractId: id } });
  };

  const handleUpdate = () => {
    if (!loading && pageInfo?.hasNextPage) {
      fetchMore({
        variables: {
          limit: 20,
          cursor: pageInfo.endCursor,
        },
      });
    }
  };

  const getStatusConfig = (
    item: ExtractType
  ): {
    color: string;
    bgColor: string;
    text: string;
    icon: React.ReactNode;
  } => {
    if (item.error)
      return {
        color: "#dc2626",
        bgColor: "#fef2f2",
        text: "Error",
        icon: <AlertTriangle style={styles.statusIcon} />,
      };
    if (item.finished)
      return {
        color: "#059669",
        bgColor: "#f0fdf4",
        text: "Completed",
        icon: <CheckCircle2 style={styles.statusIcon} />,
      };
    if (item.started)
      return {
        color: "#d97706",
        bgColor: "#fffbeb",
        text: "Processing",
        icon: <Play style={styles.statusIcon} />,
      };
    return {
      color: "#475569",
      bgColor: "#f8fafc",
      text: "Queued",
      icon: <Clock style={styles.statusIcon} />,
    };
  };

  const formatDateTime = (dateString?: string) => {
    if (!dateString) return "—";
    const date = new Date(dateString);
    return date.toLocaleString([], {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const ActionButton = ({
    icon: Icon,
    onClick,
    className,
  }: {
    icon: React.ComponentType<any>;
    onClick: (e: React.MouseEvent) => void;
    className?: string;
  }) => (
    <button className={className} style={styles.actionIcon} onClick={onClick}>
      <Icon style={styles.icon} />
    </button>
  );

  const handleDeleteClick = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setPendingDeleteId(id);
    setDeleteModalOpen(true);
  };

  const handleConfirmDelete = () => {
    if (pendingDeleteId) {
      onDelete(pendingDeleteId);
      setDeleteModalOpen(false);
      setPendingDeleteId(null);
    }
  };

  return (
    <>
      <div ref={containerRef} style={{ ...styles.container, ...(style || {}) }}>
        <table style={styles.table}>
          <thead>
            <tr style={styles.headerRow}>
              <th style={{ ...styles.headerCell, width: "30%" }}>Name</th>
              <th style={styles.headerCell}>Status</th>
              <th style={styles.headerCell}>Created</th>
              <th style={styles.headerCell}>Started</th>
              <th style={styles.headerCell}>Completed</th>
              <th
                style={{
                  ...styles.headerCell,
                  width: "100px",
                  textAlign: "right" as const,
                }}
              >
                Actions
              </th>
            </tr>
          </thead>
          <tbody>
            {items?.map((item) => {
              const status = getStatusConfig(item);
              const isSelected = selectedId === item.id;
              const isHovered = hoveredId === item.id;
              const canStart = !item.started && !item.finished && !item.error;

              return (
                <tr
                  key={item.id}
                  style={{
                    ...styles.row,
                    ...(isHovered ? styles.rowHovered : {}),
                    ...(isSelected ? styles.selectedRow : {}),
                  }}
                  onMouseEnter={() => setHoveredId(item.id)}
                  onMouseLeave={() => setHoveredId(null)}
                  onClick={() => onSelectRow?.(item)}
                >
                  <td style={{ ...styles.cell, ...styles.nameCell }}>
                    <FileText style={styles.icon} />
                    {item.name || "Untitled Extract"}
                  </td>
                  <td style={styles.cell}>
                    <span
                      style={
                        {
                          ...styles.status,
                          color: status.color,
                          backgroundColor: status.bgColor,
                        } as React.CSSProperties
                      }
                    >
                      {status.icon}
                      {status.text}
                    </span>
                  </td>
                  <td style={styles.cell}>
                    {formatDateTime(item.created || undefined)}
                  </td>
                  <td style={styles.cell}>
                    {formatDateTime(item.started || undefined)}
                  </td>
                  <td style={styles.cell}>
                    {formatDateTime(item.finished || undefined)}
                  </td>
                  <td style={{ ...styles.cell, textAlign: "right" }}>
                    <div style={styles.actions}>
                      {canStart && (
                        <ActionButton
                          icon={Play}
                          className="play"
                          onClick={(e) => handleStartExtract(item.id, e)}
                        />
                      )}
                      <ActionButton
                        icon={Eye}
                        className="view"
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectRow?.(item);
                        }}
                      />
                      <ActionButton
                        icon={Trash2}
                        className="delete"
                        onClick={(e) => handleDeleteClick(item.id, e)}
                      />
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>

        {loading && items?.length === 0 && (
          <div style={styles.loadingOverlay}>
            <Spinner size={24} />
          </div>
        )}

        {!loading && items?.length === 0 && (
          <div style={styles.emptyState}>
            <FileText
              size={24}
              style={{ marginBottom: "1rem", opacity: 0.5 }}
            />
            <p>No extracts found</p>
          </div>
        )}

        <FetchMoreOnVisible fetchNextPage={handleUpdate} />
      </div>

      <Modal
        size="tiny"
        open={deleteModalOpen}
        onClose={() => setDeleteModalOpen(false)}
        style={{ borderRadius: "12px", padding: "1.5rem" }}
      >
        <Modal.Header
          style={{ borderBottom: "1px solid #f1f5f9", paddingBottom: "1rem" }}
        >
          Confirm Delete
        </Modal.Header>
        <Modal.Content>
          <p style={{ color: "#475569" }}>
            Are you sure you want to delete this extract? This action cannot be
            undone.
          </p>
        </Modal.Content>
        <Modal.Actions
          style={{ borderTop: "1px solid #f1f5f9", paddingTop: "1rem" }}
        >
          <Button
            variant="ghost"
            onClick={() => setDeleteModalOpen(false)}
            style={{
              borderRadius: "6px",
              border: "1px solid #e2e8f0",
            }}
          >
            Cancel
          </Button>
          <Button
            variant="danger"
            onClick={handleConfirmDelete}
            style={{
              borderRadius: "6px",
              marginLeft: "0.75rem",
            }}
          >
            Delete
          </Button>
        </Modal.Actions>
      </Modal>
    </>
  );
}
