import React, { useCallback } from "react";

import { useReactiveVar } from "@apollo/client";

import {
  editingDocument,
  openedCorpus,
  openedDocument,
  selectedFolderId,
  showSelectCorpusAnalyzerOrFieldsetModal,
  showUploadNewDocumentsModal,
  uploadModalPreloadedFiles,
  viewingDocument,
} from "../../graphql/cache";
import { DocumentFormFields } from "../forms/DocumentFormFields";
import { validateTitleAndDescription } from "../forms/shared";
import { CRUDModal } from "../widgets/CRUD/CRUDModal";
import { DocumentUploadModal } from "../widgets/modals/DocumentUploadModal";
import { SelectAnalyzerOrFieldsetModal } from "../widgets/modals/SelectCorpusAnalyzerOrFieldsetAnalyzer";

export interface AppDocumentModalsProps {
  /** Apollo mutation handler invoked when the EDIT modal is submitted. */
  handleUpdateDocument: (document_obj: Record<string, unknown>) => void;
}

/** Top-level reactive-var-driven modals (corpus analyzer, upload, edit/view). */
export const AppDocumentModals: React.FC<AppDocumentModalsProps> = ({
  handleUpdateDocument,
}) => {
  const opened_corpus = useReactiveVar(openedCorpus);
  const opened_document = useReactiveVar(openedDocument);
  const document_to_edit = useReactiveVar(editingDocument);
  const document_to_view = useReactiveVar(viewingDocument);
  const selected_folder_id = useReactiveVar(selectedFolderId);
  const show_corpus_analyzer_fieldset_modal = useReactiveVar(
    showSelectCorpusAnalyzerOrFieldsetModal
  );
  const show_upload_new_documents_modal = useReactiveVar(
    showUploadNewDocumentsModal
  );

  const closeUploadModal = useCallback(() => {
    showUploadNewDocumentsModal(false);
    uploadModalPreloadedFiles([]);
  }, []);

  return (
    <>
      {opened_corpus ? (
        <SelectAnalyzerOrFieldsetModal
          open={show_corpus_analyzer_fieldset_modal}
          corpus={opened_corpus}
          document={opened_document ?? undefined}
          onClose={() => showSelectCorpusAnalyzerOrFieldsetModal(false)}
        />
      ) : null}
      <DocumentUploadModal
        refetch={closeUploadModal}
        open={Boolean(show_upload_new_documents_modal)}
        onClose={closeUploadModal}
        corpusId={opened_corpus?.id ?? null}
        folderId={selected_folder_id}
      />
      <CRUDModal
        open={document_to_edit !== null}
        mode="EDIT"
        oldInstance={document_to_edit ?? {}}
        modelName="document"
        onSubmit={handleUpdateDocument}
        onClose={() => editingDocument(null)}
        acceptedFileTypes="pdf"
        hasFile={true}
        fileField="pdfFile"
        fileLabel="PDF File"
        fileIsImage={false}
        validate={validateTitleAndDescription}
        renderForm={(formData, onChange, disabled) => (
          <DocumentFormFields
            formData={formData}
            onChange={onChange}
            disabled={disabled}
          />
        )}
      />
      <CRUDModal
        open={document_to_view !== null}
        mode="VIEW"
        oldInstance={document_to_view ?? {}}
        modelName="document"
        onClose={() => viewingDocument(null)}
        acceptedFileTypes="pdf"
        hasFile={true}
        fileField="pdfFile"
        fileLabel="PDF File"
        fileIsImage={false}
        renderForm={(formData, onChange, disabled) => (
          <DocumentFormFields
            formData={formData}
            onChange={onChange}
            disabled={disabled}
          />
        )}
      />
    </>
  );
};
