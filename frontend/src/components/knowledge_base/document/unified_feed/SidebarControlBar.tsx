import React, { useState, useRef, useEffect, memo, useCallback } from "react";
import styled from "styled-components";
import { motion, AnimatePresence } from "framer-motion";
import { OS_LEGAL_COLORS } from "../../../../assets/configurations/osLegalStyles";
import {
  FOCUS_RING,
  RADIUS,
  SHADOW,
} from "../../../../assets/configurations/designTokens";
import {
  MessageSquare,
  FileText,
  Filter,
  Check,
  ChevronDown,
  Search,
  Layers,
  ChartNetwork,
  Notebook,
  Eye,
  ArrowUpDown,
  SlidersHorizontal,
} from "lucide-react";
import { Dropdown } from "@os-legal/ui";
import {
  ContentFilters,
  SortOption,
  ContentItemType,
  SidebarViewMode,
} from "./types";
import { CollapsibleAnnotationControls } from "./CollapsibleAnnotationControls";

interface SidebarControlBarProps {
  /** Current view mode */
  viewMode: SidebarViewMode["mode"];
  /** Callback to change view mode */
  onViewModeChange: (mode: SidebarViewMode["mode"]) => void;
  /** Current filters (only used in feed mode) */
  filters: ContentFilters;
  /** Callback to update filters */
  onFiltersChange: (filters: ContentFilters) => void;
  /** Current sort option */
  sortBy: SortOption;
  /** Callback to update sort */
  onSortChange: (sort: SortOption) => void;
  /** Whether there's an active document search */
  hasActiveSearch?: boolean;
  /**
   * Compact / mobile consumption mode. When true the always-visible filter +
   * sort chrome collapses behind a single "Filter & sort" control (with a
   * count badge when any filter or sort deviates from defaults). Tapping it
   * reveals the full control set inline; collapsed by default so the feed
   * starts high and breathes. Desktop leaves this unset for byte-identical
   * rendering.
   */
  compact?: boolean;
}

/** The content-type set the feed ships with — all types selected. */
const DEFAULT_CONTENT_TYPES: ReadonlyArray<ContentItemType> = [
  "note",
  "annotation",
  "relationship",
  "search",
];
/** The feed's default sort. */
const DEFAULT_SORT: SortOption = "page";

/* Styled Components */
const ControlBarContainer = styled.div`
  background: white;
  /* Depth over borders: a soft downward shadow instead of a hairline. */
  border-bottom: none;
  box-shadow: 0 1px 8px rgba(15, 23, 42, 0.05);
  padding: 1rem 1.1rem;
  position: relative;
  z-index: 20;
`;

const FilterSection = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.7rem;
`;

const FilterRow = styled.div`
  display: flex;
  gap: 0.5rem;
  align-items: stretch;

  > * {
    flex: 1 1 0;
    min-width: 0;
  }
`;

const DropdownContainer = styled.div`
  position: relative;
  min-width: 0;
`;

/**
 * Soft-tinted ghost control. Lighter and less boxy than a heavy outlined box:
 * a faint surface tint at rest, an inset hairline for definition, and an
 * accent ring + lift when open.
 */
const MultiSelectDropdown = styled.div<{ $isOpen: boolean }>`
  position: relative;
  background: ${(props) =>
    props.$isOpen ? "white" : OS_LEGAL_COLORS.surfaceHover};
  border: none;
  border-radius: ${RADIUS.control};
  box-shadow: ${(props) =>
    props.$isOpen
      ? `inset 0 0 0 1px ${OS_LEGAL_COLORS.accent}, ${FOCUS_RING}, ${SHADOW.subtle}`
      : `inset 0 0 0 1px rgba(15, 23, 42, 0.06)`};
  cursor: pointer;
  transition: background 0.18s ease, box-shadow 0.18s ease;

  &:hover {
    background: white;
    box-shadow: ${(props) =>
      props.$isOpen
        ? `inset 0 0 0 1px ${OS_LEGAL_COLORS.accent}, ${FOCUS_RING}, ${SHADOW.subtle}`
        : `inset 0 0 0 1px rgba(15, 23, 42, 0.1), ${SHADOW.subtle}`};
  }
