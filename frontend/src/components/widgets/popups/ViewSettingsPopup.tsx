import React, { useState, useEffect } from "react";
import {
  Popup,
  Grid,
  Header,
  Dropdown,
  Label,
  DropdownItemProps,
} from "semantic-ui-react";
import { Toggle } from "@os-legal/ui";
import { ViewLabelSelector } from "../../annotator/labels/view_labels_selector/ViewLabelSelector";
import { LabelDisplayBehavior } from "../../../types/graphql-api";
import { useAnnotationDisplay } from "../../annotator/context/UISettingsAtom";
import { useNavigate, useLocation } from "react-router-dom";
import { updateAnnotationDisplayParams } from "../../../utils/navigationUtils";

interface ViewSettingsPopupProps {
  label_display_options: DropdownItemProps[];
}

export const ViewSettingsPopup: React.FC<ViewSettingsPopupProps> = ({
  label_display_options,
}) => {
  // Only read reactive var values - updates go through URL utilities
  const { showLabels, showStructural, showSelectedOnly, showBoundingBoxes } =
    useAnnotationDisplay();

  const navigate = useNavigate();
  const location = useLocation();

  const [localShowSelected, setLocalShowSelected] = useState(showSelectedOnly);
  const [localShowStructural, setLocalShowStructural] =
    useState(showStructural);
  const [localShowBoundingBoxes, setLocalShowBoundingBoxes] =
    useState(showBoundingBoxes);
  const [localLabelBehavior, setLocalLabelBehavior] = useState(showLabels);

  // Sync local state when reactive vars change (from CentralRouteManager Phase 2)
  useEffect(() => {
    setLocalShowSelected(showSelectedOnly);
    setLocalShowStructural(showStructural);
    setLocalShowBoundingBoxes(showBoundingBoxes);
    setLocalLabelBehavior(showLabels);
  }, [showLabels, showStructural, showBoundingBoxes, showSelectedOnly]);

  const handleShowSelectedChange = (checked: boolean) => {
    setLocalShowSelected(checked);
    // Update URL - CentralRouteManager Phase 2 will set reactive var
    updateAnnotationDisplayParams(location, navigate, {
      showSelectedOnly: checked,
    });
  };

  const handleShowStructuralChange = () => {
    const newStructuralValue = !localShowStructural;
    setLocalShowStructural(newStructuralValue);

    // Use navigationUtils helper to batch URL updates atomically
    // When enabling structural, force "show selected only" to be true
    updateAnnotationDisplayParams(location, navigate, {
      showStructural: newStructuralValue,
      showSelectedOnly: newStructuralValue ? true : undefined,
    });

    // Update local state for immediate UI feedback
    if (newStructuralValue) {
      setLocalShowSelected(true);
    }
  };

  const handleShowBoundingBoxesChange = (checked: boolean) => {
    setLocalShowBoundingBoxes(checked);
    // Update URL - CentralRouteManager Phase 2 will set reactive var
    updateAnnotationDisplayParams(location, navigate, {
      showBoundingBoxes: checked,
    });
  };

  const handleLabelBehaviorChange = (value: LabelDisplayBehavior) => {
    setLocalLabelBehavior(value);
    // Update URL - CentralRouteManager Phase 2 will set reactive var
    updateAnnotationDisplayParams(location, navigate, {
      labelDisplay: value,
    });
  };

  return (
    <Popup
      id="view-settings-popup"
      className="SettingsPopup"
      on="click"
      trigger={
        <Label
          id="view-settings-trigger"
          as="a"
          corner="left"
          icon="sliders horizontal"
          color="violet"
        />
      }
      style={{ padding: "1em", zIndex: "2100 !important" }}
    >
      <Grid
        id="view-settings-popup-grid"
        celled="internally"
        columns="equal"
        style={{
          width: `420px`,
          background: "#f9f9f9",
          borderRadius: "8px",
        }}
      >
        <Grid.Row>
          <Grid.Column textAlign="center" verticalAlign="middle">
            <Header size="tiny" style={{ marginBottom: "0.8em" }}>
              <i className="icon user outline" />
              Show Only Selected
            </Header>
            <Toggle
              onChange={(e) => handleShowSelectedChange(e.target.checked)}
              checked={localShowSelected}
              disabled={localShowStructural}
            />
          </Grid.Column>

          <Grid.Column textAlign="center" verticalAlign="middle">
            <Header size="tiny" style={{ marginBottom: "0.8em" }}>
              <i className="icon square outline" />
              Show Bounding Boxes
            </Header>
            <Toggle
              onChange={(e) => handleShowBoundingBoxesChange(e.target.checked)}
              checked={localShowBoundingBoxes}
            />
          </Grid.Column>
        </Grid.Row>
        <Grid.Row>
          <Grid.Column textAlign="center" verticalAlign="middle">
            <Header size="tiny" style={{ marginBottom: "0.8em" }}>
              <i className="icon sitemap" />
              Show Structural
            </Header>
            <Toggle
              data-testid="toggle-show-structural"
              onChange={handleShowStructuralChange}
              checked={localShowStructural}
            />
          </Grid.Column>
          <Grid.Column textAlign="center" verticalAlign="middle">
            <Header size="tiny" style={{ marginBottom: "0.8em" }}>
              <i className="icon tags" />
              Label Display
            </Header>
            <Dropdown
              onChange={(e, { value }) =>
                handleLabelBehaviorChange(value as LabelDisplayBehavior)
              }
              options={label_display_options}
              selection
              value={localLabelBehavior}
              style={{ minWidth: "12em" }}
            />
          </Grid.Column>
        </Grid.Row>
        <Grid.Row>
          <Grid.Column textAlign="center" verticalAlign="middle" width={16}>
            <Header size="tiny" style={{ marginBottom: "0.8em" }}>
              <i className="icon filter" />
              Label Filter
            </Header>
            <ViewLabelSelector />
          </Grid.Column>
        </Grid.Row>
      </Grid>
    </Popup>
  );
};
