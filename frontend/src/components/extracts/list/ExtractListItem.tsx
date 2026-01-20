import { Table } from "semantic-ui-react";
import { IconButton } from "@os-legal/ui";
import { Settings, Eye, Trash2 } from "lucide-react";
import { ExtractType } from "../../../types/graphql-api";
import { DateTimeWidget } from "../../widgets/data-display/DateTimeWidget";

interface ExtractItemRowProps {
  style?: Record<string, any>;
  item: ExtractType;
  onDelete: (args?: any) => void | any;
  onSelect?: (item: ExtractType) => void;
}

export function ExtractItemRow({
  onSelect,
  onDelete,
  item,
}: ExtractItemRowProps) {
  let createdTime = "";
  let createdDate = "N/A";
  if (item.created) {
    var dCreate = new Date(item.created);
    createdTime = dCreate.toLocaleTimeString();
    createdDate = dCreate.toLocaleDateString();
  }

  let startedTime = "";
  let startedDate = "N/A";
  if (item.started) {
    var dStart = new Date(item.started);
    startedTime = dStart.toLocaleTimeString();
    startedDate = dStart.toLocaleDateString();
  }

  let finishedTime = "";
  let finishedDate = "N/A";
  if (item.finished) {
    var dCompleted = new Date(item.finished);
    finishedTime = dCompleted.toLocaleTimeString();
    finishedDate = dCompleted.toLocaleDateString();
  }

  return (
    <Table.Row key={item.id}>
      <Table.Cell>{item.name}</Table.Cell>
      <Table.Cell>
        <DateTimeWidget timeString={createdTime} dateString={createdDate} />
      </Table.Cell>
      <Table.Cell textAlign="center">
        {!item.started ? (
          <Settings
            size={20}
            style={{ animation: "spin 2s linear infinite" }}
          />
        ) : (
          <DateTimeWidget timeString={startedTime} dateString={startedDate} />
        )}
      </Table.Cell>
      <Table.Cell textAlign="center">
        {!item.finished || !item.started ? (
          <Settings
            size={20}
            style={{ animation: "spin 2s linear infinite" }}
          />
        ) : (
          <DateTimeWidget timeString={finishedTime} dateString={finishedDate} />
        )}
      </Table.Cell>
      <Table.Cell textAlign="center">
        <div>
          <IconButton
            variant="secondary"
            size="sm"
            aria-label="View extract"
            {...(onSelect ? { onClick: () => onSelect(item) } : {})}
          >
            <Eye size={12} />
          </IconButton>
          <IconButton
            variant="danger"
            size="sm"
            aria-label="Delete extract"
            onClick={onDelete}
          >
            <Trash2 size={12} />
          </IconButton>
        </div>
      </Table.Cell>
    </Table.Row>
  );
}