`;

const DropdownHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.6rem 0.75rem;
  gap: 0.4rem;
  min-height: 44px;
  min-width: 0;
`;

const DropdownLabel = styled.div`
  display: flex;
  align-items: center;
  gap: 0.45rem;
  font-size: 0.875rem;
  color: ${OS_LEGAL_COLORS.textPrimary};
  font-weight: 500;
  min-width: 0;
  /* Defect fix: never let "Content Types" / "Page Number" wrap to two lines —
     keep the label on one line and truncate gracefully when space is tight. */
  white-space: nowrap;

  /* The label text segment shrinks/ellipsises; icon + badge stay fixed. */
  > span.control-label-text {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    min-width: 0;
  }

  svg {
    width: 17px;
    height: 17px;
    flex-shrink: 0;
    color: ${OS_LEGAL_COLORS.accent};
  }
`;

const SelectedCount = styled.span`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  min-width: 18px;
  height: 18px;
  background: ${OS_LEGAL_COLORS.accent};
  color: white;
  padding: 0 0.4rem;
  border-radius: 999px;
  font-size: 0.6875rem;
  font-weight: 700;
  margin-left: 0.4rem;
`;

const ChevronIcon = styled(ChevronDown)<{ $isOpen: boolean }>`
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  color: ${OS_LEGAL_COLORS.textMuted};
  transform: rotate(${(props) => (props.$isOpen ? 180 : 0)}deg);
  transition: transform 0.2s ease;
`;

/**
 * Surface for the Sort trigger render-prop. The ``@os-legal/ui`` Dropdown
 * renders the ``trigger`` node directly, so this matches {@link
 * MultiSelectDropdown} to keep both feed controls visually consistent.
 */
const SortTriggerSurface = styled.div<{ $isOpen: boolean }>`
  position: relative;
  background: ${(props) =>
    props.$isOpen ? "white" : OS_LEGAL_COLORS.surfaceHover};
  border-radius: ${RADIUS.control};
  box-shadow: ${(props) =>
    props.$isOpen
      ? `inset 0 0 0 1px ${OS_LEGAL_COLORS.accent}, ${FOCUS_RING}, ${SHADOW.subtle}`
      : `inset 0 0 0 1px rgba(15, 23, 42, 0.06)`};
  cursor: pointer;
  transition: background 0.18s ease, box-shadow 0.18s ease;

  &:hover {
    background: white;
    box-shadow: ${(props) =>
      props.$isOpen
        ? `inset 0 0 0 1px ${OS_LEGAL_COLORS.accent}, ${FOCUS_RING}, ${SHADOW.subtle}`
        : `inset 0 0 0 1px rgba(15, 23, 42, 0.1), ${SHADOW.subtle}`};
  }
`;

const DropdownMenu = styled(motion.div)`
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  right: 0;
  background: white;
  border: none;
  border-radius: ${RADIUS.md};
  box-shadow: ${SHADOW.menu};
  z-index: 50;
  overflow: hidden;
`;

const DropdownMenuItem = styled.div<{ $isSelected?: boolean }>`
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.75rem 1rem;
  cursor: pointer;
  transition: background 0.15s ease, box-shadow 0.15s ease;
  background: ${(props) =>
    props.$isSelected ? OS_LEGAL_COLORS.accentSurface : "transparent"};
  box-shadow: inset 3px 0 0
    ${(props) => (props.$isSelected ? OS_LEGAL_COLORS.accent : "transparent")};

  &:hover {
    background: ${(props) =>
      props.$isSelected
        ? OS_LEGAL_COLORS.accentLight
        : OS_LEGAL_COLORS.surfaceHover};
  }
`;

