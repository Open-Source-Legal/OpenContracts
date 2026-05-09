import {
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Button,
} from "@os-legal/ui";
import { useQuery, useReactiveVar } from "@apollo/client";
import _ from "lodash";
import {
  RequestDocumentsOutputs,
  RequestDocumentsInputs,
  SEARCH_DOCUMENTS,
} from "../../../graphql/queries";
import { CardLayout } from "../../layout/CardLayout";
import { DocumentCards } from "../../documents/DocumentCards";
import { CreateAndSearchBar } from "../../layout/CreateAndSearchBar";
import { FilterToLabelsetSelector } from "../model-filters/FilterToLabelsetSelector";
import { FilterToCorpusSelector } from "../model-filters/FilterToCorpusSelector";
import { FilterToLabelSelector } from "../model-filters/FilterToLabelSelector";
import { useCallback, useEffect, useRef, useState } from "react";
import styled from "styled-components";
import {
  CorpusType,
  DocumentType,
  LabelType,
} from "../../../types/graphql-api";
import { LooseObject } from "../../types";
import { selectedDocumentIds } from "../../../graphql/cache";
import {
  showUploadNewDocumentsModal,
  uploadModalPreloadedFiles,
} from "../../../graphql/cache";
import { FileUploadPackageProps } from "./DocumentUploadModal";
import { MODAL_BODY_MAX_HEIGHT } from "../../../assets/configurations/constants";

/**
 * Overrides the nested card styling from CreateAndSearchBar when rendered
 * inside a modal context, and ensures the search input fills available width.
 */
const ModalSearchOverride = styled.div`
  /* Remove the card-in-card appearance from SearchBarContainer (direct child) */
  & > div {
    box-shadow: none;
    border-radius: 0;
    padding: 0.75rem 0;
    background: transparent;
  }

  /* Let search input fill available modal width */
  input {
    max-width: 100% !important;
  }

  @media (max-width: 600px) {
    /* Stack filter icon below search on very small screens */
    & > div {
      flex-wrap: wrap;
      gap: 0.5rem;
    }
  }
`;

interface SelectDocumentsModalProps {
  open: boolean;
  filterDocIds: string[];
  toggleModal: () => void;
  onAddDocumentIds: (documents: string[]) => void;
}

