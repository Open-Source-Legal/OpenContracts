import React, { forwardRef } from "react";
import { Input } from "@os-legal/ui";
import { useState, useRef, useEffect } from "react";
import { Filter, Plus } from "lucide-react";
import { DynamicIcon } from "../widgets/icon-picker/DynamicIcon";
import styled from "styled-components";
import Dropdown from "../common/Dropdown";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";

/**
 * Props for each dropdown action item.
 */
export interface DropdownActionProps {
  icon: string;
  title: string;
  key: string;
  color: string;
  action_function: (args?: any) => any | void;
}

/**
 * Props for the CreateAndSearchBar component.
 */
interface CreateAndSearchBarProps {
  actions: DropdownActionProps[];
  filters?: JSX.Element;
  placeholder?: string;
  value?: string;
  style?: React.CSSProperties;
  onChange?: (search_string: string) => any | void;
}

/**
 * CreateAndSearchBar component provides a search input with optional filter and action dropdowns.
 *
 * @param {CreateAndSearchBarProps} props - The properties passed to the component.
 * @returns {JSX.Element} The rendered search bar component.
 */
export const CreateAndSearchBar: React.FC<CreateAndSearchBarProps> = ({
  actions,
  filters,
  placeholder = "Search...",
  value = "",
  style,
  onChange,
}) => {
  const actionItems = actions.map((action) => (
    <Dropdown.Item
      key={action.key}
      onClick={action.action_function}
      icon={<DynamicIcon name={action.icon} size={16} />}
      text={action.title}
    />
  ));

  const [showFilter, setShowFilter] = useState(false);
  const filterRef = useRef<HTMLDivElement>(null);

  // Close filter popover when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        filterRef.current &&
        !filterRef.current.contains(event.target as Node)
      ) {
        setShowFilter(false);
      }
    };
    if (showFilter) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [showFilter]);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (onChange) {
      onChange(e.target.value);
    }
  };

  return (
    <SearchBarContainer style={style}>
      <SearchInputWrapper>
        <StyledInputWrapper>
          <Input
            placeholder={placeholder}
            value={value}
            onChange={handleInputChange}
            fullWidth
          />
        </StyledInputWrapper>
      </SearchInputWrapper>

      <ActionsWrapper>
        {filters && (
          <div ref={filterRef} style={{ position: "relative" }}>
            <StyledButton
              aria-label="Filter"
              onClick={() => setShowFilter(!showFilter)}
            >
              <Filter size={16} />
            </StyledButton>
            {showFilter && (
              <FilterPopoverContent>{filters}</FilterPopoverContent>
            )}
          </div>
        )}

        {actions.length > 0 && (
          <StyledButtonGroup>
            <Dropdown
              align="right"
              trigger={
                <StyledButton aria-label="Add">
                  <Plus size={16} />
                </StyledButton>
              }
            >
              <Dropdown.Menu>{actionItems}</Dropdown.Menu>
            </Dropdown>
          </StyledButtonGroup>
        )}
      </ActionsWrapper>
    </SearchBarContainer>
  );
};

/**
 * Styled button that forwards refs properly and uses a native button element.
 *
 * @param {React.ButtonHTMLAttributes<HTMLButtonElement>} props - Button properties.
 * @param {React.Ref<HTMLButtonElement>} ref - Reference to the button element.
 * @returns {JSX.Element} The styled button component.
 */
