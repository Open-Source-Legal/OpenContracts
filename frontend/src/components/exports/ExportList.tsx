import { NetworkStatus } from "@apollo/client";
import { Table } from "@os-legal/ui";
import { ExportObject, PageInfo } from "../../types/graphql-api";
import { FetchMoreOnVisible } from "../widgets/infinite_scroll/FetchMoreOnVisible";
import { FetchMoreFooter } from "../widgets/infinite_scroll/FetchMoreFooter";
import { ExportItemRow } from "./ExportItemRow";
import { LoadingOverlay } from "../common/LoadingOverlay";

interface ExportListProps {
  items: ExportObject[] | undefined;
  pageInfo: PageInfo | undefined;
  loading: boolean;
  /** NetworkStatus from useQuery. When omitted, footer falls back to `loading && hasNextPage`. */
  networkStatus?: NetworkStatus;
  style?: Record<string, any>;
  fetchMore: (args?: any) => void | any;
  onDelete: (args?: any) => void | any;
}

const styles = {
  container: {
    flex: 1,
    width: "100%",
    overflowY: "auto" as const,
    backgroundColor: "#ffffff",
    borderRadius: "12px",
    boxShadow:
      "0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06)",
  },
};

export function ExportList({
  items,
  pageInfo,
  loading,
  networkStatus,
  style,
  fetchMore,
  onDelete,
}: ExportListProps) {
  const handleUpdate = () => {
    if (!loading && pageInfo?.hasNextPage) {
      fetchMore({
        variables: {
          limit: 20,
          cursor: pageInfo.endCursor,
        },
      });
    }
  };

  const export_rows = items
    ? items.map((item) => (
        <ExportItemRow key={item.id} onDelete={onDelete} item={item} />
      ))
    : [];

  const itemCount = items?.length ?? 0;

  return (
    <div
      style={{ ...styles.container, ...(style || {}), position: "relative" }}
    >
      {/* Initial-load only — refetches/deletes/fetchMore keep existing rows visible (callers needing a full block during deletes should layer their own overlay). */}
      <LoadingOverlay
        active={loading && itemCount === 0}
        content="Loading Exports..."
      />

      <Table variant="bordered">
        <Table.Head>
          <Table.Row>
            <Table.HeadCell>Description</Table.HeadCell>
            <Table.HeadCell align="center">Requested</Table.HeadCell>
            <Table.HeadCell align="center">Started</Table.HeadCell>
            <Table.HeadCell align="center">Completed</Table.HeadCell>
            <Table.HeadCell align="center">Actions</Table.HeadCell>
          </Table.Row>
        </Table.Head>
        <Table.Body>{export_rows}</Table.Body>
      </Table>

      <FetchMoreOnVisible fetchNextPage={handleUpdate} />
      <FetchMoreFooter
        visible={
          networkStatus === NetworkStatus.fetchMore ||
          (networkStatus === undefined &&
            loading &&
            Boolean(pageInfo?.hasNextPage))
        }
        message="Loading more exports…"
        data-testid="exports-fetch-more-spinner"
      />
    </div>
  );
}
