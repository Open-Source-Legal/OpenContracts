import React, { useState } from "react";
import {
  ContextMenu,
  ContextMenuItem,
} from "../src/components/widgets/context-menu/ContextMenu";

/** Stateful wrapper so tests can assert onClose / onClick callbacks */
export const ContextMenuHarness: React.FC<{
  items?: ContextMenuItem[];
  position?: { x: number; y: number };
  header?: string;
  "aria-label"?: string;
}> = ({
  items: itemsProp,
  position = { x: 100, y: 100 },
  header,
  "aria-label": ariaLabel,
}) => {
  const [open, setOpen] = useState(true);
  const [lastClicked, setLastClicked] = useState<string | null>(null);

  const defaultItems: ContextMenuItem[] = [
    {
      key: "edit",
      label: "Edit",
      onClick: () => setLastClicked("edit"),
    },
    {
      key: "view",
      label: "View Details",
      variant: "primary",
      onClick: () => setLastClicked("view"),
    },
    {
      key: "hidden",
      label: "Hidden Item",
      visible: false,
      onClick: () => setLastClicked("hidden"),
    },
    {
      key: "delete",
      label: "Delete",
      variant: "danger",
      onClick: () => setLastClicked("delete"),
    },
  ];

  const items = itemsProp ?? defaultItems;

  return (
    <div
      style={{ width: "100vw", height: "100vh", background: "#f5f5f5" }}
      data-testid="harness-root"
    >
      {open ? (
        <ContextMenu
          items={items}
          position={position}
          onClose={() => setOpen(false)}
          header={header}
          aria-label={ariaLabel}
        />
      ) : (
        <div data-testid="menu-closed">Menu closed</div>
      )}
      {lastClicked && (
        <div data-testid="last-clicked">Clicked: {lastClicked}</div>
      )}
    </div>
  );
};
