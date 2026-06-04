/**
 * Unit-level coverage for CorpusQueryView's onChatSubmit / onNavigateHome
 * branches that the CT suite cannot reach without standing up the full
 * CorpusHome + CorpusChat composer infrastructure.
 *
 * Strategy: vi.mock the heavy children so they expose `__triggerChatSubmit`
 * / `__triggerNavigateHome` buttons that synthesise the callbacks. The real
 * component's setChatExpanded / resetToSearch / state-machine is exercised;
 * only the children's UI is replaced.
 */
import React from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, act } from "@testing-library/react";
import { MockedProvider } from "@apollo/client/testing";
import { Provider } from "jotai";
import { MemoryRouter } from "react-router-dom";
import { CorpusType } from "../../types/graphql-api";
import { showQueryViewState } from "../../graphql/cache";

// Hoisted stubs so vi.mock can reference them. Each stub renders the props
// callbacks as inline buttons so a test can fire them synthetically.
//
// Local interfaces describe only the prop callbacks the stubs need to
// surface; the real components accept many more props but the stubs ignore
// them, so a narrow shape avoids dragging the full component signatures into
// this test file (and the explicit-`any` baseline at the same time).
interface MockCorpusHomeProps {
  onChatSubmit?: (text: string) => void;
  onEditDescription?: () => void;
  onEditArticle?: () => void;
  onViewChatHistory?: () => void;
}

interface MockCorpusChatProps {
  showLoad?: boolean;
  onNavigateHome?: () => void;
  onViewModeChange?: (inConversation: boolean) => void;
}

vi.mock("../../components/corpuses/CorpusHome", () => ({
  CorpusHome: (props: MockCorpusHomeProps) => (
    <div data-testid="mock-corpus-home">
      <button
        data-testid="trigger-chat-submit"
        onClick={() => props.onChatSubmit?.("how does this corpus work?")}
      >
        submit
      </button>
      <button
        data-testid="trigger-empty-submit"
        onClick={() => props.onChatSubmit?.("   ")}
      >
        submit-empty
      </button>
      <button
        data-testid="trigger-edit-description"
        onClick={() => props.onEditDescription?.()}
      >
        edit-desc
      </button>
      <button
        data-testid="trigger-edit-article"
        onClick={() => props.onEditArticle?.()}
      >
        edit-article
      </button>
      <button
        data-testid="trigger-view-history"
        onClick={() => props.onViewChatHistory?.()}
      >
        view-history
      </button>
    </div>
  ),
}));

vi.mock("../../components/corpuses/CorpusChat", () => ({
  CorpusChat: (props: MockCorpusChatProps) => (
    <div data-testid="mock-corpus-chat" data-show-load={String(props.showLoad)}>
      <button
        data-testid="trigger-navigate-home"
        onClick={() => props.onNavigateHome?.()}
      >
        nav-home
      </button>
      <button
        data-testid="trigger-conversation-view"
        onClick={() => props.onViewModeChange?.(true)}
      >
        in-conversation
      </button>
      <button
        data-testid="trigger-conversation-list"
        onClick={() => props.onViewModeChange?.(false)}
      >
        in-list
      </button>
    </div>
  ),
}));

import { CorpusQueryView } from "../CorpusQueryView";

const buildCorpus = (): CorpusType =>
  ({
    id: "C1",
    title: "Test Corpus",
  } as unknown as CorpusType);

const baseStats = {
  totalDocs: 0,
  totalAnnotations: 0,
  totalAnalyses: 0,
  totalExtracts: 0,
  totalThreads: 0,
};

const renderView = (
  props: Partial<React.ComponentProps<typeof CorpusQueryView>> = {}
) => {
  const setShowDescriptionEditor = vi.fn();
  const setShowArticleEditor = vi.fn();

  const utils = render(
    <Provider>
      <MemoryRouter>
        <MockedProvider mocks={[]} addTypename>
          <CorpusQueryView
            opened_corpus={buildCorpus()}
            setShowDescriptionEditor={setShowDescriptionEditor}
            setShowArticleEditor={setShowArticleEditor}
            stats={baseStats}
            statsLoading={false}
            {...props}
          />
        </MockedProvider>
      </MemoryRouter>
    </Provider>
  );

  return { ...utils, setShowDescriptionEditor, setShowArticleEditor };
};

