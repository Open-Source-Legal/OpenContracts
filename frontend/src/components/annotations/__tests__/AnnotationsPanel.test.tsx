import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MockedProvider } from "@apollo/client/testing";
import { MemoryRouter } from "react-router-dom";
import {
  AnnotationsPanel,
  applyLocalFilters,
  TypeFilterValue,
  SourceFilterValue,
} from "../AnnotationsPanel";
import { ServerAnnotationType, LabelType } from "../../../types/graphql-api";

// Mock the @os-legal/ui components
vi.mock("@os-legal/ui", () => ({
  SearchBox: ({
    placeholder,
    value,
    onChange,
    onSubmit,
  }: {
    placeholder: string;
    value: string;
    onChange: (e: { target: { value: string } }) => void;
    onSubmit?: (value: string) => void;
  }) => (
    <input
      data-testid="search-box"
      placeholder={placeholder}
      value={value}
      onChange={onChange}
      onKeyDown={(e) => {
        if (e.key === "Enter" && onSubmit) {
          onSubmit(value);
        }
      }}
    />
  ),
  FilterTabs: ({
    items,
    value,
    onChange,
  }: {
    items: { id: string; label: string }[];
    value: string;
    onChange: (id: string) => void;
  }) => (
    <div data-testid="filter-tabs">
      {items.map((item) => (
        <button
          key={item.id}
          data-testid={`filter-tab-${item.id}`}
          data-active={value === item.id}
          onClick={() => onChange(item.id)}
        >
          {item.label}
        </button>
      ))}
    </div>
  ),
  Avatar: ({ fallback }: { fallback: string }) => (
    <div data-testid="avatar">{fallback}</div>
  ),
  Chip: ({
    children,
  }: {
    children: React.ReactNode;
    size?: string;
    [key: string]: unknown;
  }) => <span data-testid="chip">{children}</span>,
}));

// Mock react-cool-inview to avoid IntersectionObserver issues
vi.mock("react-cool-inview", () => ({
  useInView: () => ({
    observe: vi.fn(),
    unobserve: vi.fn(),
    inView: false,
    scrollDirection: { vertical: undefined },
    entry: null,
  }),
}));

/**
 * Sequential counter for deterministic annotation IDs
 */
let mockAnnotationCounter = 0;

/**
 * Factory function to create mock annotation data
 */
const createMockAnnotation = (
  overrides: Partial<ServerAnnotationType> = {}
): ServerAnnotationType => ({
  id: `annotation-${++mockAnnotationCounter}`,
  page: 0,
  annotationLabel: {
    id: "label-1",
    text: "Test Label",
    color: "#FF0000",
    labelType: LabelType.TokenLabel,
  },
  document: {
    id: "doc-1",
    title: "Test Document",
    slug: "test-document",
  } as ServerAnnotationType["document"],
  corpus: {
    id: "corpus-1",
    title: "Test Corpus",
    slug: "test-corpus",
    labelSet: {
      id: "labelset-1",
      title: "Test Labelset",
    },
  } as ServerAnnotationType["corpus"],
  rawText: "Sample annotation text.",
  structural: false,
  isPublic: false,
  created: new Date().toISOString(),
  creator: {
    email: "test@example.com",
    username: "testuser",
  } as ServerAnnotationType["creator"],
  ...overrides,
});

/**
 * Wrapper component for tests
 */
const TestWrapper: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <MockedProvider mocks={[]} addTypename={false}>
    <MemoryRouter>{children}</MemoryRouter>
  </MockedProvider>
);

