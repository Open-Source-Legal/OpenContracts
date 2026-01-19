import React, { useState, useRef, useEffect } from "react";
import {
  Form,
  Icon as SemanticIcon,
  Popup,
  Menu,
  SemanticICONS,
} from "semantic-ui-react";
import { Search, X } from "lucide-react";
import styled from "styled-components";
import _ from "lodash";
import { ZoomButtonGroup } from "../../../widgets/buttons/ZoomButtonGroup";
import { useSearchText } from "../../context/DocumentAtom";
import { useTextSearch } from "../../hooks/useTextSearch";
import { ChangeEvent } from "react";

const ActionBarContainer = styled.div`
  position: sticky;
  top: 0;
  z-index: 500;
  padding: 8px 16px;
  background-color: #f8f9fa;
  border-bottom: 1px solid #e9ecef;
  height: 60px;
  display: flex;
  align-items: center;
`;

const StyledMenu = styled.div`
  display: flex;
  align-items: center;
  gap: 16px;
`;

const StyledSearchInput = styled(Form.Input)`
  width: 50%;
  max-width: 400px;

  .ui.input {
    width: 100%;
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  }

  input {
    border: none !important;
    padding-left: 2.67142857em !important;
  }

  i.icon {
    height: 100%;
    display: flex !important;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    left: 10px !important;
  }
`;

interface PDFActionBarProps {
  zoom: number;
  onZoomIn: () => void;
  onZoomOut: () => void;
  actionItems: {
    key: string;
    text: string;
    value: CallableFunction;
    icon?: SemanticICONS;
  }[];
  onActionSelect?: (value: string) => void;
}

/**
 * Debounce delay in milliseconds for search input
 */
const DEBOUNCE_DELAY = 600;

/**
 * Action bar for the PDF viewer, including zoom controls and a search bar.
 */
export const PDFActionBar: React.FC<PDFActionBarProps> = ({
  zoom,
  onZoomIn,
  onZoomOut,
  actionItems,
  onActionSelect,
}) => {
  const { searchText, setSearchText } = useSearchText();
  const [localSearchText, setLocalSearchText] = useState(searchText);
  const [isPopupOpen, setIsPopupOpen] = useState(false);
  const lastSearchRef = useRef<string>("");
  const isUserInitiatedRef = useRef<boolean>(false);
  const debouncedFnRef = useRef<_.DebouncedFunc<(value: string) => void>>();
  useTextSearch();

  // Keep localSearchText in sync with global searchText
  useEffect(() => {
    setLocalSearchText(searchText || "");
  }, [searchText]);

  // Create a memoized debounced function with proper typing
  useEffect(() => {
    debouncedFnRef.current = _.debounce((value: string) => {
      console.log(
        "Debounced search triggered with:",
        value,
        "isUserInitiated:",
        isUserInitiatedRef.current
      );
      if (!isUserInitiatedRef.current) {
        console.log("Skipping non-user-initiated search update");
        return;
      }
      // Only trigger search for strings of length 2 or more
      if (value.length >= 2) {
        // Only update if the value has actually changed
        if (lastSearchRef.current !== value) {
          console.log("Setting search text to:", value);
          lastSearchRef.current = value;
          setSearchText(value);
        }
      } else if (lastSearchRef.current !== "") {
        // Clear results for empty or single character strings
        console.log("Clearing search results");
        lastSearchRef.current = "";
        setSearchText("");
      }
      isUserInitiatedRef.current = false;
    }, DEBOUNCE_DELAY);

    return () => {
      debouncedFnRef.current?.cancel();
    };
  }, [setSearchText]);

  // Track search text changes
  useEffect(() => {
    console.log(
      "Search text changed to:",
      searchText,
      "local:",
      localSearchText
    );
  }, [searchText, localSearchText]);

  const handleDocSearchChange = (e: ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    console.log("Doc search change:", value);
    isUserInitiatedRef.current = true;
    // Update local state immediately for UI responsiveness
    setLocalSearchText(value);
    // Debounce the actual search operation
    debouncedFnRef.current?.(value);
  };

  const clearSearch = () => {
    console.log("Clear search triggered");
    isUserInitiatedRef.current = true;
    // Update local state immediately for UI responsiveness
    setLocalSearchText("");
    lastSearchRef.current = "";
    // Clear results immediately for explicit clear action
    setSearchText("");
    // Cancel any pending debounced operations
    debouncedFnRef.current?.cancel();
  };

  const handleActionClick = () => {
    setIsPopupOpen(!isPopupOpen);
  };

  const handleMenuItemClick = (value: CallableFunction) => {
    value();
    setIsPopupOpen(false);
  };

  const actionMenu = (
    <Menu vertical>
      {actionItems.map((item) => (
        <Menu.Item
          key={item.key}
          onClick={() => handleMenuItemClick(item.value)}
        >
          {item.icon && <SemanticIcon name={item.icon} />}
          {item.text}
        </Menu.Item>
      ))}
    </Menu>
  );

  return (
    <ActionBarContainer>
      <StyledMenu>
        <Popup
          trigger={
            <ZoomButtonGroup
              onZoomOut={onZoomOut}
              onZoomIn={onZoomIn}
              zoomLevel={zoom}
              onActionClick={handleActionClick}
            />
          }
          style={{ zIndex: 9999 }}
          content={actionMenu}
          on="click"
          position="bottom right"
          open={isPopupOpen}
          onClose={() => setIsPopupOpen(false)}
          onOpen={() => setIsPopupOpen(true)}
        />
        <StyledSearchInput
          icon={
            <span
              className="icon"
              style={{
                cursor: localSearchText ? "pointer" : "default",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
              onClick={() => (localSearchText ? clearSearch() : undefined)}
            >
              {localSearchText ? (
                <X size={16} style={{ color: "#db2828" }} />
              ) : (
                <Search size={16} style={{ color: "#2185d0" }} />
              )}
            </span>
          }
          iconPosition="left"
          placeholder="Search document..."
          value={localSearchText}
          onChange={handleDocSearchChange}
        />
      </StyledMenu>
    </ActionBarContainer>
  );
};