const StyledButton = styled(
  forwardRef<HTMLButtonElement, React.ButtonHTMLAttributes<HTMLButtonElement>>(
    (props, ref) => (
      <button {...props} ref={ref}>
        {props.children}
      </button>
    )
  )
)`
  /* Reset button styles */
  appearance: none;
  border: none;
  cursor: pointer;

  /* Base styles */
  background: var(--background-subtle, #f0f2f5);
  color: var(--text-primary, #1a2433);
  padding: 0.65em;
  min-width: 2.3em;
  height: 2.3em;
  border-radius: 12px;
  font-size: 0.95rem;
  position: relative;
  overflow: hidden;
  backdrop-filter: blur(8px);

  /* Flexbox for icon alignment */
  display: inline-flex;
  align-items: center;
  justify-content: center;

  /* Smooth transitions */
  transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
  transform-origin: center;

  /* Icon styling */
  svg,
  i.icon {
    margin: 0 !important;
    font-size: 1em;
    height: auto;
    width: auto;
    opacity: 0.85;
    position: relative;
    z-index: 2;
    transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
  }

  /* Dynamic background gradient */
  background: linear-gradient(
    135deg,
    var(--background-subtle, #f0f2f5) 0%,
    var(--background-hover, ${OS_LEGAL_COLORS.border}) 100%
  );
  background-size: 200% 200%;
  background-position: 0% 0%;

  /* Subtle border */
  box-shadow:
    inset 0 0 0 1px rgba(255, 255, 255, 0.1),
    0 2px 4px rgba(0, 0, 0, 0.05),
    0 1px 2px rgba(0, 0, 0, 0.1);

  /* Hover state */
  &:hover {
    transform: translateY(-1px) scale(1.02);
    background-position: 100% 100%;
    box-shadow:
      inset 0 0 0 1px rgba(255, 255, 255, 0.2),
      0 4px 8px rgba(0, 0, 0, 0.1),
      0 2px 4px rgba(0, 0, 0, 0.1);

    svg,
    i.icon {
      opacity: 1;
      transform: scale(1.1) rotate(8deg);
    }
  }

  /* Active state */
  &:active {
    transform: translateY(1px) scale(0.98);
    box-shadow:
      inset 0 0 0 1px rgba(255, 255, 255, 0.1),
      0 1px 2px rgba(0, 0, 0, 0.1);
    background-position: 50% 50%;
  }

  /* Focus state */
  &:focus {
    outline: none;
    box-shadow:
      0 0 0 2px #4285f4,
      0 0 0 4px rgba(66, 133, 244, 0.2);
  }

  /* Special styling for the add button */
  &[aria-label="Add"] {
    background: #4285f4;
    color: white;
    box-shadow:
      0 2px 4px rgba(66, 133, 244, 0.2),
      0 4px 8px rgba(66, 133, 244, 0.1);

    svg,
    i.icon {
      opacity: 1;
    }

    &:hover {
      background: #5c9aff;
      box-shadow:
        0 4px 8px rgba(66, 133, 244, 0.3),
        0 8px 16px rgba(66, 133, 244, 0.2);
    }

    &:active {
      background: #3b78e7;
      box-shadow: 0 2px 4px rgba(66, 133, 244, 0.2);
    }
  }

  /* Disabled state */
  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
    transform: none;
    box-shadow: none;
  }
`;

/**
 * Container for the search bar, removing the blue tint and applying a neutral background.
 */
const SearchBarContainer = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem;
  background: #ffffff;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  border-radius: 12px;
`;

/**
 * Wrapper for the search input to control its growth and margin.
 */
const SearchInputWrapper = styled.div`
  flex-grow: 1;
  margin-right: 1rem;
  max-width: 50vw;
`;

/**
 * Styled wrapper for the search input with customized border and focus effects.
 */
const StyledInputWrapper = styled.div`
  input {
    border-radius: 20px !important;
    border: 1px solid #ccc !important;
    transition: all 0.3s ease;

    &:focus {
      box-shadow: 0 0 0 2px #aaa;
    }
  }
`;

/**
 * Wrapper for action buttons, aligning them with appropriate spacing.
 */
const ActionsWrapper = styled.div`
  display: flex;
  align-items: center;
  gap: 0.75rem;
`;

/**
 * Styled button group removing unnecessary styling to ensure sane sizing.
 */
const StyledButtonGroup = styled.div`
  display: flex;
  align-items: center;
`;

/**
 * Content container for the filter popup - modern, minimal design
 */
const FilterPopoverContent = styled.div`
  padding: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
  min-width: 300px;
  max-width: 400px;

  /* Modern glassmorphism effect */
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);

  /* Subtle border and shadow for depth */
  border: 1px solid rgba(0, 0, 0, 0.06);
  border-radius: 16px;
  box-shadow:
    0 4px 6px -1px rgba(0, 0, 0, 0.08),
    0 2px 4px -1px rgba(0, 0, 0, 0.04),
    0 20px 25px -5px rgba(0, 0, 0, 0.1),
    inset 0 1px 0 0 rgba(255, 255, 255, 0.5);

  /* Allow dropdowns to overflow the container */
  overflow: visible !important;
  position: absolute;
  top: calc(100% + 10px);
  right: 0;
  z-index: 100;

  /* Smooth appearance animation */
  animation: filterPopupAppear 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);
  transform-origin: top right;

  @keyframes filterPopupAppear {
    from {
      opacity: 0;
      transform: scale(0.95) translateY(-8px);
    }
    to {
      opacity: 1;
      transform: scale(1) translateY(0);
    }
  }

  /* Ensure high z-index for dropdowns */
  & > * {
    position: relative;
    z-index: 1;
  }

  /* SUI Dropdown z-index fix */
  .ui.dropdown .menu {
    z-index: 1000 !important;
  }
`;
