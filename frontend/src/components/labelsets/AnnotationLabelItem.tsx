import React from "react";
import _ from "lodash";
import styled from "styled-components";
import { Card, Popup, Statistic, Menu } from "semantic-ui-react";
import { CheckCircle } from "lucide-react";

import default_icon from "../../assets/images/defaults/default_tag.png";
import { LabelSetType } from "../../types/graphql-api";
import { getPermissions } from "../../utils/transform";
import { PermissionTypes } from "../types";
import { MyPermissionsIndicator } from "../widgets/permissions/MyPermissionsIndicator";

const CardImage = styled.img`
  width: 100%;
  height: 200px;
  object-fit: cover;
  display: block;
`;

interface AnnotationLabelItemProps {
  item: LabelSetType;
  selected: boolean;
  opened: boolean;
  onOpen: (args: any) => void | any;
  onSelect: (args: any) => void | any;
  onDelete: (args: any) => void | any;
  contextMenuOpen: string | null;
  setContextMenuOpen: (args: any) => void | any;
}

interface ContextMenuItem {
  key: string;
  content: string;
  icon: string;
  onClick: () => void;
}

const AnnotationLabelItem = ({
  item,
  selected,
  opened,
  onOpen,
  onSelect,
  onDelete,
  contextMenuOpen,
  setContextMenuOpen,
}: AnnotationLabelItemProps) => {
  const {
    id,
    title,
    description,
    creator,
    icon,
    annotationLabels,
    isPublic,
    myPermissions,
  } = item;

  const cardClickHandler = (
    event: React.MouseEvent<HTMLAnchorElement, MouseEvent>,
    value: any
  ) => {
    event.stopPropagation();
    if (event.shiftKey) {
      if (onSelect && _.isFunction(onSelect)) {
        onSelect(id);
      }
    } else {
      if (onOpen && _.isFunction(onOpen)) {
        onOpen(id);
      }
    }
  };

  const createContextFromEvent = (
    e: React.MouseEvent<HTMLElement>
  ): HTMLElement => {
    const left = e.clientX;
    const top = e.clientY;
    const right = left + 1;
    const bottom = top + 1;

    // This is insanely hacky, but I know this is all semantic UI uses from the HTMLElement API based o
    // on their docs. When I switched from JS to Typescript, however, you get errors because obv an
    // HTMLElement needs a lot more than just getBoundingClientRect. Overriding TypeScript type on return
    // with as HTMLElement makes TypeScript shut up and lets us have a properly positioned context menu.
    // Perhaps at some point worth figuring out what actual types work, but it's burning up my time for
    // very little benefit.

    // Looks like my old code (in JS) was implicitly returning an object that implemented ClientRect.
    // However, ClientRect is deprecated: https://docs.microsoft.com/en-us/previous-versions/hh826029(v=vs.85)
    // and proper return type for getBoundingClientRect is now  a DOMRect:
    // https://developer.mozilla.org/en-US/docs/Web/API/Element/getBoundingClientRect#notes
    //
    return {
      getBoundingClientRect: () => ({
        left,
        top,
        right,
        bottom,
        height: 0,
        width: 0,
      }),
    } as HTMLElement;
  };

  const contextRef = React.useRef<HTMLElement | null>(null);

  ///////////////////////////////// VARY USER ACTIONS BASED ON PERMISSIONS ////////////////////////////////////////
  const my_permissions = getPermissions(
    item.myPermissions ? item.myPermissions : []
  );

  let context_menus: ContextMenuItem[] = [];
  if (my_permissions.includes(PermissionTypes.CAN_REMOVE)) {
    context_menus.push({
      key: "delete",
      content: "Delete Item",
      icon: "trash",
      onClick: () => onDelete(id),
    });
  }
  context_menus.push({
    key: "view",
    content: "View Details",
    icon: "eye",
    onClick: () => onOpen(id),
  });
  //////////////////////////////////////////////////////////////////////////////////////////////////////////////////

  return (
    <>
      <Card
        className="noselect"
        key={id}
        style={opened ? { backgroundColor: "#e2ffdb" } : {}}
        onClick={cardClickHandler}
        onContextMenu={(e: React.MouseEvent<HTMLElement>) => {
          e.preventDefault();
          contextRef.current = createContextFromEvent(e);
          if (contextMenuOpen === id) {
            setContextMenuOpen(-1);
          } else {
            setContextMenuOpen(id);
          }
        }}
        onMouseEnter={() => {
          if (contextMenuOpen !== id) {
            setContextMenuOpen(-1);
          }
        }}
      >
        <CardImage src={icon ? icon : default_icon} alt="Label Set Icon" />
        <Card.Content>
          <Card.Header>
            <Popup
              content={`Full Title: ${title ? title : "None Provided"}`}
              trigger={<span>{title ? title.substring(0, 48) : ""}</span>}
            />
            {selected ? (
              <div style={{ float: "right" }}>
                <CheckCircle size={20} color="green" />
              </div>
            ) : (
              <></>
            )}
          </Card.Header>
          <Card.Meta>{`Created by: ${creator?.email}`}</Card.Meta>
          <Card.Description>{description}</Card.Description>
        </Card.Content>
        <Card.Content extra>
          <Statistic.Group size="mini" widths="3">
            <Statistic>
              <Statistic.Value>
                {annotationLabels?.edges ? annotationLabels.edges.length : 0}
              </Statistic.Value>
              <Statistic.Label>Labels</Statistic.Label>
            </Statistic>
            <MyPermissionsIndicator
              myPermissions={myPermissions}
              isPublic={isPublic}
            />
          </Statistic.Group>
        </Card.Content>
      </Card>
      <Popup
        basic
        context={contextRef}
        onClose={() => setContextMenuOpen(-1)}
        open={contextMenuOpen === id}
        hideOnScroll
      >
        <Menu secondary vertical>
          {context_menus.map((item) => (
            <Menu.Item
              key={item.key}
              icon={item.icon}
              content={item.content}
              onClick={() => {
                item.onClick();
                setContextMenuOpen(-1);
              }}
            />
          ))}
        </Menu>
      </Popup>
    </>
  );
};

export default AnnotationLabelItem;
