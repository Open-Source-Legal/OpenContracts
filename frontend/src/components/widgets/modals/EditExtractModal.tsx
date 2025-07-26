import {
  ModalContent,
  Button,
  Modal,
  Icon,
  Dimmer,
  Loader,
} from "semantic-ui-react";
import {
  ColumnType,
  DatacellType,
  DocumentType,
  ExtractType,
} from "../../../types/graphql-api";
import {
  useMutation,
  useQuery,
  useReactiveVar,
  NetworkStatus,
} from "@apollo/client";
import {
  RequestGetExtractOutput,
  REQUEST_GET_EXTRACT,
  RequestGetExtractInput,
} from "../../../graphql/queries";
import { useEffect, useState, useCallback, useRef } from "react";
import {
  REQUEST_ADD_DOC_TO_EXTRACT,
  REQUEST_CREATE_COLUMN,
  REQUEST_DELETE_COLUMN,
  REQUEST_REMOVE_DOC_FROM_EXTRACT,
  REQUEST_START_EXTRACT,
  RequestAddDocToExtractInputType,
  RequestAddDocToExtractOutputType,
  RequestCreateColumnInputType,
  RequestCreateColumnOutputType,
  RequestDeleteColumnInputType,
  RequestDeleteColumnOutputType,
  RequestRemoveDocFromExtractInputType,
  RequestRemoveDocFromExtractOutputType,
  RequestStartExtractInputType,
  RequestStartExtractOutputType,
  REQUEST_CREATE_FIELDSET,
  RequestCreateFieldsetInputType,
  RequestCreateFieldsetOutputType,
  REQUEST_UPDATE_EXTRACT,
  RequestUpdateExtractInputType,
  RequestUpdateExtractOutputType,
} from "../../../graphql/mutations";
import { toast } from "react-toastify";
import {
  addingColumnToExtract,
  editingColumnForExtract,
} from "../../../graphql/cache";
import {
  ExtractDataGrid,
  ExtractDataGridHandle,
} from "../../extracts/datagrid/DataGrid";
import { CSSProperties } from "react";
import styled from "styled-components";

interface EditExtractModalProps {
  ext: ExtractType | null;
  open: boolean;
  toggleModal: () => void;
}

// Responsive Styled Components
const StyledModal = styled(Modal)`
  &.ui.modal {
    height: 90vh;
    max-height: 90vh !important;
    margin: 5vh auto !important;
    display: flex !important;
    flex-direction: column;
    background: #ffffff;
    overflow: hidden;
    border-radius: 20px;
    box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);

    @media (max-width: 768px) {
      height: 100vh;
      max-height: 100vh !important;
      margin: 0 !important;
      width: 100% !important;
      border-radius: 0;
    }
  }
`;

const ModalHeader = styled.div`
  background: linear-gradient(to right, #f8fafc, #f1f5f9);
  padding: 1.75rem 2rem;
  border-bottom: 1px solid #e2e8f0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
  position: sticky;
  top: 0;
  z-index: 10;
  flex: 0 0 auto;

  @media (max-width: 768px) {
    padding: 1.25rem 1rem;
    flex-wrap: wrap;
  }
`;

const HeaderTitle = styled.div`
  display: flex;
  align-items: center;
  gap: 1rem;

  @media (max-width: 768px) {
    flex-direction: column;
    align-items: flex-start;
    gap: 0.5rem;
    width: 100%;
  }
`;

const ExtractName = styled.h2`
  font-size: 1.75rem;
  font-weight: 700;
  color: #0f172a;
  margin: 0;
  letter-spacing: -0.025em;

  @media (max-width: 768px) {
    font-size: 1.375rem;
  }
`;

const ExtractMeta = styled.span`
  font-size: 0.875rem;
  color: #64748b;
  font-weight: 500;

  @media (max-width: 768px) {
    font-size: 0.8125rem;
  }
`;

const StyledModalContent = styled(ModalContent)`
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
  max-height: calc(90vh - 130px) !important;
  padding: 0 !important;
  background: #fafbfc;

  @media (max-width: 768px) {
    max-height: calc(100vh - 120px) !important;
    background: #ffffff;
  }
`;

