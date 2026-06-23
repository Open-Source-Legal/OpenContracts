/**
 * Reusable AuthorityKeyEquivalence editing primitives — the inline create form
 * and the per-row edit/delete table — shared by the Mappings tab and the
 * single-authority detail's Relationships section. Extracted (verbatim in
 * behaviour) from the standalone AuthorityMappings panel so both surfaces drive
 * the SAME superuser-gated create/update/delete mutations and the same
 * manual-only edit rule (loader-owned baseline/popular_name/uslm rows stay
 * read-only). Mutation wiring stays with the caller; these are presentational +
 * local-edit-state only.
 */
import React, { useState } from "react";
import { Button, Table } from "@os-legal/ui";
import { Check, Pencil, Plus, Trash2, X } from "lucide-react";

import { formatDateTime } from "../../../../utils/formatters";
import { ScrollableTableWrapper } from "../../../layout/SharedSegments";
import {
  Badge,
  CreateField,
  CreateForm,
  FieldLabel,
  IconButton,
  KeyCell,
  KeyInput,
  Muted,
  RowActions,
  TextInput,
} from "./consoleChrome";
import { sourceLabel, sourceTone } from "./tones";

export interface KeyEquivalenceRow {
  id: string;
  fromKey: string;
  toKey: string;
  source: string;
  note?: string | null;
  editable: boolean;
  createdByUsername?: string | null;
  modified?: string | null;
}

const EQUIV_TABLE_MIN_WIDTH_PX = 860;

/* ---- create form --------------------------------------------------------- */

interface CreateFormProps {
  onCreate: (vals: { fromKey: string; toKey: string; note: string }) => void;
  creating: boolean;
  /** Prefill + lock guidance when creating from a specific authority detail. */
  fromPlaceholder?: string;
  toPlaceholder?: string;
  testIdPrefix?: string;
}

export const KeyEquivalenceCreateForm: React.FC<CreateFormProps> = ({
  onCreate,
  creating,
  fromPlaceholder = "e.g. securities-act:5",
  toPlaceholder = "e.g. usc-15:77e",
  testIdPrefix = "mappings",
}) => {
  const [fromKey, setFromKey] = useState("");
  const [toKey, setToKey] = useState("");
  const [note, setNote] = useState("");

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!fromKey.trim() || !toKey.trim()) return;
    onCreate({
      fromKey: fromKey.trim(),
      toKey: toKey.trim(),
      note: note.trim(),
    });
    setFromKey("");
    setToKey("");
    setNote("");
  };

  return (
    <CreateForm onSubmit={submit} data-testid={`${testIdPrefix}-create-form`}>
      <CreateField>
        <FieldLabel htmlFor={`${testIdPrefix}-new-from`}>From key</FieldLabel>
        <KeyInput
          id={`${testIdPrefix}-new-from`}
          value={fromKey}
          onChange={(e) => setFromKey(e.target.value)}
          placeholder={fromPlaceholder}
          data-testid={`${testIdPrefix}-new-from`}
        />
      </CreateField>
      <CreateField>
        <FieldLabel htmlFor={`${testIdPrefix}-new-to`}>
          To key (canonical)
        </FieldLabel>
        <KeyInput
          id={`${testIdPrefix}-new-to`}
          value={toKey}
          onChange={(e) => setToKey(e.target.value)}
          placeholder={toPlaceholder}
          data-testid={`${testIdPrefix}-new-to`}
        />
      </CreateField>
      <CreateField style={{ flex: "2 1 220px" }}>
        <FieldLabel htmlFor={`${testIdPrefix}-new-note`}>
          Note (optional)
        </FieldLabel>
        <TextInput
          id={`${testIdPrefix}-new-note`}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Why this bridge exists"
          data-testid={`${testIdPrefix}-new-note`}
        />
      </CreateField>
      <Button
        variant="primary"
        type="submit"
        disabled={creating || !fromKey.trim() || !toKey.trim()}
        data-testid={`${testIdPrefix}-create-submit`}
      >
        <Plus size={14} style={{ marginRight: 6 }} />
        {creating ? "Adding…" : "Add mapping"}
      </Button>
    </CreateForm>
  );
};

/* ---- editable table ------------------------------------------------------ */

interface TableProps {
  rows: KeyEquivalenceRow[];
  onUpdate: (
    id: string,
    vals: { fromKey: string; toKey: string; note: string }
  ) => void;
  onDelete: (row: KeyEquivalenceRow) => void;
  busy: boolean;
  /** Show the Created-by + Modified columns (the Mappings tab does; detail omits). */
  showProvenance?: boolean;
  testIdPrefix?: string;
}