describe("CorpusQueryView handler branches", () => {
  beforeEach(() => {
    showQueryViewState("ASK");
  });

  it("submitting a non-empty chat query expands the chat", () => {
    renderView();
    expect(screen.getByTestId("mock-corpus-home")).toBeInTheDocument();

    act(() => {
      fireEvent.click(screen.getByTestId("trigger-chat-submit"));
    });

    // chatExpanded=true swaps the dashboard for CorpusChat (showLoad=false).
    expect(screen.getByTestId("mock-corpus-chat")).toBeInTheDocument();
    expect(screen.getByTestId("mock-corpus-chat")).toHaveAttribute(
      "data-show-load",
      "false"
    );
  });

  it("submitting whitespace-only does NOT expand the chat", () => {
    renderView();
    act(() => {
      fireEvent.click(screen.getByTestId("trigger-empty-submit"));
    });
    expect(screen.queryByTestId("mock-corpus-chat")).not.toBeInTheDocument();
    expect(screen.getByTestId("mock-corpus-home")).toBeInTheDocument();
  });

  it("onEditDescription calls setShowDescriptionEditor(true)", () => {
    const { setShowDescriptionEditor } = renderView();
    act(() => {
      fireEvent.click(screen.getByTestId("trigger-edit-description"));
    });
    expect(setShowDescriptionEditor).toHaveBeenCalledWith(true);
  });

  it("onEditArticle calls setShowArticleEditor(true)", () => {
    const { setShowArticleEditor } = renderView();
    act(() => {
      fireEvent.click(screen.getByTestId("trigger-edit-article"));
    });
    expect(setShowArticleEditor).toHaveBeenCalledWith(true);
  });

  it("onViewChatHistory flips reactive var to VIEW", () => {
    renderView();
    act(() => {
      fireEvent.click(screen.getByTestId("trigger-view-history"));
    });
    expect(showQueryViewState()).toBe("VIEW");
  });

  it("CorpusChat onNavigateHome from VIEW state resets back to dashboard", () => {
    showQueryViewState("VIEW");
    renderView();
    expect(screen.getByTestId("mock-corpus-chat")).toBeInTheDocument();
    expect(screen.getByTestId("mock-corpus-chat")).toHaveAttribute(
      "data-show-load",
      "true"
    );

    act(() => {
      fireEvent.click(screen.getByTestId("trigger-navigate-home"));
    });

    // After navigate-home, state flips back to ASK and dashboard is shown.
    expect(showQueryViewState()).toBe("ASK");
    expect(screen.getByTestId("mock-corpus-home")).toBeInTheDocument();
  });

  it("after expanding chat, CorpusChat onNavigateHome resets to search", () => {
    renderView();
    act(() => {
      fireEvent.click(screen.getByTestId("trigger-chat-submit"));
    });
    expect(screen.getByTestId("mock-corpus-chat")).toBeInTheDocument();

    act(() => {
      fireEvent.click(screen.getByTestId("trigger-navigate-home"));
    });

    expect(screen.queryByTestId("mock-corpus-chat")).not.toBeInTheDocument();
    expect(screen.getByTestId("mock-corpus-home")).toBeInTheDocument();
  });

  it("onViewModeChange toggles suppression of the outer Back header", () => {
    renderView();
    act(() => {
      fireEvent.click(screen.getByTestId("trigger-chat-submit"));
    });

    // onChatSubmit pre-sets chatExpandedInConversation=true, so the outer
    // Back header is initially suppressed (the inner CorpusChat header is
    // the single source of back navigation while a conversation is open).
    expect(screen.queryByText("Back")).not.toBeInTheDocument();

    // Returning to the conversation-list view (onViewModeChange(false))
    // un-suppresses the outer Back header.
    act(() => {
      fireEvent.click(screen.getByTestId("trigger-conversation-list"));
    });
    expect(screen.queryByText("Back")).toBeInTheDocument();

    // Re-entering a conversation re-suppresses it.
    act(() => {
      fireEvent.click(screen.getByTestId("trigger-conversation-view"));
    });
    expect(screen.queryByText("Back")).not.toBeInTheDocument();
  });

  it("VIEW (Conversation History) suppresses the outer header while a conversation is open", () => {
    // Regression for the stacked "Conversation History" + "Conversation"
    // double header: in VIEW mode the outer header must hide once a single
    // conversation is open (the inner CorpusChat header owns Back + Home there)
    // and reappear when the user returns to the conversation list.
    showQueryViewState("VIEW");
    renderView();

    // Conversation-list view: the outer "Conversation History" header is shown.
    expect(screen.queryByText("Conversation History")).toBeInTheDocument();

    // Opening a conversation (onViewModeChange(true)) suppresses the outer
    // header — previously it stayed, stacking on the inner one.
    act(() => {
      fireEvent.click(screen.getByTestId("trigger-conversation-view"));
    });
    expect(screen.queryByText("Conversation History")).not.toBeInTheDocument();

    // Returning to the list (onViewModeChange(false)) restores it.
    act(() => {
      fireEvent.click(screen.getByTestId("trigger-conversation-list"));
    });
    expect(screen.queryByText("Conversation History")).toBeInTheDocument();
  });
});