describe("AnnotationsPanel", () => {
  const defaultProps = {
    items: [] as ServerAnnotationType[],
    loading: false,
    typeFilter: "all" as TypeFilterValue,
    sourceFilter: "all" as SourceFilterValue,
    searchValue: "",
    onTypeFilterChange: vi.fn(),
    onSourceFilterChange: vi.fn(),
    onSearchChange: vi.fn(),
    onFetchMore: vi.fn(),
    onItemClick: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockAnnotationCounter = 0;
  });

  describe("Filter Tabs", () => {
    it("renders type filter tabs (All/Doc/Text)", () => {
      render(
        <TestWrapper>
          <AnnotationsPanel {...defaultProps} />
        </TestWrapper>
      );

      // There are multiple "all" tabs (one for type, one for source)
      const allTabs = screen.getAllByTestId("filter-tab-all");
      expect(allTabs[0]).toHaveTextContent("All Types");
      expect(screen.getByTestId("filter-tab-doc")).toHaveTextContent(
        "Doc Labels"
      );
      expect(screen.getByTestId("filter-tab-text")).toHaveTextContent(
        "Text Labels"
      );
    });

    it("renders source filter tabs (All/Human/Agent/Structural)", () => {
      render(
        <TestWrapper>
          <AnnotationsPanel {...defaultProps} />
        </TestWrapper>
      );

      // Source filter tabs (second "all" tab is for sources)
      const allButtons = screen.getAllByTestId("filter-tab-all");
      expect(allButtons.length).toBe(2);
      expect(allButtons[1]).toHaveTextContent("All Sources");
      expect(screen.getByTestId("filter-tab-human")).toHaveTextContent("Human");
      expect(screen.getByTestId("filter-tab-agent")).toHaveTextContent(
        "AI Agent"
      );
      expect(screen.getByTestId("filter-tab-structural")).toHaveTextContent(
        "Structural"
      );
    });

    it("calls onTypeFilterChange when type tab clicked", () => {
      const onTypeFilterChange = vi.fn();
      render(
        <TestWrapper>
          <AnnotationsPanel
            {...defaultProps}
            onTypeFilterChange={onTypeFilterChange}
          />
        </TestWrapper>
      );

      fireEvent.click(screen.getByTestId("filter-tab-doc"));
      expect(onTypeFilterChange).toHaveBeenCalledWith("doc");
    });

    it("calls onSourceFilterChange when source tab clicked", () => {
      const onSourceFilterChange = vi.fn();
      render(
        <TestWrapper>
          <AnnotationsPanel
            {...defaultProps}
            onSourceFilterChange={onSourceFilterChange}
          />
        </TestWrapper>
      );

      fireEvent.click(screen.getByTestId("filter-tab-structural"));
      expect(onSourceFilterChange).toHaveBeenCalledWith("structural");
    });

    it("highlights active filter tab", () => {
      render(
        <TestWrapper>
          <AnnotationsPanel
            {...defaultProps}
            typeFilter="doc"
            sourceFilter="human"
          />
        </TestWrapper>
      );

      expect(screen.getByTestId("filter-tab-doc")).toHaveAttribute(
        "data-active",
        "true"
      );
      expect(screen.getByTestId("filter-tab-human")).toHaveAttribute(
        "data-active",
        "true"
      );
    });
  });

  describe("Search", () => {
    it("renders search box with placeholder", () => {
      render(
        <TestWrapper>
          <AnnotationsPanel {...defaultProps} />
        </TestWrapper>
      );

      const searchBox = screen.getByTestId("search-box");
      expect(searchBox).toBeInTheDocument();
      expect(searchBox).toHaveAttribute("placeholder", "Search annotations...");
    });

    it("calls onSearchChange when typing", () => {
      const onSearchChange = vi.fn();
      render(
        <TestWrapper>
          <AnnotationsPanel {...defaultProps} onSearchChange={onSearchChange} />
        </TestWrapper>
      );

      const searchBox = screen.getByTestId("search-box");
      fireEvent.change(searchBox, { target: { value: "test query" } });
      expect(onSearchChange).toHaveBeenCalledWith("test query");
    });

    it("calls onSearchSubmit on enter", () => {
      const onSearchSubmit = vi.fn();
      render(
        <TestWrapper>
          <AnnotationsPanel
            {...defaultProps}
            searchValue="test query"
            onSearchSubmit={onSearchSubmit}
          />
        </TestWrapper>
      );

      const searchBox = screen.getByTestId("search-box");
      fireEvent.keyDown(searchBox, { key: "Enter" });
      expect(onSearchSubmit).toHaveBeenCalledWith("test query");
    });
  });

  describe("Grid Display", () => {
    it("renders ModernAnnotationCard for each item", () => {
      const items = [
        createMockAnnotation({ id: "ann-1", rawText: "First annotation" }),
        createMockAnnotation({ id: "ann-2", rawText: "Second annotation" }),
      ];

      render(
        <TestWrapper>
          <AnnotationsPanel {...defaultProps} items={items} />
        </TestWrapper>
      );

      expect(screen.getByText("First annotation")).toBeInTheDocument();
      expect(screen.getByText("Second annotation")).toBeInTheDocument();
    });

    it("calls onItemClick when card clicked", () => {
      const onItemClick = vi.fn();
      const items = [
        createMockAnnotation({ id: "ann-1", rawText: "Click me" }),
      ];

      render(
        <TestWrapper>
          <AnnotationsPanel
            {...defaultProps}
            items={items}
            onItemClick={onItemClick}
          />
        </TestWrapper>
      );

      const text = screen.getByText("Click me");
      fireEvent.click(text.closest("div")!);
      expect(onItemClick).toHaveBeenCalledWith(items[0]);
    });

    it("displays similarity scores when provided", () => {
      const items = [createMockAnnotation({ id: "ann-1" })];
      const similarityScores = new Map([["ann-1", 0.85]]);

      render(
        <TestWrapper>
          <AnnotationsPanel
            {...defaultProps}
            items={items}
            similarityScores={similarityScores}
          />
        </TestWrapper>
      );

      expect(screen.getByText("85%")).toBeInTheDocument();
    });
  });

  describe("Empty State", () => {
    it("shows empty state when items array is empty", () => {
      render(
        <TestWrapper>
          <AnnotationsPanel {...defaultProps} items={[]} />
        </TestWrapper>
      );

      expect(screen.getByText("No annotations found")).toBeInTheDocument();
    });

    it("shows custom empty message when provided", () => {
      render(
        <TestWrapper>
          <AnnotationsPanel
            {...defaultProps}
            items={[]}
            emptyStateMessage="No results for this corpus"
          />
        </TestWrapper>
      );

      expect(
        screen.getByText("No results for this corpus")
      ).toBeInTheDocument();
    });

    it("still shows filter tabs when empty", () => {
      render(
        <TestWrapper>
          <AnnotationsPanel {...defaultProps} items={[]} />
        </TestWrapper>
      );

      // Filter tabs should still be visible
      expect(screen.getByTestId("filter-tab-doc")).toBeInTheDocument();
      expect(screen.getByTestId("filter-tab-structural")).toBeInTheDocument();
    });

    it("shows semantic search empty state when isSemanticSearch is true", () => {
      render(
        <TestWrapper>
          <AnnotationsPanel
            {...defaultProps}
            items={[]}
            isSemanticSearch={true}
          />
        </TestWrapper>
      );

      expect(
        screen.getByText("No matching annotations found")
      ).toBeInTheDocument();
      expect(
        screen.getByText(/Try a different search query or adjust your filters/)
      ).toBeInTheDocument();
    });
  });

  describe("Loading State", () => {
    it("renders skeleton cards on initial load instead of a dark overlay", () => {
      // Issue #1560: the previous inverted LoadingOverlay painted a tall
      // near-black band over a flex container whose height was undefined.
      // The skeletons match the eventual ModernAnnotationCard layout and
      // give the grid a predictable height while data is fetched.
      const { container } = render(
        <TestWrapper>
          <AnnotationsPanel {...defaultProps} items={[]} loading={true} />
        </TestWrapper>
      );

      const skeletons = container.querySelectorAll('[aria-hidden="true"]');
      expect(skeletons.length).toBeGreaterThan(0);
      expect(
        screen.queryByText("Loading annotations...")
      ).not.toBeInTheDocument();
    });

    it("does not show empty state while loading", () => {
      render(
        <TestWrapper>
          <AnnotationsPanel {...defaultProps} items={[]} loading={true} />
        </TestWrapper>
      );

      expect(
        screen.queryByText("No annotations found")
      ).not.toBeInTheDocument();
    });
  });

  describe("Error State", () => {
    it("shows error banner when searchError is provided", () => {
      const error = new Error("Network error occurred");
      render(
        <TestWrapper>
          <AnnotationsPanel {...defaultProps} searchError={error} />
        </TestWrapper>
      );

      expect(screen.getByText(/Search failed:/)).toBeInTheDocument();
      expect(screen.getByText(/Network error occurred/)).toBeInTheDocument();
    });
  });
});

