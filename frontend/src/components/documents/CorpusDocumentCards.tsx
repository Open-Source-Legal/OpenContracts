import { useCallback, useEffect, useMemo } from "react";
import { toast } from "react-toastify";
import { notifyTransientNetworkError } from "../../utils/networkNotifications";
import { useMutation, useQuery, useReactiveVar } from "@apollo/client";
import { useNavigate } from "react-router-dom";

import { navigateToDocument } from "../../utils/navigationUtils";
import { DEFAULT_LIST_PAGE_SIZE } from "../../assets/configurations/constants";
import { DocumentCards } from "../../components/documents/DocumentCards";
import { DocumentMetadataGrid } from "../../components/documents/DocumentMetadataGrid";
import { FolderCard } from "../corpuses/folders/FolderCard";
import { ParentFolderCard } from "../corpuses/folders/ParentFolderCard";
import { ViewMode } from "../corpuses/folders/FolderDocumentBrowser";

import {
  selectedDocumentIds,
  documentSearchTerm,
  filterToLabelId,
  selectedMetaAnnotationId,
  showUploadNewDocumentsModal,
  uploadModalPreloadedFiles,
  openedCorpus,
  selectedFolderId,
  linkDocumentsModalState,
  currentViewTotalDocumentCount,
  documentsLoading as documentsLoadingVar,
} from "../../graphql/cache";
import { evictCorpusDocumentCaches } from "../../graphql/cacheEvictions";
import {
  GET_CORPUS_FOLDERS,
  GetCorpusFoldersInputs,
  GetCorpusFoldersOutputs,
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
  GET_CORPUS_ARTICLE,
  GetCorpusArticleInput,
  GetCorpusArticleOutput,
} from "../../graphql/queries";
import { CreateArticlePlaceholder } from "./CreateArticlePlaceholder";
import {
  CAML_ARTICLE_FILENAME,
  MARKDOWN_MIME_TYPE,
} from "../../assets/configurations/constants";
import { DocumentType } from "../../types/graphql-api";
import { FileUploadPackageProps } from "../widgets/modals/DocumentUploadModal";

interface CorpusDocumentCardsProps {
  opened_corpus_id: string | null;
  viewMode?: ViewMode;
  onOpenArticleEditor?: () => void;
  canUpdate?: boolean;
}