const MenuItemLabel = styled.div`
  display: flex;
  align-items: center;
  gap: 0.625rem;
  font-size: 0.875rem;
  color: ${OS_LEGAL_COLORS.textPrimary};
  font-weight: 500;

  svg {
    width: 17px;
    height: 17px;
  }
`;

const CheckIcon = styled(Check)`
  width: 17px;
  height: 17px;
  color: ${OS_LEGAL_COLORS.accent};
`;

const QuickActions = styled.div`
  display: flex;
  gap: 0.5rem;
  padding: 0.7rem 0.85rem;
  background: ${OS_LEGAL_COLORS.surfaceHover};
`;

/** Soft-tinted ghost button — lighter than a flat outlined box. */
const QuickActionButton = styled.button`
  flex: 1;
  background: white;
  border: none;
  box-shadow: inset 0 0 0 1px rgba(15, 23, 42, 0.07);
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-size: 0.8125rem;
  font-weight: 600;
  cursor: pointer;
  padding: 0.5rem 0.875rem;
  border-radius: 9px;
  transition: background 0.18s ease, box-shadow 0.18s ease, color 0.18s ease,
    transform 0.12s ease;

  &:hover {
    background: white;
    box-shadow: inset 0 0 0 1px rgba(15, 23, 42, 0.12), ${SHADOW.subtle};
    color: ${OS_LEGAL_COLORS.textTertiary};
  }

  &:active {
    transform: scale(0.97);
    background: ${OS_LEGAL_COLORS.surfaceLight};
  }
`;

const SearchInputWrapper = styled.div`
  position: relative;
  flex: 1;
`;

const SearchIconWrapper = styled.div`
  position: absolute;
  left: 0.875rem;
  top: 50%;
  transform: translateY(-50%);
  color: ${OS_LEGAL_COLORS.textMuted};
  pointer-events: none;

  svg {
    width: 18px;
    height: 18px;
  }
`;

/** Crisp elevated search field — depth over borders, accent focus ring. */
const StyledSearchInput = styled.input`
  width: 100%;
  padding: 0.7rem 0.95rem 0.7rem 2.6rem;
  border: none;
  border-radius: ${RADIUS.control};
  font-size: 0.9rem;
  color: ${OS_LEGAL_COLORS.textPrimary};
  background: white;
  box-shadow: inset 0 0 0 1px rgba(15, 23, 42, 0.07), ${SHADOW.subtle};
  transition: box-shadow 0.18s ease;
  min-height: 44px;

  &::placeholder {
    color: ${OS_LEGAL_COLORS.textMuted};
  }

  &:hover {
    box-shadow: inset 0 0 0 1px rgba(15, 23, 42, 0.12), ${SHADOW.subtle};
  }

  &:focus {
    outline: none;
    box-shadow: inset 0 0 0 1px ${OS_LEGAL_COLORS.accent}, ${FOCUS_RING},
      ${SHADOW.raised};
  }
`;

const contentTypeIcons: Record<ContentItemType, React.ReactNode> = {
  note: <Notebook />,
  annotation: <FileText />,
  relationship: <ChartNetwork />,
  search: <Search />,
};

const contentTypeLabels: Record<ContentItemType, string> = {
  note: "Notes",
  annotation: "Annotations",
  relationship: "Relationships",
  search: "Search Results",
};

const contentTypeColors: Record<ContentItemType, string> = {
  note: OS_LEGAL_COLORS.folderIcon,
  annotation: OS_LEGAL_COLORS.primaryBlue,
  relationship: "#8b5cf6",
  search: OS_LEGAL_COLORS.greenMedium,
};

const AnnotationFiltersWrapper = styled(motion.div)`
  margin-top: 0.75rem;
`;