describe("applyLocalFilters", () => {
  const createAnnotations = (): ServerAnnotationType[] => [
    createMockAnnotation({
      id: "human-text",
      structural: false,
      annotationType: LabelType.TokenLabel,
    }),
    createMockAnnotation({
      id: "human-doc",
      structural: false,
      annotationType: "DOC_TYPE_LABEL" as LabelType,
    }),
    createMockAnnotation({
      id: "structural-text",
      structural: true,
      annotationType: LabelType.TokenLabel,
    }),
    createMockAnnotation({
      id: "agent-text",
      structural: false,
      annotationType: LabelType.TokenLabel,
      analysis: {
        id: "analysis-1",
        analyzer: { analyzerId: "gpt4_analyzer" },
      } as ServerAnnotationType["analysis"],
    }),
  ];

  it("returns all items when filters are 'all'", () => {
    const items = createAnnotations();
    const result = applyLocalFilters(items, "all", "all");
    expect(result).toHaveLength(4);
  });

  it("filters by type 'doc'", () => {
    const items = createAnnotations();
    const result = applyLocalFilters(items, "doc", "all");
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe("human-doc");
  });

  it("filters by type 'text'", () => {
    const items = createAnnotations();
    const result = applyLocalFilters(items, "text", "all");
    expect(result).toHaveLength(3);
  });

  it("filters by source 'human'", () => {
    const items = createAnnotations();
    const result = applyLocalFilters(items, "all", "human");
    expect(result).toHaveLength(2);
    expect(result.map((a) => a.id)).toEqual(["human-text", "human-doc"]);
  });

  it("filters by source 'structural'", () => {
    const items = createAnnotations();
    const result = applyLocalFilters(items, "all", "structural");
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe("structural-text");
  });

  it("filters by source 'agent'", () => {
    const items = createAnnotations();
    const result = applyLocalFilters(items, "all", "agent");
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe("agent-text");
  });

  it("combines type and source filters", () => {
    const items = createAnnotations();
    const result = applyLocalFilters(items, "text", "human");
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe("human-text");
  });

  it("removes duplicate items by id", () => {
    const items = [
      createMockAnnotation({ id: "dup-1" }),
      createMockAnnotation({ id: "dup-1" }), // duplicate
    ];
    const result = applyLocalFilters(items, "all", "all");
    expect(result).toHaveLength(1);
  });
});
