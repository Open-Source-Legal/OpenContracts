import React, { useState, useEffect } from "react";
import { Popup, Grid, Header } from "semantic-ui-react";
import { IconButton, Toggle } from "@os-legal/ui";
import { SlidersHorizontal } from "lucide-react";
import { useAnnotationDisplay } from "../../annotator/hooks/useAnnotationDisplay"; // Adjusted path

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
      <Grid
        celled="internally"
        columns="equal"
        style={{
          width: `220px`, // Adjusted width for a single setting
          background: "#f9f9f9",
          borderRadius: "8px",
        }}
      >
        <Grid.Row>
          <Grid.Column textAlign="center" verticalAlign="middle">
            <Header size="tiny" style={{ marginBottom: "0.8em" }}>
              <i className="icon sitemap" />{" "}
              {/* Icon for structural/hierarchy */}
              Show Structural Groups
            </Header>
            <Toggle
              onChange={(e) =>
                handleShowStructuralRelationshipsChange(e.target.checked)
              }
              checked={localShowStructuralRelationships}
            />
          </Grid.Column>
        </Grid.Row>
      </Grid>
    </Popup>
  );
};
