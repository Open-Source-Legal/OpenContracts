/**
 * Coverage for ``AppDocumentModals`` — the conditional/ternary branches
 * extracted from ``App`` so the patch lines that gate which modal renders
 * can be unit-tested without mounting the whole routing tree.
 *
 * Heavy modal children (``SelectAnalyzerOrFieldsetModal``,
 * ``DocumentUploadModal``, ``CRUDModal``) are stubbed so the test focuses
 * on the prop expressions that the component computes — the ternaries on
 * ``opened_document``/``document_to_edit``/``document_to_view``, the
 * ``opened_corpus`` guard, and the shared close callback for the upload
 * modal.
 */
import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  editingDocument,
  openedCorpus,
  openedDocument,
  selectedFolderId,
  showSelectCorpusAnalyzerOrFieldsetModal,
  showUploadNewDocumentsModal,
  uploadModalPreloadedFiles,
  viewingDocument,
} from "../../../graphql/cache";
import type { CorpusType, DocumentType } from "../../../types/graphql-api";
import { AppDocumentModals } from "../AppDocumentModals";

type ModalProps = Record<string, unknown>;

/** Spies that capture the props each stubbed modal receives on every render. */
const selectAnalyzerCalls: ModalProps[] = [];
const uploadModalCalls: ModalProps[] = [];
const crudModalCalls: ModalProps[] = [];

vi.mock("../../widgets/modals/SelectCorpusAnalyzerOrFieldsetAnalyzer", () => ({
  SelectAnalyzerOrFieldsetModal: (props: ModalProps) => {
    selectAnalyzerCalls.push(props);
    return <div data-testid="select-analyzer-modal" />;
  },
}));

vi.mock("../../widgets/modals/DocumentUploadModal", () => ({
  DocumentUploadModal: (props: ModalProps) => {
    uploadModalCalls.push(props);
    return <div data-testid="upload-modal" />;
  },
}));

vi.mock("../../widgets/CRUD/CRUDModal", () => ({
  CRUDModal: (props: ModalProps) => {
    crudModalCalls.push(props);
    return <div data-testid={`crud-modal-${props.mode as string}`} />;
  },
}));

/** Avoid pulling form-field internals into the test; the component invokes
 *  ``renderForm`` lazily via the CRUD modal stub, which we ignore.
 */
vi.mock("../../forms/DocumentFormFields", () => ({
  DocumentFormFields: () => <div />,
}));

vi.mock("../../forms/shared", () => ({
  validateTitleAndDescription: () => [],
}));

const corpusFixture = (id = "Q29ycHVzVHlwZTox"): CorpusType =>
  ({
    id,
    title: "Test corpus",
  } as unknown as CorpusType);

const documentFixture = (id = "RG9jdW1lbnRUeXBlOjE="): DocumentType =>
  ({
    id,
    title: "Test document",
  } as unknown as DocumentType);

/** Reset every reactive var the component reads so each test starts clean. */
const resetVars = () => {
  openedCorpus(null);
  openedDocument(null);
  editingDocument(null);
  viewingDocument(null);
  selectedFolderId(null);
  showSelectCorpusAnalyzerOrFieldsetModal(false);
  showUploadNewDocumentsModal(false);
  uploadModalPreloadedFiles([]);
};

