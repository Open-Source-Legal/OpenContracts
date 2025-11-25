import { useEffect, useCallback, useState } from "react";
import _ from "lodash";
import { toast } from "react-toastify";
import { useMutation, useQuery, useReactiveVar } from "@apollo/client";
import { useLocation, useNavigate } from "react-router-dom";
import { Button, Icon, Popup, Segment } from "semantic-ui-react";
import styled from "styled-components";
import {
  DndContext,
  DragEndEvent,
  DragStartEvent,
  PointerSensor,
  useSensor,
  useSensors,
  closestCenter,
} from "@dnd-kit/core";
import { navigateToDocument } from "../../utils/navigationUtils";
import useWindowDimensions from "../hooks/WindowDimensionHook";

import { DocumentCards } from "../../components/documents/DocumentCards";
import { DocumentMetadataGrid } from "../../components/documents/DocumentMetadataGrid";
import { FolderCard } from "../corpuses/folders/FolderCard";

import {
  selectedDocumentIds,
  documentSearchTerm,
  authToken,
  filterToLabelId,
  selectedMetaAnnotationId,
  showUploadNewDocumentsModal,
  uploadModalPreloadedFiles,
  openedCorpus,
  selectedFolderId,
} from "../../graphql/cache";
import {
  GET_CORPUS_FOLDERS,
  GetCorpusFoldersInputs,
  GetCorpusFoldersOutputs,
  MOVE_DOCUMENT_TO_FOLDER,
  MoveDocumentToFolderInputs,
  MoveDocumentToFolderOutputs,
  buildFolderTree,
} from "../../graphql/queries/folders";
import {
  REMOVE_DOCUMENTS_FROM_CORPUS,
  RemoveDocumentsFromCorpusOutputs,
  RemoveDocumentsFromCorpusInputs,
} from "../../graphql/mutations";
import {
  RequestDocumentsInputs,
  RequestDocumentsOutputs,
  GET_DOCUMENTS,
} from "../../graphql/queries";
import { DocumentType } from "../../types/graphql-api";
import { FileUploadPackageProps } from "../widgets/modals/DocumentUploadModal";
import { openedDocument } from "../../graphql/cache";

const ViewToggleContainer = styled.div`
  position: absolute;
  top: 1rem;
  right: 1rem;
  z-index: 100;

  @media (max-width: 768px) {
    top: 0.75rem;
    right: 0.75rem;
  }
`;

const ViewToggleButton = styled(Button)`
  &&& {
    background: white;
    border: 1px solid #e2e8f0;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    padding: 0.75rem;
    min-width: auto;
    transition: all 0.2s ease;

    &:hover {
      background: #f8fafc;
      border-color: #cbd5e1;
      transform: translateY(-1px);
      box-shadow: 0 2px 4px rgba(0, 0, 0, 0.12);
    }

    &.active {
      background: #3b82f6;
      color: white;
      border-color: #3b82f6;

      &:hover {
        background: #2563eb;
        border-color: #2563eb;
      }
    }

    @media (max-width: 768px) {
      padding: 0.625rem;

      .icon {
        font-size: 1rem;
      }
    }
  }
`;