export const SelectDocumentsModal = ({
  open,
  filterDocIds,
  toggleModal,
  onAddDocumentIds,
}: SelectDocumentsModalProps) => {
  const [filtered_to_labelset_id, filterToLabelsetId] = useState<string | null>(
    null
  );
  const [filtered_to_label_id, filterToLabelId] = useState<string | null>(null);
  const [filtered_to_corpus, filterToCorpus] = useState<CorpusType | null>(
    null
  );
  const selected_document_ids = useReactiveVar(selectedDocumentIds);
  const [document_search_term, documentSearchTerm] = useState<string>("");
  const [searchCache, setSearchCache] = useState<string>(document_search_term);

  let document_variables: LooseObject = {
    includeMetadata: true,
  };
  if (document_search_term) {
    document_variables["textSearch"] = document_search_term;
  }

  if (filtered_to_label_id) {
    document_variables["hasLabelWithId"] = filtered_to_label_id;
  }
  if (filtered_to_corpus) {
    document_variables["inCorpusWithId"] = filtered_to_corpus.id;
    document_variables["includeCaml"] = false;
  }
  // Only annotate document labels if there is a selected corpus to cut down on possible explosion of possible labels otherwise.
  if (filtered_to_corpus || filtered_to_labelset_id) {
    document_variables["annotateDocLabels"] = true;
  } else {
    document_variables["annotateDocLabels"] = false;
  }

  const {
    refetch: refetchDocuments,
    loading: documents_loading,
    networkStatus: documents_network_status,
    error: documents_error,
    data: documents_data,
    fetchMore: fetchMoreDocuments,
  } = useQuery<RequestDocumentsOutputs, RequestDocumentsInputs>(
    SEARCH_DOCUMENTS,
    {
      variables: document_variables,
      nextFetchPolicy: "network-only",
      notifyOnNetworkStatusChange: true, // required to get loading signal on fetchMore
    }
  );

  const document_nodes = documents_data?.documents?.edges
    ? documents_data.documents.edges
    : [];
  const document_items = document_nodes
    .map((edge) => (edge?.node ? edge.node : undefined))
    .filter((item): item is DocumentType => !!item)
    .filter((item) => !filterDocIds.includes(item.id));

  // If doc search term changes, refetch documents
  useEffect(() => {
    console.log("document_search_term change");
    refetchDocuments();
  }, [document_search_term]);

  // If selected label changes, refetch docs
  useEffect(() => {
    console.log("filtered_to_label_id change");
    refetchDocuments();
  }, [filtered_to_label_id]);

  // If selected labelSET changes, refetch docs
  useEffect(() => {
    console.log("filter_to_labelset_id change");
    refetchDocuments();
  }, [filtered_to_labelset_id]);

  // If selected corpus changes, refetch docs
  useEffect(() => {
    console.log("filtered_to_corpus change");
    refetchDocuments();
  }, [filtered_to_corpus]);

  /**
   * Set up the debounced search handling for the Document SearchBar
   */
  const debouncedSearch = useRef(
    _.debounce((searchTerm) => {
      documentSearchTerm(searchTerm);
    }, 1000)
  );

  const handleSearchChange = (value: string) => {
    setSearchCache(value);
    debouncedSearch.current(value);
  };

  const handleConfirm = () => {
    onAddDocumentIds(selected_document_ids);
    selectedDocumentIds([]);
    toggleModal();
  };

  const handleCancel = () => {
    selectedDocumentIds([]);
    toggleModal();
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

  return (
    <Modal open={open} onClose={() => toggleModal()} size="fullscreen">
      <ModalHeader>Select Document(s)</ModalHeader>
      <ModalBody
        style={{
          flex: 1,
          overflow: "hidden",
          maxHeight: MODAL_BODY_MAX_HEIGHT,
          padding: "0.5rem 1rem",
        }}
      >
        <CardLayout
          Modals={<></>}
          SearchBar={
            <ModalSearchOverride>
              <CreateAndSearchBar
                actions={[]}
                filters={
                  <>
                    <FilterToLabelsetSelector
                      fixed_labelset_id={
                        filtered_to_corpus?.labelSet?.id
                          ? filtered_to_corpus.labelSet.id
                          : undefined
                      }
                    />
                    <FilterToCorpusSelector
                      uses_labelset_id={filtered_to_labelset_id}
                    />
                    {filtered_to_labelset_id ||
                    filtered_to_corpus?.labelSet?.id ? (
                      <FilterToLabelSelector
                        label_type={LabelType.TokenLabel}
                        only_labels_for_labelset_id={
                          filtered_to_labelset_id
                            ? filtered_to_labelset_id
                            : filtered_to_corpus?.labelSet?.id
                            ? filtered_to_corpus.labelSet.id
                            : undefined
                        }
                      />
                    ) : (
                      <></>
                    )}
                  </>
                }
                value={searchCache}
                placeholder="Search for document containing text..."
                onChange={handleSearchChange}
              />
            </ModalSearchOverride>
          }
          style={{ height: "100%", display: "flex", flexDirection: "column" }}
        >
          <DocumentCards
            containerStyle={{
              flex: 1,
              minHeight: 0,
              position: "relative",
            }}
            style={{
              height: "100%",
            }}
            onClick={onSelect}
            items={document_items}
            pageInfo={documents_data?.documents?.pageInfo}
            loading={documents_loading}
            networkStatus={documents_network_status}
            loading_message="Loading Documents..."
            fetchMore={fetchMoreDocuments}
            onDrop={onDrop}
          />
        </CardLayout>
      </ModalBody>
      <ModalFooter>
        <Button variant="secondary" onClick={() => handleCancel()}>
          Cancel
        </Button>
        <Button variant="primary" onClick={() => handleConfirm()}>
          Add Documents
        </Button>
      </ModalFooter>
    </Modal>
  );
};
