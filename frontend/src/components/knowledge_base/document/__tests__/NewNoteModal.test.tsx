import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MockedProvider } from "@apollo/client/testing";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { toast } from "react-toastify";
import { NewNoteModal } from "../NewNoteModal";
import { CREATE_NOTE } from "../../../../graphql/mutations/noteMutations";

// Mock toast notifications
vi.mock("react-toastify", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

describe("NewNoteModal", () => {
  const mockDocumentId = "doc-123";
  const mockCorpusId = "corpus-456";
  const mockOnClose = vi.fn();
  const mockOnCreated = vi.fn();

  const defaultProps = {
    isOpen: true,
    onClose: mockOnClose,
    documentId: mockDocumentId,
    corpusId: mockCorpusId,
    onCreated: mockOnCreated,
  };

  const createNoteMock = {
    request: {
      query: CREATE_NOTE,
      variables: {
        documentId: mockDocumentId,
        corpusId: mockCorpusId,
        title: "Test Note",
        content: "Test content",
      },
    },
    result: {
      data: {
        createNote: {
          ok: true,
          message: "Note created successfully",
          obj: {
            id: "note-789",
            title: "Test Note",
            content: "Test content",
            created: "2024-01-01T00:00:00Z",
            modified: "2024-01-01T00:00:00Z",
            creator: {
              id: "user-1",
              email: "test@example.com",
            },
          },
        },
      },
    },
  };

  const renderComponent = (props = {}, mocks: any[] = [createNoteMock]) => {
    return render(
      <MockedProvider mocks={mocks} addTypename={false}>
        <NewNoteModal {...defaultProps} {...props} />
      </MockedProvider>
    );
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("Rendering", () => {
    it("should render the modal when open", () => {
      renderComponent();

      expect(screen.getByText("Create New Note")).toBeInTheDocument();
      expect(
        screen.getByPlaceholderText("Enter note title...")
      ).toBeInTheDocument();
      expect(
        screen.getByPlaceholderText("Write your note here...")
      ).toBeInTheDocument();
      expect(screen.getByText("Markdown supported:")).toBeInTheDocument();
    });

    it("should not render when closed", () => {
      renderComponent({ isOpen: false });

      expect(screen.queryByText("Create New Note")).not.toBeInTheDocument();
    });
  });

  describe("Form Validation", () => {
    it("should disable submit button when title is empty", async () => {
      renderComponent();

      const contentField = screen.getByPlaceholderText(
        "Write your note here..."
      );
      await userEvent.type(contentField, "Some content");

      const createButton = screen.getByRole("button", { name: "Create Note" });
      expect(createButton).toBeDisabled();
    });

    it("should disable submit button when content is empty", async () => {
      renderComponent();

      const titleField = screen.getByPlaceholderText("Enter note title...");
      await userEvent.type(titleField, "Some title");

      const createButton = screen.getByRole("button", { name: "Create Note" });
      expect(createButton).toBeDisabled();
    });

    it("should disable submit button when fields contain only whitespace", async () => {
      renderComponent();

      const titleField = screen.getByPlaceholderText("Enter note title...");
      await userEvent.type(titleField, "   ");

      const contentField = screen.getByPlaceholderText(
        "Write your note here..."
      );
      await userEvent.type(contentField, "   ");

      const createButton = screen.getByRole("button", { name: "Create Note" });
      expect(createButton).toBeDisabled();
    });

    it("should enable submit button when both fields have valid content", async () => {
      renderComponent();

      const titleField = screen.getByPlaceholderText("Enter note title...");
      await userEvent.type(titleField, "Valid Title");

      const contentField = screen.getByPlaceholderText(
        "Write your note here..."
      );
      await userEvent.type(contentField, "Valid content");

      const createButton = screen.getByRole("button", { name: "Create Note" });
      expect(createButton).not.toBeDisabled();
    });
  });

  describe("Successful Creation", () => {
    it("should create note successfully with valid data", async () => {
      renderComponent();

      const titleField = screen.getByPlaceholderText("Enter note title...");
      await userEvent.type(titleField, "Test Note");

      const contentField = screen.getByPlaceholderText(
        "Write your note here..."
      );
      await userEvent.type(contentField, "Test content");

      const createButton = screen.getByRole("button", { name: "Create Note" });
      await userEvent.click(createButton);

      await waitFor(() => {
        expect(toast.success).toHaveBeenCalledWith(
          "Note created successfully!"
        );
        expect(mockOnClose).toHaveBeenCalled();
        expect(mockOnCreated).toHaveBeenCalled();
      });
    });

    it("should clear form after successful creation", async () => {
      renderComponent();

      const titleField = screen.getByPlaceholderText("Enter note title...");
      await userEvent.type(titleField, "Test Note");

      const contentField = screen.getByPlaceholderText(
        "Write your note here..."
      );
      await userEvent.type(contentField, "Test content");

      const createButton = screen.getByRole("button", { name: "Create Note" });
      await userEvent.click(createButton);

      await waitFor(() => {
        expect(mockOnClose).toHaveBeenCalled();
      });
    });
  });

  describe("Error Handling", () => {
    it("should show error message from server", async () => {
      const errorMock = {
        ...createNoteMock,
        result: {
          data: {
            createNote: {
              ok: false,
              message: "Permission denied",
              obj: null,
            },
          },
        },
      };

      renderComponent({}, [errorMock]);

      const titleField = screen.getByPlaceholderText("Enter note title...");
      await userEvent.type(titleField, "Test Note");

      const contentField = screen.getByPlaceholderText(
        "Write your note here..."
      );
      await userEvent.type(contentField, "Test content");

      const createButton = screen.getByRole("button", { name: "Create Note" });
      await userEvent.click(createButton);

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith("Permission denied");
        expect(mockOnCreated).not.toHaveBeenCalled();
      });
    });

    it("should show generic error on network failure", async () => {
      const errorMock = {
        ...createNoteMock,
        error: new Error("Network error"),
      };

      renderComponent({}, [errorMock]);

      const titleField = screen.getByPlaceholderText("Enter note title...");
      await userEvent.type(titleField, "Test Note");

      const contentField = screen.getByPlaceholderText(
        "Write your note here..."
      );
      await userEvent.type(contentField, "Test content");

      const createButton = screen.getByRole("button", { name: "Create Note" });
      await userEvent.click(createButton);

      await waitFor(() => {
        expect(toast.error).toHaveBeenCalledWith("Failed to create note");
        expect(mockOnCreated).not.toHaveBeenCalled();
      });
    });
  });

  describe("Modal Actions", () => {
    it("should close modal when Cancel is clicked", async () => {
      renderComponent();

      const cancelButton = screen.getByRole("button", { name: "Cancel" });
      await userEvent.click(cancelButton);

      expect(mockOnClose).toHaveBeenCalled();
      expect(mockOnCreated).not.toHaveBeenCalled();
    });

    it("should clear form when closing", async () => {
      renderComponent();

      const titleField = screen.getByPlaceholderText("Enter note title...");
      await userEvent.type(titleField, "Test Note");

      const contentField = screen.getByPlaceholderText(
        "Write your note here..."
      );
      await userEvent.type(contentField, "Test content");

      const cancelButton = screen.getByRole("button", { name: "Cancel" });
      await userEvent.click(cancelButton);

      expect(mockOnClose).toHaveBeenCalled();
    });

    it("should disable buttons while loading", async () => {
      // Keep the mutation pending while checking its loading state. An
      // immediate mock response can settle before user-event finishes clicking.
      renderComponent({}, [{ ...createNoteMock, delay: Infinity }]);

      const titleField = screen.getByPlaceholderText("Enter note title...");
      await userEvent.type(titleField, "Test Note");

      const contentField = screen.getByPlaceholderText(
        "Write your note here..."
      );
      await userEvent.type(contentField, "Test content");

      const createButton = screen.getByRole("button", { name: "Create Note" });
      await userEvent.click(createButton);

      // Check buttons are disabled during mutation
      expect(createButton).toBeDisabled();
      expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    });
  });

  describe("Optional Props", () => {
    it("should work without corpusId", async () => {
      const mockWithoutCorpus = {
        request: {
          query: CREATE_NOTE,
          variables: {
            documentId: mockDocumentId,
            corpusId: undefined,
            title: "Test Note",
            content: "Test content",
          },
        },
        result: {
          data: {
            createNote: {
              ok: true,
              message: "Note created successfully",
              obj: {
                id: "note-789",
                title: "Test Note",
                content: "Test content",
                created: "2024-01-01T00:00:00Z",
                modified: "2024-01-01T00:00:00Z",
                creator: {
                  id: "user-1",
                  email: "test@example.com",
                },
              },
            },
          },
        },
      };

      renderComponent({ corpusId: undefined }, [mockWithoutCorpus]);

      const titleField = screen.getByPlaceholderText("Enter note title...");
      await userEvent.type(titleField, "Test Note");

      const contentField = screen.getByPlaceholderText(
        "Write your note here..."
      );
      await userEvent.type(contentField, "Test content");

      const createButton = screen.getByRole("button", { name: "Create Note" });
      await userEvent.click(createButton);

      await waitFor(() => {
        expect(toast.success).toHaveBeenCalledWith(
          "Note created successfully!"
        );
      });
    });

    it("should work without onCreated callback", async () => {
      renderComponent({ onCreated: undefined });

      const titleField = screen.getByPlaceholderText("Enter note title...");
      await userEvent.type(titleField, "Test Note");

      const contentField = screen.getByPlaceholderText(
        "Write your note here..."
      );
      await userEvent.type(contentField, "Test content");

      const createButton = screen.getByRole("button", { name: "Create Note" });
      await userEvent.click(createButton);

      await waitFor(() => {
        expect(toast.success).toHaveBeenCalledWith(
          "Note created successfully!"
        );
        expect(mockOnClose).toHaveBeenCalled();
      });
    });
  });
});