const ScrollableContent = styled.div`
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  overflow-x: hidden;
  min-height: 0;
  padding: 1.5rem 2rem;

  @media (max-width: 768px) {
    padding: 1rem;
  }
`;

const ContentWrapper = styled.div`
  display: flex;
  flex-direction: column;
  height: 100%;
  flex: 1 1 auto;
  min-height: 0;
`;

const TopSection = styled.div`
  flex: 0 0 auto;
  padding: 1.5rem 2rem 0;

  @media (max-width: 768px) {
    padding: 1rem 1rem 0;
  }
`;

const GridSection = styled.div`
  flex: 1 1 auto;
  min-height: 0;
  padding: 0 2rem 1.5rem;
  display: flex;
  flex-direction: column;

  @media (max-width: 768px) {
    padding: 0 1rem 1rem;
  }
`;

const StatsContainer = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 1.25rem;
  padding: 0;
  margin: 0 0 1.5rem 0;

  @media (max-width: 640px) {
    grid-template-columns: repeat(2, 1fr);
    gap: 0.75rem;
    margin: 0 0 1rem 0;
  }

  @media (max-width: 480px) {
    grid-template-columns: 1fr 1fr;
    gap: 0.5rem;
  }
`;

const StatCard = styled.div`
  padding: 1.5rem;
  background: #ffffff;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  transition: all 0.2s ease;
  position: relative;
  overflow: hidden;

  &::before {
    content: "";
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 4px;
    background: linear-gradient(to right, #3b82f6, #2563eb);
    opacity: 0;
    transition: opacity 0.2s ease;
  }

  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 16px -4px rgba(0, 0, 0, 0.1);
    border-color: #cbd5e1;

    &::before {
      opacity: 1;
    }
  }

  @media (max-width: 640px) {
    padding: 1rem;

    &:hover {
      transform: none;
    }
  }

  @media (max-width: 480px) {
    padding: 0.75rem;
    border-radius: 8px;
  }
`;

const StatLabel = styled.div`
  font-size: 0.8125rem;
  font-weight: 600;
  color: #64748b;
  margin-bottom: 0.625rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;

  @media (max-width: 640px) {
    font-size: 0.6875rem;
    margin-bottom: 0.375rem;
  }
`;

const StatValue = styled.div`
  font-size: 1.5rem;
  font-weight: 700;
  color: #0f172a;
  display: flex;
  align-items: center;
  gap: 0.75rem;

  .icon {
    opacity: 0.8;
  }

  @media (max-width: 640px) {
    font-size: 1.125rem;
    gap: 0.5rem;

    .icon {
      font-size: 1rem !important;
    }
  }

  @media (max-width: 480px) {
    font-size: 1rem;
  }
`;

const StatusWithButton = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  gap: 0.5rem;

  @media (max-width: 640px) {
    flex-direction: row;
    align-items: center;
    gap: 0.5rem;
  }
`;

const ControlsContainer = styled.div`
  flex: 0 0 auto;
  display: flex;
  justify-content: flex-end;
  gap: 1rem;
  padding: 0 0 1.5rem;
  align-items: center;

  @media (max-width: 640px) {
    justify-content: center;
    flex-wrap: wrap;
    padding: 0 0 0.75rem;
    gap: 0.75rem;
  }
`;

const DataGridContainer = styled.div`
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  position: relative;
  margin: 0;
  border-radius: 16px;
  background: #ffffff;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.06);
  border: 1px solid #e2e8f0;
  overflow: hidden;

  @media (max-width: 768px) {
    min-height: 0;
    border-radius: 12px;
    flex: 1 1 auto;
  }
`;

const ModalActions = styled.div`
  flex: 0 0 auto;
  padding: 1.25rem 2rem !important;
  background: linear-gradient(to top, #f8fafc, #ffffff);
  border-top: 1px solid #e2e8f0;
  position: sticky;
  bottom: 0;
  z-index: 10;
  box-shadow: 0 -4px 12px rgba(0, 0, 0, 0.03);
  display: flex;
  justify-content: flex-end;

  @media (max-width: 768px) {
    padding: 1rem !important;
    justify-content: center;

    button {
      flex: 1;
      max-width: 200px;
    }
  }
`;