export const KeyEquivalenceTable: React.FC<TableProps> = ({
  rows,
  onUpdate,
  onDelete,
  busy,
  showProvenance = true,
  testIdPrefix = "mappings",
}) => {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editFrom, setEditFrom] = useState("");
  const [editTo, setEditTo] = useState("");
  const [editNote, setEditNote] = useState("");

  const startEdit = (r: KeyEquivalenceRow) => {
    setEditingId(r.id);
    setEditFrom(r.fromKey);
    setEditTo(r.toKey);
    setEditNote(r.note ?? "");
  };
  const cancelEdit = () => setEditingId(null);
  const saveEdit = (id: string) => {
    if (!editFrom.trim() || !editTo.trim()) return;
    onUpdate(id, {
      fromKey: editFrom.trim(),
      toKey: editTo.trim(),
      note: editNote.trim(),
    });
    setEditingId(null);
  };

  return (
    <ScrollableTableWrapper
      $minWidth={`${EQUIV_TABLE_MIN_WIDTH_PX}px`}
      data-testid={`${testIdPrefix}-table-scroll`}
    >
      <Table variant="minimal">
        <Table.Head>
          <Table.Row>
            <Table.HeadCell>From key</Table.HeadCell>
            <Table.HeadCell>To key</Table.HeadCell>
            <Table.HeadCell>Source</Table.HeadCell>
            <Table.HeadCell>Note</Table.HeadCell>
            {showProvenance && <Table.HeadCell>Created by</Table.HeadCell>}
            {showProvenance && <Table.HeadCell>Modified</Table.HeadCell>}
            <Table.HeadCell>Actions</Table.HeadCell>
          </Table.Row>
        </Table.Head>
        <Table.Body>
          {rows.map((r) => {
            const isEditing = editingId === r.id;
            return (
              <Table.Row key={r.id} data-testid={`${testIdPrefix}-row`}>
                <Table.Cell>
                  {isEditing ? (
                    <KeyInput
                      value={editFrom}
                      onChange={(e) => setEditFrom(e.target.value)}
                      aria-label="Edit from key"
                      data-testid={`${testIdPrefix}-edit-from`}
                    />
                  ) : (
                    <KeyCell>{r.fromKey}</KeyCell>
                  )}
                </Table.Cell>
                <Table.Cell>
                  {isEditing ? (
                    <KeyInput
                      value={editTo}
                      onChange={(e) => setEditTo(e.target.value)}
                      aria-label="Edit to key"
                      data-testid={`${testIdPrefix}-edit-to`}
                    />
                  ) : (
                    <KeyCell>{r.toKey}</KeyCell>
                  )}
                </Table.Cell>
                <Table.Cell>
                  <Badge $tone={sourceTone(r.source)}>
                    {sourceLabel(r.source)}
                  </Badge>
                </Table.Cell>
                <Table.Cell>
                  {isEditing ? (
                    <TextInput
                      value={editNote}
                      onChange={(e) => setEditNote(e.target.value)}
                      aria-label="Edit note"
                      data-testid={`${testIdPrefix}-edit-note`}
                    />
                  ) : r.note ? (
                    r.note
                  ) : (
                    <Muted>—</Muted>
                  )}
                </Table.Cell>
                {showProvenance && (
                  <Table.Cell>
                    {r.createdByUsername ?? <Muted>—</Muted>}
                  </Table.Cell>
                )}
                {showProvenance && (
                  <Table.Cell>
                    {r.modified ? formatDateTime(r.modified) : <Muted>—</Muted>}
                  </Table.Cell>
                )}
                <Table.Cell>
                  {!r.editable ? (
                    <Muted title="Bundled mappings are read-only">
                      read-only
                    </Muted>
                  ) : isEditing ? (
                    <RowActions>
                      <IconButton
                        type="button"
                        onClick={() => saveEdit(r.id)}
                        disabled={busy || !editFrom.trim() || !editTo.trim()}
                        aria-label="Save mapping"
                        title="Save"
                        data-testid={`${testIdPrefix}-save`}
                      >
                        <Check />
                      </IconButton>
                      <IconButton
                        type="button"
                        onClick={cancelEdit}
                        aria-label="Cancel edit"
                        title="Cancel"
                        data-testid={`${testIdPrefix}-cancel`}
                      >
                        <X />
                      </IconButton>
                    </RowActions>
                  ) : (
                    <RowActions>
                      <IconButton
                        type="button"
                        onClick={() => startEdit(r)}
                        disabled={busy}
                        aria-label={`Edit ${r.fromKey}`}
                        title="Edit"
                        data-testid={`${testIdPrefix}-edit`}
                      >
                        <Pencil />
                      </IconButton>
                      <IconButton
                        type="button"
                        $danger
                        onClick={() => onDelete(r)}
                        disabled={busy}
                        aria-label={`Delete ${r.fromKey}`}
                        title="Delete"
                        data-testid={`${testIdPrefix}-delete`}
                      >
                        <Trash2 />
                      </IconButton>
                    </RowActions>
                  )}
                </Table.Cell>
              </Table.Row>
            );
          })}
        </Table.Body>
      </Table>
    </ScrollableTableWrapper>
  );
};
