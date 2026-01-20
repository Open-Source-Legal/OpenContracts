import React, { useState, useEffect } from "react";
import { Popup } from "semantic-ui-react";
import { IconButton, Toggle, VStack } from "@os-legal/ui";
import styled from "styled-components";
import { SlidersHorizontal } from "lucide-react";
import { useAnnotationDisplay } from "../../annotator/hooks/useAnnotationDisplay"; // Adjusted path

const SettingsHeader = styled.h4`
  font-size: 1rem;
  font-weight: 600;
  color: #1e293b;
  margin: 0 0 0.8em 0;
  display: flex;
  align-items: center;
  gap: 0.5em;
`;

interface RelationshipViewSettingsPopupProps {
  // No specific props needed for now, but can be extended
}

export const RelationshipViewSettingsPopup: React.FC<
  RelationshipViewSettingsPopupProps
> = ({}) => {
  const { showStructuralRelationships, setShowStructuralRelationships } =
    useAnnotationDisplay();

  // Local state to manage the checkbox toggle immediately
  const [
    localShowStructuralRelationships,
    setLocalShowStructuralRelationships,
  ] = useState(showStructuralRelationships);

  // Effect to sync local state if global state changes (e.g., on initial load or from another source)
  useEffect(() => {
    setLocalShowStructuralRelationships(showStructuralRelationships);
  }, [showStructuralRelationships]);

  const handleShowStructuralRelationshipsChange = (checked: boolean) => {
    setLocalShowStructuralRelationships(checked);
    setShowStructuralRelationships(checked); // Update global state
  };

  return (
    <Popup
      className="RelationshipSettingsPopup"
      on="click"
      trigger={
        // Using a similar trigger style to ViewSettingsPopup
        <IconButton
          variant="primary"
          size="sm"
          aria-label="Relationship settings"
          style={{ position: "absolute", left: 0, top: 0 }}
        >
          <SlidersHorizontal size={16} />
        </IconButton>
      }
      style={{ padding: "1em", zIndex: "2100 !important" }} // Ensure it's above other elements
      position="bottom left" // Example position, adjust as needed
    >
      <VStack
        gap="sm"
        style={{
          width: "220px",
          background: "#f9f9f9",
          borderRadius: "8px",
          padding: "1em",
          textAlign: "center",
        }}
      >
        <SettingsHeader>
          <i className="icon sitemap" /> {/* Icon for structural/hierarchy */}
          Show Structural Groups
        </SettingsHeader>
        <Toggle
          onChange={(e) =>
            handleShowStructuralRelationshipsChange(e.target.checked)
          }
          checked={localShowStructuralRelationships}
        />
      </VStack>
    </Popup>
  );
};