const MobileCloseButton = styled.button`
  display: none;
  position: absolute;
  top: 1.25rem;
  right: 1.25rem;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 0;
  cursor: pointer;
  z-index: 11;
  backdrop-filter: blur(8px);
  transition: all 0.2s ease;

  @media (max-width: 768px) {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 44px;
    height: 44px;

    &:active {
      background: #f1f5f9;
      transform: scale(0.95);
    }
  }
`;

const ResponsiveButton = styled(Button)`
  border-radius: 10px !important;
  font-weight: 600 !important;
  letter-spacing: -0.01em !important;
  transition: all 0.2s ease !important;

  @media (max-width: 768px) {
    padding: 14px 28px !important;
    font-size: 1rem !important;
    min-height: 48px;
  }
`;

const DownloadButton = styled(ResponsiveButton)`
  background: #ffffff !important;
  border: 1.5px solid #e2e8f0 !important;
  color: #475569 !important;

  &:hover:not(:disabled) {
    background: #f8fafc !important;
    border-color: #cbd5e1 !important;
    color: #1e293b !important;
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
  }

  &:active:not(:disabled) {
    transform: translateY(0);
  }

  @media (max-width: 640px) {
    width: 100%;
  }
`;

const StatusIcon = styled.div<{ $status?: string }>`
  display: flex;
  align-items: center;
  gap: 0.75rem;

  ${(props) =>
    props.$status === "processing" &&
    `
    color: #3b82f6;
  `}

  ${(props) =>
    props.$status === "completed" &&
    `
    color: #10b981;
  `}
  
  ${(props) =>
    props.$status === "failed" &&
    `
    color: #ef4444;
  `}
  
  ${(props) =>
    props.$status === "not-started" &&
    `
    color: #6b7280;
  `}
  
  @media (max-width: 640px) {
    gap: 0.5rem;

    span {
      font-size: 0.875rem;
    }
  }
`;

const StartButton = styled(Button)`
  background: linear-gradient(135deg, #3b82f6, #2563eb) !important;
  color: white !important;
  border: none !important;
  border-radius: 12px !important;
  width: 44px !important;
  height: 44px !important;
  padding: 0 !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  transition: all 0.3s ease !important;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3) !important;

  &:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 20px rgba(59, 130, 246, 0.4) !important;
    background: linear-gradient(135deg, #2563eb, #1d4ed8) !important;
  }

  &:active {
    transform: translateY(0) !important;
  }

  .icon {
    margin: 0 !important;
  }

  @media (max-width: 640px) {
    width: 36px !important;
    height: 36px !important;
    border-radius: 10px !important;

    .icon {
      font-size: 14px !important;
    }
  }
`;

// Legacy styles for buttons (keeping these as they have complex hover states)
const styles = {
  startButton: {
    width: "40px",
    height: "40px",
    background: "linear-gradient(135deg, #2563eb, #1d4ed8)",
    transition: "all 0.3s ease",
    border: "none",
    padding: "0",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    position: "relative",
    "&:hover": {
      transform: "translateY(-2px)",
      boxShadow: "0 8px 20px -2px rgba(37, 99, 235, 0.35)",
      background: "linear-gradient(135deg, #3b82f6, #2563eb)",
      "& .play-icon": {
        transform: "scale(0)",
        opacity: 0,
      },
      "& .rocket-icon": {
        transform: "scale(1)",
        opacity: 1,
      },
    },
  } as CSSProperties,
  iconBase: {
    position: "absolute",
    fontSize: "16px",
    margin: "0",
    transition: "all 0.3s ease",
  } as CSSProperties,
  playIcon: {
    transform: "scale(1)",
    opacity: 1,
  } as CSSProperties,
  rocketIcon: {
    transform: "scale(0)",
    opacity: 0,
  } as CSSProperties,
  downloadButton: {
    background: "transparent",
    border: "1px solid #e2e8f0",
    borderRadius: "8px",
    padding: "8px 16px",
    display: "flex",
    alignItems: "center",
    gap: "8px",
    color: "#64748b",
    fontSize: "0.875rem",
    fontWeight: 500,
    transition: "all 0.2s ease",
    "&:hover:not(:disabled)": {
      background: "#f8fafc",
      borderColor: "#94a3b8",
      transform: "translateY(-1px)",
      color: "#334155",
      boxShadow: "0 2px 4px rgba(148, 163, 184, 0.1)",
    },
    "&:active:not(:disabled)": {
      transform: "translateY(0)",
    },
    "&:disabled": {
      opacity: 0.5,
      cursor: "not-allowed",
    },
  } as CSSProperties,
  downloadIcon: {
    fontSize: "16px",
    transition: "transform 0.2s ease",
  } as CSSProperties,
};

