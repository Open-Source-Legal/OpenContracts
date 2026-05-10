import React, { Dispatch, SetStateAction } from "react";
import { OS_LEGAL_COLORS } from "../../../../assets/configurations/osLegalStyles";
import { X, Edit } from "lucide-react";
import {
  Button,
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
} from "@os-legal/ui";
import { useNavigate } from "react-router-dom";
import { NoteType } from "../../../../types/graphql-api";

import { SafeMarkdown } from "../../markdown/SafeMarkdown";
import { NoteEditor } from "../NoteEditor";
import { NewNoteModal } from "../NewNoteModal";
import { AddToCorpusModal } from "../../../modals/AddToCorpusModal";
import { getDocumentUrl } from "../../../../utils/navigationUtils";
import { getCreatorDisplay } from "../../../../utils/userDisplay";

export interface DocumentModalsProps {
  /** Whether the graph modal is shown */
  showGraph: boolean;
  /** Setter for graph modal visibility */
  setShowGraph: (show: boolean) => void;
  /** Currently selected note for viewing */
  selectedNote: NoteType | null;
  /** Setter for selected note */
  setSelectedNote: Dispatch<SetStateAction<NoteType | null>>;
  /** ID of note currently being edited */
  editingNoteId: string | null;
  /** Setter for editing note ID */
  setEditingNoteId: (id: string | null) => void;
  /** Whether the new note modal is shown */
  showNewNoteModal: boolean;
  /** Setter for new note modal visibility */
  setShowNewNoteModal: (show: boolean) => void;
  /** Whether the add-to-corpus modal is shown */
  showAddToCorpusModal: boolean;
  /** Setter for add-to-corpus modal visibility */
  setShowAddToCorpusModal: (show: boolean) => void;
  /** Whether the view is read-only */
  readOnly: boolean;
  /** Document ID */
  documentId: string;
  /** Optional corpus ID */
  corpusId?: string;
  /** Refetch function to update data after mutations */
  refetch: () => void;
  /** Combined document data for navigation after corpus assignment.
   * Must be compatible with getDocumentUrl()'s first parameter. */
  combinedDocumentData?: {
    id: string;
    slug?: string | null;
    creator?: { id: string; slug?: string | null } | null;
  } | null;
}

/**
 * Renders all modal dialogs used by the DocumentKnowledgeBase component:
 * - Graph modal
 * - Note viewing modal
 * - Note editor modal
 * - New note creation modal
 * - Add to corpus modal
 */
export const DocumentModals: React.FC<DocumentModalsProps> = ({
  showGraph,
  setShowGraph,
  selectedNote,
  setSelectedNote,
  editingNoteId,
  setEditingNoteId,
  showNewNoteModal,
  setShowNewNoteModal,
  showAddToCorpusModal,
  setShowAddToCorpusModal,
  readOnly,
  documentId,
  corpusId,
  refetch,
  combinedDocumentData,
}) => {
  const navigate = useNavigate();

  return (
    <>
      <Modal open={showGraph} onClose={() => setShowGraph(false)} size="lg">
        <ModalHeader title="Graph View" onClose={() => setShowGraph(false)} />
        <ModalBody>{/* Graph or relationship visualization */}</ModalBody>
        <ModalFooter>
          <Button
            variant="secondary"
            onClick={() => setShowGraph(false)}
            leftIcon={<X size={16} />}
          >
            Close
          </Button>
        </ModalFooter>
      </Modal>

      {!!selectedNote && (
        <Modal
          open={!!selectedNote}
          onClose={() => setSelectedNote(null)}
          size="lg"
        >
          <ModalHeader
            title={selectedNote.title || "Untitled Note"}
            onClose={() => setSelectedNote(null)}
          />
          <ModalBody>
            <SafeMarkdown>{selectedNote.content}</SafeMarkdown>
            <div
              style={{
                fontSize: "0.85em",
                color: OS_LEGAL_COLORS.textSecondary,
                marginTop: "1rem",
              }}
            >
              Added by {getCreatorDisplay(selectedNote.creator)} on{" "}
              {new Date(selectedNote.created).toLocaleString()}
            </div>
          </ModalBody>
          <ModalFooter>
            {!readOnly && (
              <Button
                variant="primary"
                leftIcon={<Edit size={16} />}
                onClick={() => {
                  setEditingNoteId(selectedNote.id);
                  setSelectedNote(null);
                }}
              >
                Edit Note
              </Button>
            )}
            <Button variant="secondary" onClick={() => setSelectedNote(null)}>
              Close
            </Button>
          </ModalFooter>
        </Modal>
      )}

      {!readOnly && editingNoteId && (
        <NoteEditor
          noteId={editingNoteId}
          isOpen={true}
          onClose={() => setEditingNoteId(null)}
          onUpdate={() => {
            // Refetch the document data to get updated notes
            refetch();
          }}
        />
      )}

      {!readOnly && (
        <NewNoteModal
          isOpen={showNewNoteModal}
          onClose={() => setShowNewNoteModal(false)}
          documentId={documentId}
          corpusId={corpusId}
          onCreated={() => {
            // Refetch the document data to get the new note
            refetch();
          }}
        />
      )}

      <AddToCorpusModal
        documentId={documentId}
        open={showAddToCorpusModal}
        onClose={() => setShowAddToCorpusModal(false)}
        onSuccess={(newCorpusId, newCorpus) => {
          // Navigate with corpus context using proper SPA navigation
          if (combinedDocumentData && newCorpus) {
            const url = getDocumentUrl(
              combinedDocumentData as Parameters<typeof getDocumentUrl>[0],
              newCorpus
            );
            if (url !== "#") {
              navigate(url);
            } else {
              console.warn("[DocumentModals] Missing slugs for navigation:", {
                newCorpus,
                document: combinedDocumentData,
              });
              navigate("/documents");
            }
          } else {
            navigate("/documents");
          }
        }}
      />
    </>
  );
};