/* ── Compact (mobile) "Filter & sort" chrome ──────────────────────────────
 * On mobile the four desktop controls collapse behind a single trigger so the
 * annotation list starts high. Soft-tinted ghost styling mirrors the desktop
 * controls; depth over borders. */

/** Slim container for the collapsed mobile control — no heavy chrome padding. */
const CompactControlBar = styled.div`
  background: white;
  border-bottom: none;
  box-shadow: 0 1px 8px rgba(15, 23, 42, 0.05);
  padding: 0.55rem 0.7rem;
  position: relative;
  z-index: 20;
`;

/** Single soft-tinted "Filter & sort" toggle. */
const CompactToggle = styled.button<{ $isOpen: boolean; $isActive: boolean }>`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
  min-height: 44px;
  padding: 0.55rem 0.75rem;
  border: none;
  border-radius: ${RADIUS.control};
  cursor: pointer;
  font-size: 0.875rem;
  font-weight: 600;
  text-align: left;
  background: ${(props) =>
    props.$isOpen || props.$isActive
      ? OS_LEGAL_COLORS.accentSurface
      : OS_LEGAL_COLORS.surfaceHover};
  color: ${(props) =>
    props.$isOpen || props.$isActive
      ? OS_LEGAL_COLORS.accent
      : OS_LEGAL_COLORS.textSecondary};
  box-shadow: ${(props) =>
    props.$isOpen || props.$isActive
      ? `inset 0 0 0 1px ${OS_LEGAL_COLORS.accentMedium}`
      : `inset 0 0 0 1px rgba(15, 23, 42, 0.06)`};
  transition: background 0.18s ease, box-shadow 0.18s ease, color 0.18s ease;

  &:hover {
    background: ${(props) =>
      props.$isOpen || props.$isActive ? OS_LEGAL_COLORS.accentLight : "white"};
  }

  &:active {
    transform: scale(0.99);
  }

  > .compact-toggle-icon {
    width: 18px;
    height: 18px;
    flex-shrink: 0;
    color: ${(props) =>
      props.$isOpen || props.$isActive
        ? OS_LEGAL_COLORS.accent
        : OS_LEGAL_COLORS.textSecondary};
  }

  > .compact-toggle-label {
    flex: 1;
    min-width: 0;
  }
`;

/** Teal count badge — number of filter/sort dimensions deviating from default. */
const CompactBadge = styled.span`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  min-width: 18px;
  height: 18px;
  padding: 0 0.4rem;
  background: ${OS_LEGAL_COLORS.accent};
  color: white;
  border-radius: 999px;
  font-size: 0.6875rem;
  font-weight: 700;
`;

/** Inline expandable panel holding the full control set. */
const CompactExpandPanel = styled(motion.div)`
  overflow: hidden;
`;

/** Inner padding wrapper so the height animation has no padding jump. */
const CompactExpandInner = styled.div`
  padding-top: 0.6rem;
`;

/**
 * SidebarControlBar provides controls for switching between chat/feed views
 * and filtering content in the unified feed. Memoized to prevent unnecessary rerenders.
 */