describe("AppDocumentModals", () => {
  const handleUpdateDocument = vi.fn();

  beforeEach(() => {
    selectAnalyzerCalls.length = 0;
    uploadModalCalls.length = 0;
    crudModalCalls.length = 0;
    handleUpdateDocument.mockClear();
    resetVars();
  });

  afterEach(() => {
    resetVars();
  });

  it("does not render SelectAnalyzerOrFieldsetModal when no corpus is opened", () => {
    render(<AppDocumentModals handleUpdateDocument={handleUpdateDocument} />);

    expect(screen.queryByTestId("select-analyzer-modal")).toBeNull();

    // The upload modal still renders, with corpusId falling back to null and
    // folderId picked up from the (null) reactive var.
    const upload = uploadModalCalls.at(-1);
    expect(upload?.corpusId).toBeNull();
    expect(upload?.folderId).toBeNull();
    expect(upload?.open).toBe(false);
  });

  it("renders SelectAnalyzerOrFieldsetModal with document=undefined when no document opened", () => {
    act(() => {
      openedCorpus(corpusFixture());
      showSelectCorpusAnalyzerOrFieldsetModal(true);
    });

    render(<AppDocumentModals handleUpdateDocument={handleUpdateDocument} />);

    expect(screen.getByTestId("select-analyzer-modal")).toBeInTheDocument();
    const lastCall = selectAnalyzerCalls.at(-1);
    expect(lastCall?.open).toBe(true);
    expect(lastCall?.corpus).toMatchObject({ id: "Q29ycHVzVHlwZTox" });
    expect(lastCall?.document).toBeUndefined();

    // corpusId on the upload modal should reflect the opened corpus' id.
    const upload = uploadModalCalls.at(-1);
    expect(upload?.corpusId).toBe("Q29ycHVzVHlwZTox");
  });

  it("threads opened_document into SelectAnalyzerOrFieldsetModal when both are set", () => {
    act(() => {
      openedCorpus(corpusFixture());
      openedDocument(documentFixture());
    });

    render(<AppDocumentModals handleUpdateDocument={handleUpdateDocument} />);

    const lastCall = selectAnalyzerCalls.at(-1);
    expect(lastCall?.document).toMatchObject({ id: "RG9jdW1lbnRUeXBlOjE=" });
  });

  it("invoking SelectAnalyzerOrFieldsetModal.onClose clears the open flag", () => {
    act(() => {
      openedCorpus(corpusFixture());
      showSelectCorpusAnalyzerOrFieldsetModal(true);
    });

    render(<AppDocumentModals handleUpdateDocument={handleUpdateDocument} />);

    const onClose = selectAnalyzerCalls.at(-1)?.onClose as () => void;
    expect(typeof onClose).toBe("function");
    act(() => onClose());

    expect(showSelectCorpusAnalyzerOrFieldsetModal()).toBe(false);
  });

  it("DocumentUploadModal share one closeUploadModal callback for refetch and onClose", () => {
    render(<AppDocumentModals handleUpdateDocument={handleUpdateDocument} />);

    const upload = uploadModalCalls.at(-1);
    expect(upload?.refetch).toBe(upload?.onClose);
  });

  it("invoking the upload close callback clears the modal open flag and preloaded files", () => {
    act(() => {
      showUploadNewDocumentsModal(true);
      uploadModalPreloadedFiles([
        // Minimal shape — the cache reactive var only requires `file`/`formData`.
        {
          file: new File(["a"], "a.pdf", { type: "application/pdf" }),
          formData: { title: "a.pdf", description: "" },
        },
      ]);
    });

    render(<AppDocumentModals handleUpdateDocument={handleUpdateDocument} />);

    expect(uploadModalCalls.at(-1)?.open).toBe(true);

    const onClose = uploadModalCalls.at(-1)?.onClose as () => void;
    act(() => onClose());

    expect(showUploadNewDocumentsModal()).toBe(false);
    expect(uploadModalPreloadedFiles()).toEqual([]);
  });

  it("renders both CRUD modals closed with empty oldInstance when no edit/view document is set", () => {
    render(<AppDocumentModals handleUpdateDocument={handleUpdateDocument} />);

    const editProps = crudModalCalls.find((c) => c.mode === "EDIT");
    const viewProps = crudModalCalls.find((c) => c.mode === "VIEW");
    expect(editProps?.open).toBe(false);
    expect(editProps?.oldInstance).toEqual({});
    expect(viewProps?.open).toBe(false);
    expect(viewProps?.oldInstance).toEqual({});
  });

  it("opens the EDIT modal with the document_to_edit instance", () => {
    const doc = documentFixture("ZWRpdC1kb2M=");
    act(() => {
      editingDocument(doc);
    });

    render(<AppDocumentModals handleUpdateDocument={handleUpdateDocument} />);

    const editProps = crudModalCalls.find((c) => c.mode === "EDIT");
    expect(editProps?.open).toBe(true);
    expect(editProps?.oldInstance).toMatchObject({ id: "ZWRpdC1kb2M=" });
    expect(editProps?.onSubmit).toBe(handleUpdateDocument);
  });

  it("invoking the EDIT modal onClose clears editingDocument", () => {
    act(() => {
      editingDocument(documentFixture());
    });

    render(<AppDocumentModals handleUpdateDocument={handleUpdateDocument} />);

    const onClose = crudModalCalls.find((c) => c.mode === "EDIT")
      ?.onClose as () => void;
    act(() => onClose());

    expect(editingDocument()).toBeNull();
  });

  it("opens the VIEW modal with the document_to_view instance", () => {
    const doc = documentFixture("dmlldy1kb2M=");
    act(() => {
      viewingDocument(doc);
    });

    render(<AppDocumentModals handleUpdateDocument={handleUpdateDocument} />);

    const viewProps = crudModalCalls.find((c) => c.mode === "VIEW");
    expect(viewProps?.open).toBe(true);
    expect(viewProps?.oldInstance).toMatchObject({ id: "dmlldy1kb2M=" });
  });

  it("invoking the VIEW modal onClose clears viewingDocument", () => {
    act(() => {
      viewingDocument(documentFixture());
    });

    render(<AppDocumentModals handleUpdateDocument={handleUpdateDocument} />);

    const onClose = crudModalCalls.find((c) => c.mode === "VIEW")
      ?.onClose as () => void;
    act(() => onClose());

    expect(viewingDocument()).toBeNull();
  });

  it("propagates selected_folder_id into the upload modal", () => {
    act(() => {
      selectedFolderId("folder-42");
    });

    render(<AppDocumentModals handleUpdateDocument={handleUpdateDocument} />);

    expect(uploadModalCalls.at(-1)?.folderId).toBe("folder-42");
  });

  it("invokes both renderForm callbacks (covers the inline render-prop branches)", () => {
    act(() => {
      editingDocument(documentFixture());
      viewingDocument(documentFixture());
    });

    render(<AppDocumentModals handleUpdateDocument={handleUpdateDocument} />);

    const editRenderForm = crudModalCalls.find((c) => c.mode === "EDIT")
      ?.renderForm as (
      formData: Record<string, unknown>,
      onChange: (u: unknown) => void,
      disabled: boolean
    ) => unknown;
    const viewRenderForm = crudModalCalls.find((c) => c.mode === "VIEW")
      ?.renderForm as (
      formData: Record<string, unknown>,
      onChange: (u: unknown) => void,
      disabled: boolean
    ) => unknown;

    // Calling the render-prop should produce a JSX node — coverage for the
    // inline arrow function bodies.
    expect(editRenderForm({}, () => undefined, false)).toBeTruthy();
    expect(viewRenderForm({}, () => undefined, true)).toBeTruthy();
  });
});