// Custom hook to detect mobile
const useIsMobile = () => {
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const checkIsMobile = () => {
      setIsMobile(window.innerWidth <= 768);
    };

    checkIsMobile();
    window.addEventListener("resize", checkIsMobile);
    return () => window.removeEventListener("resize", checkIsMobile);
  }, []);

  return isMobile;
};

export const EditExtractModal = ({
  open,
  ext,
  toggleModal,
}: EditExtractModalProps) => {
  const dataGridRef = useRef<ExtractDataGridHandle>(null);
  const isMobile = useIsMobile();

  const [extract, setExtract] = useState<ExtractType | null>(ext);
  const [cells, setCells] = useState<DatacellType[]>([]);
  const [rows, setRows] = useState<DocumentType[]>([]);
  const [columns, setColumns] = useState<ColumnType[]>([]);
  const adding_column_to_extract = useReactiveVar(addingColumnToExtract);
  const editing_column_for_extract = useReactiveVar(editingColumnForExtract);

  useEffect(() => {
    console.log("adding_column_to_extract", adding_column_to_extract);
  }, [adding_column_to_extract]);

  useEffect(() => {
    if (ext) {
      setExtract(ext);
    }
  }, [ext]);

  const [addDocsToExtract, { loading: add_docs_loading }] = useMutation<
    RequestAddDocToExtractOutputType,
    RequestAddDocToExtractInputType
  >(REQUEST_ADD_DOC_TO_EXTRACT, {
    onCompleted: (data) => {
      console.log("Add data to ", data);
      setRows((old_rows) => [
        ...old_rows,
        ...(data.addDocsToExtract.objs as DocumentType[]),
      ]);
      toast.success("SUCCESS! Added docs to extract.");
    },
    onError: (err) => {
      toast.error("ERROR! Could not add docs to extract.");
    },
  });

  const handleAddDocIdsToExtract = (
    extractId: string,
    documentIds: string[]
  ) => {
    addDocsToExtract({
      variables: {
        extractId,
        documentIds,
      },
    });
  };

  const [removeDocsFromExtract, { loading: remove_docs_loading }] = useMutation<
    RequestRemoveDocFromExtractOutputType,
    RequestRemoveDocFromExtractInputType
  >(REQUEST_REMOVE_DOC_FROM_EXTRACT, {
    onCompleted: (data) => {
      toast.success("SUCCESS! Removed docs from extract.");
      console.log("Removed docs and return data", data);
      setRows((old_rows) =>
        old_rows.filter(
          (item) => !data.removeDocsFromExtract.idsRemoved.includes(item.id)
        )
      );
    },
    onError: (err) => {
      toast.error("ERROR! Could not remove docs from extract.");
    },
  });

  const handleRemoveDocIdsFromExtract = (
    extractId: string,
    documentIds: string[]
  ) => {
    removeDocsFromExtract({
      variables: {
        extractId,
        documentIdsToRemove: documentIds,
      },
    });
  };

  const [deleteColumn] = useMutation<
    RequestDeleteColumnOutputType,
    RequestDeleteColumnInputType
  >(REQUEST_DELETE_COLUMN, {
    onCompleted: (data) => {
      toast.success("SUCCESS! Removed column from Extract.");
      setColumns((columns) =>
        columns.filter((item) => item.id !== data.deleteColumn.deletedId)
      );
    },
    onError: (err) => {
      toast.error("ERROR! Could not remove column.");
    },
  });

  const [createFieldset] = useMutation<
    RequestCreateFieldsetOutputType,
    RequestCreateFieldsetInputType
  >(REQUEST_CREATE_FIELDSET);

  const [updateExtract] = useMutation<
    RequestUpdateExtractOutputType,
    RequestUpdateExtractInputType
  >(REQUEST_UPDATE_EXTRACT, {
    onCompleted: () => {
      toast.success("Extract updated with new fieldset.");
      refetch();
    },
    onError: () => {
      toast.error("Failed to update extract with new fieldset.");
    },
  });

  /**
   * Handles the deletion of a column from the extract.
   * If the fieldset is not in use, deletes the column directly.
   * If the fieldset is in use, creates a new fieldset without the column and updates the extract.
   *
   * @param {string} columnId - The ID of the column to delete.
   */
  const handleDeleteColumnIdFromExtract = async (columnId: string) => {
    if (!extract?.fieldset?.id) return;

    if (!extract.fieldset.inUse) {
      // Fieldset is not in use; delete the column directly
      try {
        await deleteColumn({
          variables: {
            id: columnId,
          },
        });
        // Remove the column from local state
        setColumns((prevColumns) =>
          prevColumns.filter((column) => column.id !== columnId)
        );
        // Refetch data to get updated columns
        refetch();
        toast.success("SUCCESS! Removed column from Extract.");
      } catch (error) {
        console.error(error);
        toast.error("Error while deleting column from extract.");
      }
    } else {
      // Fieldset is in use; proceed with existing logic
      try {
        // Step 1: Create a new fieldset
        const { data: fieldsetData } = await createFieldset({
          variables: {
            name: `${extract.fieldset.name} (edited)`,
            description: extract.fieldset.description || "",
          },
        });

        const newFieldsetId = fieldsetData?.createFieldset.obj.id;

        if (!newFieldsetId) throw new Error("Fieldset creation failed.");

        // Step 2: Copy existing columns except the deleted one
        const columnsToCopy = columns.filter((col) => col.id !== columnId);
        await Promise.all(
          columnsToCopy.map((column) =>
            createColumn({
              variables: {
                fieldsetId: newFieldsetId,
                name: column.name,
                query: column.query || "",
                matchText: column.matchText,
                outputType: column.outputType,
                limitToLabel: column.limitToLabel,
                instructions: column.instructions,
                taskName: column.taskName,
              },
            })
          )
        );

        // Step 3: Update the extract to use the new fieldset
        console.log("Updating extract to use new fieldset", newFieldsetId);
        await updateExtract({
          variables: {
            id: extract.id,
            fieldsetId: newFieldsetId,
          },
        });

        // Update local state
        setExtract((prevExtract) =>
          prevExtract
            ? { ...prevExtract, fieldset: fieldsetData.createFieldset.obj }
            : prevExtract
        );

        // Refetch data to get updated columns
        refetch();
      } catch (error) {
        console.error(error);
        toast.error("Error while deleting column from extract.");
      }
    }
  };

  const [createColumn, { loading: create_column_loading }] = useMutation<
    RequestCreateColumnOutputType,
    RequestCreateColumnInputType
  >(REQUEST_CREATE_COLUMN, {
    onCompleted: (data) => {
      toast.success("SUCCESS! Created column.");
      setColumns((columns) => [...columns, data.createColumn.obj]);
      addingColumnToExtract(null);
    },
    onError: (err) => {
      toast.error("ERROR! Could not create column.");
      addingColumnToExtract(null);
    },
  });

  // Define the handler for adding a column
  const handleAddColumn = useCallback(() => {
    if (!extract?.fieldset) return;
    addingColumnToExtract(extract);
  }, [extract?.fieldset]);

  const {
    loading,
    error,
    data: extract_data,
    refetch,
    networkStatus,
  } = useQuery<RequestGetExtractOutput, RequestGetExtractInput>(
    REQUEST_GET_EXTRACT,
    {
      variables: {
        id: extract ? extract.id : "",
      },
      nextFetchPolicy: "network-only",
      notifyOnNetworkStatusChange: true,
    }
  );

  useEffect(() => {
    let pollInterval: NodeJS.Timeout;

    if (extract && extract.started && !extract.finished && !extract.error) {
      // Start polling every 5 seconds
      pollInterval = setInterval(() => {
        refetch({ id: extract.id });
      }, 5000);

      // Set up a timeout to stop polling after 10 minutes
      const timeoutId = setTimeout(() => {
        clearInterval(pollInterval);
        toast.info(
          "Job is taking too long... polling paused after 10 minutes."
        );
      }, 600000);

      // Clean up the interval and timeout when the component unmounts or the extract changes
      return () => {
        clearInterval(pollInterval);
        clearTimeout(timeoutId);
      };
    }
  }, [extract, refetch]);

  useEffect(() => {
    if (open && extract) {
      refetch();
    }
  }, [open]);

  useEffect(() => {
    console.log("XOXO - Extract Data", extract_data);
    if (extract_data) {
      const { fullDatacellList, fullDocumentList, fieldset } =
        extract_data.extract;
      console.log("XOXO - Full Datacell List", fullDatacellList);
      console.log("XOXO - Full Document List", fullDocumentList);
      console.log("XOXO - Fieldset", fieldset);
      setCells(fullDatacellList ? fullDatacellList : []);
      setRows(fullDocumentList ? fullDocumentList : []);
      // Add debug logging here
      console.log("Setting columns to:", fieldset?.fullColumnList);
      setColumns(fieldset?.fullColumnList ? fieldset.fullColumnList : []);
      // Update the extract state with the latest data
      setExtract(extract_data.extract);
    }
  }, [extract_data]);

  const [startExtract, { loading: start_extract_loading }] = useMutation<
    RequestStartExtractOutputType,
    RequestStartExtractInputType
  >(REQUEST_START_EXTRACT, {
    onCompleted: (data) => {
      toast.success("SUCCESS! Started extract.");
      setExtract((old_extract) => {
        return { ...old_extract, ...data.startExtract.obj };
      });
    },
    onError: (err) => {
      toast.error("ERROR! Could not start extract.");
    },
  });

  // Add handler for row updates
  const handleRowUpdate = useCallback((updatedRow: DocumentType) => {
    setRows((prevRows) =>
      prevRows.map((row) => (row.id === updatedRow.id ? updatedRow : row))
    );
  }, []);

  // Adjust isLoading to show loading indicator when data is first loading
  const isLoading =
    loading || create_column_loading || add_docs_loading || remove_docs_loading;

  // Determine if the grid should show loading
  const isGridLoading = extract?.started && !extract.finished && !extract.error;

  if (!extract || !extract.id) {
    return null;
  }

  return (
    <>
      <StyledModal
        id="edit-extract-modal"
        closeIcon={!isMobile}
        size="fullscreen"
        open={open}
        onClose={toggleModal}
        data-testid="edit-extract-modal"
      >
        <ModalHeader>
          <HeaderTitle>
            <ExtractName id="extract-name" data-testid="extract-name">
              {extract.name}
            </ExtractName>
            <ExtractMeta id="extract-meta" data-testid="extract-meta">
              Created by {extract.creator?.email} on{" "}
              {new Date(extract.created).toLocaleDateString()}
            </ExtractMeta>
          </HeaderTitle>
          <MobileCloseButton
            onClick={toggleModal}
            data-testid="close-button-mobile"
          >
            <Icon name="close" size="large" />
          </MobileCloseButton>
        </ModalHeader>

        <StyledModalContent>
          <ContentWrapper>
            <TopSection>
              <StatsContainer>
                <StatCard data-testid="status-card">
                  <StatLabel>Status</StatLabel>
                  <StatValue>
                    {extract.started && !extract.finished && !extract.error ? (
                      <StatusIcon
                        id="status-processing"
                        $status="processing"
                        data-testid="status-processing"
                      >
                        <Icon name="spinner" loading />
                        <span>Processing</span>
                      </StatusIcon>
                    ) : extract.finished ? (
                      <StatusIcon
                        id="status-completed"
                        $status="completed"
                        data-testid="status-completed"
                      >
                        <Icon name="check circle" />
                        <span>Completed</span>
                      </StatusIcon>
                    ) : extract.error ? (
                      <StatusIcon
                        id="status-failed"
                        $status="failed"
                        data-testid="status-failed"
                      >
                        <Icon name="exclamation circle" />
                        <span>Failed</span>
                      </StatusIcon>
                    ) : (
                      <StatusWithButton>
                        <StatusIcon
                          id="status-not-started"
                          $status="not-started"
                          data-testid="status-not-started"
                        >
                          <Icon name="clock outline" />
                          <span>{!isMobile && "Not Started"}</span>
                        </StatusIcon>
                        <StartButton
                          id="start-extract-button"
                          onClick={() =>
                            startExtract({
                              variables: { extractId: extract.id },
                            })
                          }
                          data-testid="start-extract-button"
                        >
                          <Icon name="play" />
                        </StartButton>
                      </StatusWithButton>
                    )}
                  </StatValue>
                </StatCard>

                <StatCard data-testid="docs-card">
                  <StatLabel>Docs</StatLabel>
                  <StatValue>
                    <Icon name="file outline" color="blue" />
                    <span id="docs-count" data-testid="docs-count">
                      {rows.length}
                    </span>
                  </StatValue>
                </StatCard>

                <StatCard data-testid="cols-card">
                  <StatLabel>Cols</StatLabel>
                  <StatValue>
                    <Icon name="columns" color="teal" />
                    <span id="cols-count" data-testid="cols-count">
                      {columns.length}
                    </span>
                  </StatValue>
                </StatCard>

                {extract.corpus && (
                  <StatCard data-testid="corpus-card">
                    <StatLabel>Corpus</StatLabel>
                    <StatValue>
                      <Icon name="database" color="purple" />
                      <span id="corpus-title" data-testid="corpus-title">
                        {extract.corpus.title && isMobile
                          ? extract.corpus.title.substring(0, 10) + "..."
                          : extract.corpus.title || "Untitled"}
                      </span>
                    </StatValue>
                  </StatCard>
                )}
              </StatsContainer>

              <ControlsContainer>
                <DownloadButton
                  id="export-csv-button"
                  basic
                  onClick={() => dataGridRef.current?.exportToCsv()}
                  disabled={
                    loading ||
                    isGridLoading ||
                    networkStatus === NetworkStatus.refetch
                  }
                  data-testid="export-csv-button"
                >
                  <Icon name="download" style={styles.downloadIcon} />
                  {!isMobile && "Export CSV"}
                </DownloadButton>
              </ControlsContainer>
            </TopSection>

            <GridSection>
              <DataGridContainer
                style={{ position: "relative" }}
                id="data-grid-container"
                data-testid="data-grid-container"
              >
                {loading && (
                  <Dimmer
                    id="loading-dimmer"
                    active
                    inverted
                    style={{
                      position: "absolute",
                      margin: 0,
                      borderRadius: "12px",
                    }}
                    data-testid="loading-dimmer"
                  >
                    <Loader>
                      {extract.started && !extract.finished
                        ? "Processing..."
                        : "Loading..."}
                    </Loader>
                  </Dimmer>
                )}
                <ExtractDataGrid
                  ref={dataGridRef}
                  onAddDocIds={handleAddDocIdsToExtract}
                  onRemoveDocIds={handleRemoveDocIdsFromExtract}
                  onRemoveColumnId={handleDeleteColumnIdFromExtract}
                  onUpdateRow={handleRowUpdate}
                  onAddColumn={handleAddColumn}
                  extract={extract}
                  cells={cells}
                  rows={rows}
                  columns={columns}
                  loading={Boolean(isGridLoading)}
                  data-testid="extract-data-grid"
                />
              </DataGridContainer>
            </GridSection>
          </ContentWrapper>
        </StyledModalContent>

        <ModalActions>
          <ResponsiveButton
            id="close-button"
            onClick={toggleModal}
            data-testid="close-button"
          >
            Close
          </ResponsiveButton>
        </ModalActions>
      </StyledModal>
    </>
  );
};