export const SidebarControlBar: React.FC<SidebarControlBarProps> = memo(
  ({
    viewMode,
    onViewModeChange,
    filters,
    onFiltersChange,
    sortBy,
    onSortChange,
    hasActiveSearch = false,
    compact = false,
  }) => {
    const [searchQuery, setSearchQuery] = useState(filters.searchQuery || "");
    const [showContentDropdown, setShowContentDropdown] = useState(false);
    /* Mobile-only: the collapsed "Filter & sort" panel — closed by default so
       the annotation list starts high. */
    const [compactExpanded, setCompactExpanded] = useState(false);
    const dropdownRef = useRef<HTMLDivElement>(null);

    // Close dropdown when clicking outside
    useEffect(() => {
      const handleClickOutside = (event: MouseEvent) => {
        if (
          dropdownRef.current &&
          !dropdownRef.current.contains(event.target as Node)
        ) {
          setShowContentDropdown(false);
        }
      };

      if (showContentDropdown) {
        document.addEventListener("mousedown", handleClickOutside);
        return () =>
          document.removeEventListener("mousedown", handleClickOutside);
      }
    }, [showContentDropdown]);

    // Memoize callbacks to prevent child component rerenders
    const handleContentTypeToggle = useCallback(
      (type: ContentItemType) => {
        const newTypes = new Set(filters.contentTypes);
        if (newTypes.has(type)) {
          newTypes.delete(type);
        } else {
          newTypes.add(type);
        }
        onFiltersChange({ ...filters, contentTypes: newTypes });
      },
      [filters, onFiltersChange]
    );

    const handleSelectAll = useCallback(() => {
      const allTypes: ContentItemType[] = [
        "note",
        "annotation",
        "relationship",
      ];
      if (hasActiveSearch) allTypes.push("search");
      onFiltersChange({ ...filters, contentTypes: new Set(allTypes) });
    }, [filters, onFiltersChange, hasActiveSearch]);

    const handleClearAll = useCallback(() => {
      onFiltersChange({ ...filters, contentTypes: new Set() });
    }, [filters, onFiltersChange]);

    const handleSearchChange = useCallback(
      (value: string) => {
        setSearchQuery(value);
        // Debounced update to filters
        const timeoutId = setTimeout(() => {
          onFiltersChange({ ...filters, searchQuery: value || undefined });
        }, 300);
        return () => clearTimeout(timeoutId);
      },
      [filters, onFiltersChange]
    );

    const sortOptions = [
      { value: "page", label: "Page Number" },
      { value: "type", label: "Content Type" },
      { value: "date", label: "Date Created" },
    ];

    const availableContentTypes: ContentItemType[] = [
      "note",
      "annotation",
      "relationship",
    ];
    if (hasActiveSearch) availableContentTypes.push("search");

    const selectedCount = filters.contentTypes.size;

    // Check if annotations are selected
    const showAnnotationFilters =
      viewMode === "feed" && filters.contentTypes.has("annotation");

    /* Mobile badge: how many filter/sort dimensions deviate from the feed's
       defaults (all content types, sort by page, no search). */
    const contentTypesAreDefault =
      filters.contentTypes.size === DEFAULT_CONTENT_TYPES.length &&
      DEFAULT_CONTENT_TYPES.every((t) => filters.contentTypes.has(t));
    const compactActiveCount =
      (contentTypesAreDefault ? 0 : 1) +
      (sortBy !== DEFAULT_SORT ? 1 : 0) +
      (searchQuery.trim() ? 1 : 0);

    // Don't show control bar in chat mode at all
    if (viewMode === "chat") {
      return null;
    }

    /* Shared control set — identical markup for desktop (always visible) and
       mobile (revealed inside the collapsed "Filter & sort" panel). */
    const filterSection = (
      <FilterSection>
        {/* Search Input */}
        <SearchInputWrapper>
          <SearchIconWrapper>
            <Search />
          </SearchIconWrapper>
          <StyledSearchInput
            placeholder="Search in content..."
            value={searchQuery}
            onChange={(e) => handleSearchChange(e.target.value)}
          />
        </SearchInputWrapper>

        {/* Content Types and Sort Row */}
        <FilterRow>
          {/* Content Type Multi-Select */}
          <DropdownContainer ref={dropdownRef}>
            <MultiSelectDropdown
              $isOpen={showContentDropdown}
              onClick={() => setShowContentDropdown(!showContentDropdown)}
            >
              <DropdownHeader>
                <DropdownLabel>
                  <Filter />
                  <span className="control-label-text">Content Types</span>
                  {selectedCount > 0 && (
                    <SelectedCount>{selectedCount}</SelectedCount>
                  )}
                </DropdownLabel>
                <ChevronIcon $isOpen={showContentDropdown} />
              </DropdownHeader>
            </MultiSelectDropdown>

            <AnimatePresence>
              {showContentDropdown && (
                <DropdownMenu
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  transition={{ duration: 0.15 }}
                >
                  {availableContentTypes.map((type) => (
                    <DropdownMenuItem
                      key={type}
                      $isSelected={filters.contentTypes.has(type)}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleContentTypeToggle(type);
                      }}
                    >
                      <MenuItemLabel style={{ color: contentTypeColors[type] }}>
                        {contentTypeIcons[type]}
                        {contentTypeLabels[type]}
                      </MenuItemLabel>
                      {filters.contentTypes.has(type) && <CheckIcon />}
                    </DropdownMenuItem>
                  ))}
                  <QuickActions>
                    <QuickActionButton
                      onClick={(e) => {
                        e.stopPropagation();
                        handleSelectAll();
                      }}
                    >
                      Select All
                    </QuickActionButton>
                    <QuickActionButton
                      onClick={(e) => {
                        e.stopPropagation();
                        handleClearAll();
                      }}
                    >
                      Clear All
                    </QuickActionButton>
                  </QuickActions>
                </DropdownMenu>
              )}
            </AnimatePresence>
          </DropdownContainer>

          {/* Sort Dropdown */}
          <Dropdown
            mode="select"
            fluid
            options={sortOptions}
            value={sortBy}
            onChange={(value) => onSortChange(value as SortOption)}
            placeholder="Sort by..."
            trigger={(state) => (
              <SortTriggerSurface $isOpen={state.isOpen}>
                <DropdownHeader>
                  <DropdownLabel>
                    <ArrowUpDown />
                    <span className="control-label-text">
                      {state.selectedOption &&
                      !Array.isArray(state.selectedOption)
                        ? state.selectedOption.label
                        : state.placeholder}
                    </span>
                  </DropdownLabel>
                  <ChevronIcon $isOpen={state.isOpen} />
                </DropdownHeader>
              </SortTriggerSurface>
            )}
          />
        </FilterRow>

        {/* Annotation-specific Filters - Collapsible */}
        <AnimatePresence>
          {showAnnotationFilters && (
            <AnnotationFiltersWrapper
              initial={{ opacity: 0, height: 0, marginTop: 0 }}
              animate={{
                opacity: 1,
                height: "auto",
                marginTop: "0.75rem",
              }}
              exit={{ opacity: 0, height: 0, marginTop: 0 }}
              transition={{ duration: 0.2 }}
            >
              <CollapsibleAnnotationControls showLabelFilters />
            </AnnotationFiltersWrapper>
          )}
        </AnimatePresence>
      </FilterSection>
    );

    /* Mobile: collapse the whole control set behind one "Filter & sort"
       trigger so the annotation list starts high and breathes. */
    if (compact) {
      return (
        <CompactControlBar>
          <CompactToggle
            type="button"
            $isOpen={compactExpanded}
            $isActive={compactActiveCount > 0}
            onClick={() => setCompactExpanded((v) => !v)}
            aria-expanded={compactExpanded}
            data-testid="compact-filter-sort-toggle"
          >
            <SlidersHorizontal className="compact-toggle-icon" />
            <span className="compact-toggle-label">Filter &amp; sort</span>
            {compactActiveCount > 0 && (
              <CompactBadge>{compactActiveCount}</CompactBadge>
            )}
            <ChevronIcon $isOpen={compactExpanded} />
          </CompactToggle>
          <AnimatePresence initial={false}>
            {compactExpanded && (
              <CompactExpandPanel
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.2, ease: "easeOut" }}
              >
                <CompactExpandInner>{filterSection}</CompactExpandInner>
              </CompactExpandPanel>
            )}
          </AnimatePresence>
        </CompactControlBar>
      );
    }

    return <ControlBarContainer>{filterSection}</ControlBarContainer>;
  }
);

SidebarControlBar.displayName = "SidebarControlBar";