export const CorpusDocumentCards = ({
  opened_corpus_id,
  viewMode = "modern-list",
  onOpenArticleEditor,
  canUpdate = false,
}: CorpusDocumentCardsProps) => {
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
  const filter_to_label_id = useReactiveVar(filterToLabelId);
  const selected_folder_id = useReactiveVar(selectedFolderId);

  // Check if Readme.CAML already exists (for placeholder tile)
  const articleQueryVars = useMemo<GetCorpusArticleInput>(
    () => ({
      corpusId: opened_corpus_id || "",
      title: CAML_ARTICLE_FILENAME,
    }),
    [opened_corpus_id]
  );

  const { data: articleData } = useQuery<
    GetCorpusArticleOutput,
    GetCorpusArticleInput
  >(GET_CORPUS_ARTICLE, {
    variables: articleQueryVars,
    skip: !opened_corpus_id,
  });

  const hasArticle =
    (articleData?.documents?.edges?.length ?? 0) > 0 &&
    !!articleData?.documents?.edges[0]?.node?.txtExtractFile;

  const navigate = useNavigate();

  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  // Setup document queries and mutations
  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  // Note: openedCorpus is set by CentralRouteManager when on /c/:user/:corpus route
  // This component just reads it for context (e.g., file uploads)

  const queryVariables = {
    // Bound the FIRST page (fetchMore already pages at DEFAULT_LIST_PAGE_SIZE).
    // Without this the initial query is unbounded and graphene returns up to
    // RELAY_CONNECTION_MAX_LIMIT (100) documents — each signing pdf+icon URLs
    // on GCS, which is the dominant cost of the first paint. Subsequent pages
    // load on scroll via fetchMore.
    limit: DEFAULT_LIST_PAGE_SIZE,
    ...(opened_corpus_id
      ? {
          annotateDocLabels: true,
          inCorpusWithId: opened_corpus_id,
          includeMetadata: true,
          includeCaml: true,
          // Folder filter is descendant-aware (see DocumentFilter.in_folder):
          // null (no folder selected) = "__root__" = every document in the
          //   corpus, regardless of folder nesting.
          // string = a specific folder ID = documents in that folder and all
          //   of its sub-folders.
          // Note: invalid folder IDs return 0 results (no validation performed).
          inFolderId:
            selected_folder_id === null ? "__root__" : selected_folder_id,
        }
      : { annotateDocLabels: false, includeMetadata: false }),
    ...(selected_metadata_id_to_filter_on
      ? { hasAnnotationsWithIds: selected_metadata_id_to_filter_on }
      : {}),
    ...(filter_to_label_id ? { hasLabelWithId: filter_to_label_id } : {}),
    ...(document_search_term ? { textSearch: document_search_term } : {}),
  };

  const {
    loading: documents_loading,
    networkStatus: documents_network_status,
    error: documents_error,
    data: documents_response,
    fetchMore: fetchMoreDocuments,
  } = useQuery<RequestDocumentsOutputs, RequestDocumentsInputs>(GET_DOCUMENTS, {
    variables: queryVariables,
    fetchPolicy: "cache-and-network", // Ensure fresh results when search term changes
    notifyOnNetworkStatusChange: true, // necessary in order to trigger loading signal on fetchMore
  });
  if (documents_error) {
    notifyTransientNetworkError(
      "ERROR\nCould not fetch documents for corpus.",
      {
        toastId: "fetch-documents-error",
      }
    );
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
    notifyTransientNetworkError("ERROR\nCould not fetch folders for corpus.", {
      toastId: "fetch-folders-error",
    });
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
    // Evict the document list, folder tree (sidebar doc counts), Select-All id
    // list, and trash view so all of them refetch after a per-card removal.
    update: (cache) => evictCorpusDocumentCaches(cache),
  });

  // Note: moveDocumentToFolder mutation is now handled by FolderDocumentBrowser
  // which wraps this component in a DndContext with unified drag-drop handling

  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  // Query to shape item data
  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  // Memoize on the stable Apollo edges reference so identity only changes
  // when the query result itself changes.
  const document_items = useMemo<DocumentType[]>(() => {
    const edges = documents_response?.documents?.edges ?? [];
    return edges
      .map((edge) => (edge?.node ? edge.node : undefined))
      .filter((item): item is DocumentType => !!item);
  }, [documents_response?.documents?.edges]);

  // Publish the TOTAL number of documents matching the current view filters
  // (the connection's totalCount, NOT just the loaded page) so the toolbar can
  // show "X of N" and drive the all-selected state. "Select All" itself fetches
  // the full id set on demand via GET_CORPUS_DOCUMENT_IDS, so the count here is
  // all the toolbar needs from this component.
  //
  // Under cache-and-network Apollo keeps the previous `data` during a refetch,
  // so totalCount stays stable instead of flickering to 0. Only write when the
  // value actually changes; reset to 0 on unmount via a separate []-deps effect
  // (returning a cleanup from the main effect would double-write per change).
  const total_document_count = documents_response?.documents?.totalCount ?? 0;
  useEffect(() => {
    if (currentViewTotalDocumentCount() !== total_document_count) {
      currentViewTotalDocumentCount(total_document_count);
    }
  }, [total_document_count]);
  useEffect(
    () => () => {
      currentViewTotalDocumentCount(0);
    },
    []
  );

  // Sync loading state to reactive var. Same rule: no cleanup-then-set on
  // dep change, and skip identical writes so we don't notify subscribers
  // for no-op transitions.
  useEffect(() => {
    if (documentsLoadingVar() !== documents_loading) {
      documentsLoadingVar(documents_loading);
    }
  }, [documents_loading]);
  useEffect(
    () => () => {
      documentsLoadingVar(false);
    },
    []
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
    // CAML articles open in the article editor, not the document viewer
    if (
      document.title === CAML_ARTICLE_FILENAME &&
      document.fileType === MARKDOWN_MIME_TYPE &&
      onOpenArticleEditor
    ) {
      onOpenArticleEditor();
      return;
    }

    // Use smart navigation utility to prefer slugs and prevent redirects
    const corpusData = opened_corpus_id ? openedCorpus() : null;
    navigateToDocument(
      document as any,
      corpusData as any,
      navigate,
      window.location.pathname
    );
  };

  // Handler for linking a document to another (via context menu)
  const onLinkToDocument = useCallback((document: DocumentType) => {
    linkDocumentsModalState({
      open: true,
      initialSourceIds: [document.id],
      initialTargetIds: [],
    });
  }, []);

  // Handler for drag-and-drop document linking (source dropped onto target)
  const onDocumentDrop = useCallback(
    (sourceDocId: string, targetDocId: string) => {
      // Don't allow linking a document to itself
      if (sourceDocId === targetDocId) return;

      linkDocumentsModalState({
        open: true,
        initialSourceIds: [sourceDocId],
        initialTargetIds: [targetDocId],
      });
    },
    []
  );

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

  // Get parent folder info for navigation (if we're inside a subfolder)
  const currentFolder = folders_response?.corpusFolders.find(
    (f) => f.id === selected_folder_id
  );
  const parentFolderId = currentFolder?.parent?.id || null;
  const parentFolderName = currentFolder?.parent?.name || "Documents";

  // Build prefix items: ParentFolderCard (if in subfolder) + folder cards
  const prefixItems: React.ReactNode[] = [];

  // Add ".." card if we're inside a subfolder
  if (selected_folder_id) {
    prefixItems.push(
      <ParentFolderCard
        key="parent-folder"
        parentFolderId={parentFolderId}
        parentFolderName={parentFolderName}
        viewMode={viewMode === "modern-list" ? "modern-list" : "modern-card"}
      />
    );
  }

  // Add folder cards for current directory's children
  current_folder_tree.forEach((folder) => {
    prefixItems.push(
      <FolderCard
        key={folder.id}
        folder={folder}
        viewMode={viewMode === "modern-list" ? "modern-list" : "modern-card"}
      />
    );
  });

  // Add "Create article" placeholder if no Readme.CAML exists and user can edit
  if (!hasArticle && canUpdate && onOpenArticleEditor && !selected_folder_id) {
    prefixItems.push(
      <CreateArticlePlaceholder
        key="create-article"
        viewMode={viewMode === "modern-list" ? "modern-list" : "modern-card"}
        onClick={onOpenArticleEditor}
      />
    );
  }

  // Note: DndContext is now provided by FolderDocumentBrowser parent component
  // View toggles are now in the FolderDocumentBrowser toolbar
  return (
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
            networkStatus={documents_network_status}
            loading_message="Documents Loading..."
            pageInfo={documents_response?.documents.pageInfo}
            containerStyle={{
              height: "100%",
              display: "flex",
              flexDirection: "column",
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
            prefixItems={prefixItems}
            onLinkToDocument={onLinkToDocument}
            onDocumentDrop={onDocumentDrop}
          />
        ) : (
          <div
            style={{
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
  );
};