export const CorpusDocumentCards = ({
  opened_corpus_id,
}: {
  opened_corpus_id: string | null;
}) => {
  const { width } = useWindowDimensions();
  const isMobile = width <= 768;

  const [viewMode, setViewMode] = useState<
    "modern-card" | "modern-list" | "grid"
  >(isMobile ? "modern-list" : "modern-card");

  /**
   * Similar to AnnotationCorpusCards, this component wraps the DocumentCards component
   * (which is a pure rendering component) with some query logic for a given corpus_id.
   * If the corpus_id is passed in, it will query and display the documents for
   * that corpus and let you browse them.
   */

  const selected_document_ids = useReactiveVar(selectedDocumentIds);
  const document_search_term = useReactiveVar(documentSearchTerm);
  const selected_metadata_id_to_filter_on = useReactiveVar(
    selectedMetaAnnotationId
  );

  const auth_token = useReactiveVar(authToken);
  const filter_to_label_id = useReactiveVar(filterToLabelId);
  const selected_folder_id = useReactiveVar(selectedFolderId);

  const location = useLocation();
  const navigate = useNavigate();

  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  // Setup document queries and mutations
  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  // Note: openedCorpus is set by CentralRouteManager when on /c/:user/:corpus route
  // This component just reads it for context (e.g., file uploads)

  const queryVariables = {
    ...(opened_corpus_id
      ? {
          annotateDocLabels: true,
          inCorpusWithId: opened_corpus_id,
          includeMetadata: true,
        }
      : { annotateDocLabels: false, includeMetadata: false }),
    ...(selected_metadata_id_to_filter_on
      ? { hasAnnotationsWithIds: selected_metadata_id_to_filter_on }
      : {}),
    ...(filter_to_label_id ? { hasLabelWithId: filter_to_label_id } : {}),
    ...(document_search_term ? { textSearch: document_search_term } : {}),
    // ALWAYS pass inFolderId to filter by folder
    // null = root level only, string = specific folder only
    inFolderId: selected_folder_id ?? undefined,
  };

  console.log("[QUERY] GET_DOCUMENTS variables:", queryVariables);

  const {
    refetch: refetchDocuments,
    loading: documents_loading,
    error: documents_error,
    data: documents_response,
    fetchMore: fetchMoreDocuments,
  } = useQuery<RequestDocumentsOutputs, RequestDocumentsInputs>(GET_DOCUMENTS, {
    variables: queryVariables,
    fetchPolicy: "cache-and-network", // Ensure fresh results when search term changes
    notifyOnNetworkStatusChange: true, // necessary in order to trigger loading signal on fetchMore
  });
  if (documents_error) {
    toast.error("ERROR\nCould not fetch documents for corpus.");
  }

  // Fetch folders for current directory
  const {
    loading: folders_loading,
    error: folders_error,
    data: folders_response,
  } = useQuery<GetCorpusFoldersOutputs, GetCorpusFoldersInputs>(
    GET_CORPUS_FOLDERS,
    {
      variables: { corpusId: opened_corpus_id || "" },
      skip: !opened_corpus_id,
      fetchPolicy: "cache-and-network",
    }
  );

  if (folders_error) {
    toast.error("ERROR\nCould not fetch folders for corpus.");
  }

  // Filter folders to show only direct children of current folder
  const current_folder_children =
    folders_response?.corpusFolders.filter((folder) => {
      if (selected_folder_id) {
        return folder.parent?.id === selected_folder_id;
      } else {
        return !folder.parent; // Root level folders
      }
    }) || [];

  // Build tree for folder cards
  const current_folder_tree = buildFolderTree(current_folder_children);

  // REMOVED: All manual refetch effects
  // useQuery automatically refetches when variables change (document_search_term,
  // selected_metadata_id_to_filter_on, filter_to_label_id, opened_corpus_id)
  // These manual refetches were causing excessive server requests

  const [removeDocumentsFromCorpus, {}] = useMutation<
    RemoveDocumentsFromCorpusOutputs,
    RemoveDocumentsFromCorpusInputs
  >(REMOVE_DOCUMENTS_FROM_CORPUS, {
    onCompleted: () => {
      refetchDocuments();
    },
  });

  const [moveDocumentToFolder] = useMutation<
    MoveDocumentToFolderOutputs,
    MoveDocumentToFolderInputs
  >(MOVE_DOCUMENT_TO_FOLDER, {
    onCompleted: () => {
      refetchDocuments();
    },
  });

  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  // Drag-and-drop setup
  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  const [activeDragId, setActiveDragId] = useState<string | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8, // Require 8px movement before drag starts
      },
    })
  );

  const handleDragStart = useCallback((event: DragStartEvent) => {
    setActiveDragId(event.active.id as string);
  }, []);

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event;
      setActiveDragId(null);

      if (!over || active.id === over.id) {
        return;
      }

      const dragData = active.data.current;
      const dropData = over.data.current;

      // Only handle document drops on folder cards in this component
      if (dragData?.type !== "document") {
        return; // Folder-to-folder handled by sidebar
      }

      const documentId = dragData.documentId;
      let targetFolderId: string | null;

      if (dropData?.type === "folder") {
        targetFolderId = dropData.folderId;
      } else {
        return; // Not a valid drop target
      }

      moveDocumentToFolder({
        variables: {
          documentId,
          corpusId: opened_corpus_id || "",
          folderId: targetFolderId,
        },
      })
        .then((result) => {
          if (result.data?.moveDocumentToFolder.ok) {
            toast.success("Document moved to folder");
          } else {
            toast.error(
              result.data?.moveDocumentToFolder.message ||
                "Failed to move document"
            );
          }
        })
        .catch((error) => {
          toast.error(`Error moving document: ${error.message}`);
        });
    },
    [moveDocumentToFolder, opened_corpus_id]
  );

  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  // Query to shape item data
  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  const document_data = documents_response?.documents?.edges
    ? documents_response.documents.edges
    : [];
  const document_items = document_data
    .map((edge) => (edge?.node ? edge.node : undefined))
    .filter((item): item is DocumentType => !!item);

  console.log(
    "[QUERY] GET_DOCUMENTS returned",
    document_items.length,
    "documents for folderId:",
    selected_folder_id
  );

  const handleRemoveContracts = (delete_ids: string[]) => {
    removeDocumentsFromCorpus({
      variables: {
        corpusId: opened_corpus_id ? opened_corpus_id : "",
        documentIdsToRemove: delete_ids,
      },
    })
      .then(() => {
        selectedDocumentIds([]);
        toast.success("SUCCESS! Contracts removed.");
      })
      .catch(() => {
        selectedDocumentIds([]);
        toast.error("ERROR! Contract removal failed.");
      });
  };

  const onSelect = (document: DocumentType) => {
    // console.log("On selected document", document);
    if (selected_document_ids.includes(document.id)) {
      // console.log("Already selected... deselect")
      const values = selected_document_ids.filter((id) => id !== document.id);
      // console.log("Filtered values", values);
      selectedDocumentIds(values);
    } else {
      selectedDocumentIds([...selected_document_ids, document.id]);
    }
    // console.log("selected doc ids", selected_document_ids);
  };

  const onOpen = (document: DocumentType) => {
    // Use smart navigation utility to prefer slugs and prevent redirects
    const corpusData = opened_corpus_id ? openedCorpus() : null;
    navigateToDocument(
      document as any,
      corpusData as any,
      navigate,
      window.location.pathname
    );
  };

  const onDrop = useCallback((acceptedFiles: File[]) => {
    const filePackages: FileUploadPackageProps[] = acceptedFiles.map(
      (file) => ({
        file,
        formData: {
          title: file.name,
          description: `Content summary for ${file.name}`,
        },
      })
    );
    showUploadNewDocumentsModal(true);
    uploadModalPreloadedFiles(filePackages);
  }, []);

  // Build folder cards to show before documents
  const folderCards = current_folder_tree.map((folder) => (
    <FolderCard
      key={folder.id}
      folder={folder}
      viewMode={viewMode === "modern-list" ? "modern-list" : "modern-card"}
    />
  ));

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
    >
      <div
        style={{
          flex: 1,
          height: "100%",
          width: "100%",
          position: "relative",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
        <ViewToggleContainer>
          <Button.Group>
            <Popup
              content="Card View"
              trigger={
                <ViewToggleButton
                  icon="grid layout"
                  active={viewMode === "modern-card"}
                  onClick={() => setViewMode("modern-card")}
                  data-testid="card-view-button"
                />
              }
            />
            <Popup
              content="List View"
              trigger={
                <ViewToggleButton
                  icon="list"
                  active={viewMode === "modern-list"}
                  onClick={() => setViewMode("modern-list")}
                  data-testid="list-view-button"
                />
              }
            />
            <Popup
              content="Table View"
              trigger={
                <ViewToggleButton
                  icon="table"
                  active={viewMode === "grid"}
                  onClick={() => setViewMode("grid")}
                  data-testid="grid-view-button"
                />
              }
            />
          </Button.Group>
        </ViewToggleContainer>

        <div
          id="corpus-document-card-content-container"
          style={{
            flex: 1,
            position: "relative",
            overflow: "hidden",
            minHeight: 0,
            display: "flex",
            flexDirection: "column",
          }}
        >
          {viewMode !== "grid" ? (
            <DocumentCards
              items={document_items}
              loading={documents_loading}
              loading_message="Documents Loading..."
              pageInfo={documents_response?.documents.pageInfo}
              containerStyle={{
                height: "100%",
                display: "flex",
                flexDirection: "column",
                paddingTop: "3.5rem", // Add padding to prevent overlap with view toggle buttons
              }}
              style={{
                flex: 1,
                minHeight: 0,
                overflowY: "auto",
              }}
              fetchMore={fetchMoreDocuments}
              onShiftClick={onSelect}
              onClick={onOpen}
              removeFromCorpus={
                opened_corpus_id ? handleRemoveContracts : undefined
              }
              onDrop={onDrop}
              viewMode={viewMode}
              prefixItems={folderCards}
            />
          ) : (
            <div
              style={{
                paddingTop: "3.5rem",
                height: "100%",
                display: "flex",
                flexDirection: "column",
              }}
            >
              <DocumentMetadataGrid
                corpusId={opened_corpus_id || ""}
                documents={document_items}
                loading={documents_loading}
                onDocumentClick={onOpen}
                pageInfo={documents_response?.documents.pageInfo}
                fetchMore={fetchMoreDocuments}
                hasMore={
                  documents_response?.documents.pageInfo?.hasNextPage ?? false
                }
              />
            </div>
          )}
        </div>
      </div>
    </DndContext>
  );
};
