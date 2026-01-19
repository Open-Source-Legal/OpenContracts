import { Table, Button } from "semantic-ui-react";
import { ExportObject } from "../../types/graphql-api";
import { DateTimeWidget } from "../widgets/data-display/DateTimeWidget";
import { Loader2, Trash2, Download } from "lucide-react";

interface ExportItemRowProps {
  style?: Record<string, any>;
  item: ExportObject;
  key: string;
  onDelete: (args?: any) => void | any;
}

export function ExportItemRow({ onDelete, item, key }: ExportItemRowProps) {
  let requestedTime = "";
  let requestedDate = "N/A";
  if (item.created) {
    var dCreate = new Date(item.created);
    requestedTime = dCreate.toLocaleTimeString();
    requestedDate = dCreate.toLocaleDateString();
  }

  let startedTime = "";
  let startedDate = "N/A";
  if (item.started) {
    var dStart = new Date(item.started);
    startedTime = dStart.toLocaleTimeString();
    startedDate = dStart.toLocaleDateString();
  }

  let completedTime = "";
  let completedDate = "N/A";
  if (item.finished) {
    var dCompleted = new Date(item.finished);
    completedTime = dCompleted.toLocaleTimeString();
    completedDate = dCompleted.toLocaleDateString();
  }

  return (
    <Table.Row key={key}>
      <Table.Cell>{item.name}</Table.Cell>
      <Table.Cell>
        <DateTimeWidget timeString={requestedTime} dateString={requestedDate} />
      </Table.Cell>
      <Table.Cell textAlign="center">
        {!item.started ? (
          <Loader2 size={20} className="animate-spin" />
        ) : (
          <DateTimeWidget timeString={startedTime} dateString={startedDate} />
        )}
      </Table.Cell>
      <Table.Cell textAlign="center">
        {!item.finished || !item.started ? (
          <Loader2 size={20} className="animate-spin" />
        ) : (
          <DateTimeWidget
            timeString={completedTime}
            dateString={completedDate}
          />
        )}
      </Table.Cell>
      <Table.Cell textAlign="center">
        <div>
          <Button
            circular
            size="mini"
            color="red"
            onClick={() => onDelete(item.id)}
          >
            <Trash2 size={12} />
          </Button>
          {item.finished ? (
            <Button
              circular
              size="mini"
              color="blue"
              onClick={() => {
                window.location.href = item.file;
              }}
            >
              <Download size={12} />
            </Button>
          ) : (
            <></>
          )}
        </div>
      </Table.Cell>
    </Table.Row>
  );
}
