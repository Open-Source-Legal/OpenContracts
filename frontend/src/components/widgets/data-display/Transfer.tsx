import { FC, ReactNode } from "react";
import { HStack } from "@os-legal/ui";
import {
  DragDropContext,
  Droppable,
  Draggable,
  DraggableProvided,
  DraggableStateSnapshot,
  DroppableProvided,
  DroppableStateSnapshot,
  DropResult,
  ResponderProvided,
} from "@hello-pangea/dnd";
import { AnnotationSummary } from "../../annotator/AnnotationSummary";
import styled from "styled-components";

// Use string ID for annotation consistency with RelationModal
interface DataSourceItem {
  key: string; // Typically the annotation ID
  annotation: string; // Annotation ID string
}

// Props for DraggableList
interface DraggableListProps {
  id: string; // Droppable ID
  value_list: DataSourceItem[]; // Expects items with string annotation ID
  render: (item: DataSourceItem) => ReactNode;
}

const DropZone = styled.div<{ isDraggingOver: boolean }>`
  background: ${(props) => (props.isDraggingOver ? "lightblue" : "white")};
  flex: 1;
  min-height: 60px;
  padding: 8px;
`;

const DraggableItem = styled.div<{ isDragging: boolean }>`
  user-select: none;
  margin-bottom: 8px;
  background: ${(props) => (props.isDragging ? "lightgreen" : "white")};
  padding: 8px;
  border: 1px solid #ccc;
`;

const ColumnHeader = styled.div`
  padding: 0.78571429em 1em;
  background: rgba(0, 0, 0, 0.03);
  border: 1px solid rgba(34, 36, 38, 0.15);
  border-bottom: none;
  border-radius: 0.28571429rem 0.28571429rem 0 0;
  font-weight: 700;
  color: rgba(0, 0, 0, 0.87);
`;

const ColumnContent = styled.div`
  flex: 1;
  overflow-y: auto;
  padding: 0;
  background: #fff;
  border: 1px solid rgba(34, 36, 38, 0.15);
  border-top: none;
  border-radius: 0 0 0.28571429rem 0.28571429rem;
`;

export const DraggableList: FC<DraggableListProps> = ({
  id,
  value_list,
  render,
}) => {
  const grid = 8;

  return (
    <Droppable droppableId={id}>
      {(provided: DroppableProvided, snapshot: DroppableStateSnapshot) => (
        <DropZone
          ref={provided.innerRef}
          {...provided.droppableProps}
          isDraggingOver={snapshot.isDraggingOver}
        >
          {value_list.map((item, index) => (
            <Draggable key={item.key} draggableId={item.key} index={index}>
              {(
                providedDraggable: DraggableProvided,
                snapshotDraggable: DraggableStateSnapshot
              ) => (
                <DraggableItem
                  ref={providedDraggable.innerRef}
                  {...providedDraggable.draggableProps}
                  {...providedDraggable.dragHandleProps}
                  isDragging={snapshotDraggable.isDragging}
                  style={providedDraggable.draggableProps.style}
                >
                  {render(item)}
                </DraggableItem>
              )}
            </Draggable>
          ))}
          {provided.placeholder}
        </DropZone>
      )}
    </Droppable>
  );
};

/**
 * Props for Transfer component
 */
interface TransferProps {
  dataSource?: DataSourceItem[]; // Expects items with string annotation ID
  targetKeys: string[];
  onChange: (newTargetKeys: string[]) => void;
}

/**
 * A component to allow dragging items between two lists.
 * @param dataSource - Array of items {key: string, annotation: AnnotationType}
 * @param targetKeys - Array of keys present in the target list.
 * @param onChange - Callback function when items are moved, returns the new list of targetKeys.
 * @returns
 */
export const Transfer: FC<TransferProps> = ({
  dataSource = [], // Default to empty array if undefined
  targetKeys,
  onChange,
}) => {
  const source_list = dataSource.filter(
    (item: DataSourceItem) => !targetKeys.includes(item.key)
  );
  const target_list = dataSource.filter((item: DataSourceItem) =>
    targetKeys.includes(item.key)
  );

  const onDragEnd = (
    result: DropResult,
    provided?: ResponderProvided
  ): void => {
    const { source, destination, draggableId } = result;

    // Dropped outside the list
    if (!destination) {
      return;
    }

    // Dropped in the same place
    if (
      source.droppableId === destination.droppableId &&
      source.index === destination.index
    ) {
      return;
    }

    try {
      // Dropped into target from source col
      if (
        source.droppableId === "source_annotations" &&
        destination.droppableId === "target_annotations"
      ) {
        onChange([...targetKeys, draggableId]);
      }
      // Dropped into source column from target col
      else if (
        source.droppableId === "target_annotations" &&
        destination.droppableId === "source_annotations"
      ) {
        onChange(targetKeys.filter((key: string) => key !== draggableId));
      }
    } catch (error) {
      console.error("Error handling drag end:", error);
      // Handle potential errors during state update if necessary
    }
  };

  return (
    <DragDropContext onDragEnd={onDragEnd}>
      <HStack gap="lg" style={{ justifyContent: "center" }}>
        <div
          style={{
            flex: 1,
            height: "40vh",
            display: "flex",
            flexDirection: "column",
            paddingRight: "2vw",
            paddingLeft: "10px",
            borderRight: "1px solid rgba(34, 36, 38, 0.15)",
          }}
        >
          <ColumnHeader>Source Annotation(s):</ColumnHeader>
          <ColumnContent>
            <DraggableList
              id="source_annotations"
              value_list={source_list}
              render={(item: DataSourceItem) => (
                <AnnotationSummary annotationId={item.annotation} />
              )}
            />
          </ColumnContent>
        </div>
        <div
          style={{
            flex: 1,
            height: "40vh",
            display: "flex",
            flexDirection: "column",
            paddingLeft: "2vw",
            paddingRight: "10px",
          }}
        >
          <ColumnHeader>Target Annotation(s):</ColumnHeader>
          <ColumnContent>
            <DraggableList
              id="target_annotations"
              value_list={target_list}
              render={(item: DataSourceItem) => (
                <AnnotationSummary annotationId={item.annotation} />
              )}
            />
          </ColumnContent>
        </div>
      </HStack>
    </DragDropContext>
  );
};
