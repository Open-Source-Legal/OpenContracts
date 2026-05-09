/**
 * A modal for viewing and searching exports, with lazy loading and infinite scroll.
 */
import { useEffect, useRef, useState } from "react";
import {
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Button,
} from "@os-legal/ui";
import { X } from "lucide-react";
import _ from "lodash";
import { CreateAndSearchBar } from "../../layout/CreateAndSearchBar";
import { LoadingOverlay } from "../../common/LoadingOverlay";
import { ExportList } from "../../exports/ExportList";
import { LooseObject } from "../../types";
import { useLazyQuery, useMutation, useReactiveVar } from "@apollo/client";
import {
  GetExportsInputs, // Placeholder - do not guess shape
  GetExportsOutputs, // Placeholder - do not guess shape
  GET_EXPORTS,
} from "../../../graphql/queries";
import {
  DELETE_EXPORT,
  DeleteExportInputs,
  DeleteExportOutputs,
} from "../../../graphql/mutations";
import { ExportObject } from "../../../types/graphql-api";
import { exportSearchTerm, showExportModal } from "../../../graphql/cache";
import { toast } from "react-toastify";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";

export interface ExportModalProps {
  /**
   * Whether the modal is currently visible.
   */
  visible: boolean;
  /**
   * Function to toggle the modal visibility.
   */
  toggleModal: (args?: any) => void | any;
}

export function ExportModal({ visible, toggleModal }: ExportModalProps) {
  const export_search_term = useReactiveVar(exportSearchTerm);
  const show_export_modal = useReactiveVar(showExportModal);

  const [exportSearchCache, setExportSearchCache] =
    useState<string>(export_search_term);

  // Sorting props (placeholders only; implement logic in your queries if needed)
  const [orderByCreated, setOrderByCreated] = useState<
    "created" | "-created" | undefined
  >();
  const [orderByFinished, setOrderByFinished] = useState<
    "finished" | "-finished" | undefined
  >();
  const [orderByStarted, setOrderByStarted] = useState<
    "started" | "-started" | undefined
  >();

  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  // Debounced Search Handler
  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  const debouncedExportSearch = useRef(
    _.debounce((searchTerm: string) => {
      exportSearchTerm(searchTerm);
    }, 1000)
  );

  const handleCorpusSearchChange = (value: string) => {
    setExportSearchCache(value);
    debouncedExportSearch.current(value);
  };

  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  // Setup query variables based on user inputs
  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  const exports_variables: LooseObject = {};
  if (export_search_term) {
    exports_variables["name_Contains"] = export_search_term;
  }
  if (orderByCreated) {
    exports_variables["orderByCreated"] = orderByCreated;
  }
  if (orderByStarted) {
    exports_variables["orderByStarted"] = orderByStarted;
  }
  if (orderByFinished) {
    exports_variables["orderByFinished"] = orderByFinished;
  }

  const [
    fetchExports,
    {
      refetch: refetchExports,
      loading: exports_loading,
      networkStatus: exports_network_status,
      error: exports_error,
      data: exports_response,
      fetchMore: fetchMoreExports,
    },
  ] = useLazyQuery<GetExportsOutputs, GetExportsInputs>(GET_EXPORTS, {
    variables: exports_variables,
    fetchPolicy: "network-only",
    notifyOnNetworkStatusChange: true, // Mirroring usage in Extracts
  });

  const [deleteExport, { loading: deleting }] = useMutation<
    DeleteExportOutputs,
    DeleteExportInputs
  >(DELETE_EXPORT, {
    onCompleted: (data) => {
      if (data.deleteExport.ok) {
        toast.success("Export deleted successfully");
        refetchExports && refetchExports();
      } else {
        toast.error(`Failed to delete export: ${data.deleteExport.message}`);
      }
    },
    onError: (error) => {
      toast.error(`Error deleting export: ${error.message}`);
    },
  });

  if (exports_error) {
    toast.error("ERROR!\nUnable to get export list.");
  }

  const handleDelete = (id: string) => {
    if (window.confirm("Are you sure you want to delete this export?")) {
      deleteExport({ variables: { id } });
    }
  };

  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  // Effects to refetch on user input changes
  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  useEffect(() => {
    fetchExports();
  }, []);

  // If visibility is toggled and modal is now visible, load the exports
  useEffect(() => {
    if (show_export_modal) {
      fetchExports();
    }
  }, [show_export_modal]);

  // Refetch on each filter / search param change
  useEffect(() => {
    refetchExports && refetchExports();
  }, [export_search_term, orderByCreated, orderByStarted, orderByFinished]);

  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  // Shape GraphQL Data
  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  const export_data = exports_response?.userexports?.edges ?? [];
  const export_items = export_data
    .map((edge) => (edge ? edge.node : undefined))
    .filter((item): item is ExportObject => !!item);

  return (
    <Modal open={visible} onClose={() => toggleModal()} size="lg">
      <ModalHeader title="Corpus Exports" onClose={() => toggleModal()} />
      <ModalBody style={{ position: "relative" }}>
        <div
          style={{
            padding: "0.75rem",
            background: OS_LEGAL_COLORS.warningSurface,
            border: `1px solid ${OS_LEGAL_COLORS.warningBorder}`,
            borderRadius: "8px",
            fontSize: "0.85rem",
            color: OS_LEGAL_COLORS.warningText,
            marginBottom: "1rem",
            textAlign: "center",
          }}
        >
          WARNING - If you have a free account, your exports will be deleted
          within 24 hours of completion.
        </div>
        <LoadingOverlay
          active={exports_loading}
          inverted
          content="Loading..."
        />
        <div
          style={{
            display: "flex",
            justifyContent: "center",
            flexDirection: "row",
            width: "100%",
            marginBottom: "1rem",
          }}
        >
          <CreateAndSearchBar
            onChange={(value: string) => handleCorpusSearchChange(value)}
            actions={[]}
            placeholder="Search for export by name..."
            value={exportSearchCache}
            style={{ flex: 1 }}
          />
        </div>
        <ExportList
          items={export_items}
          pageInfo={exports_response?.userexports?.pageInfo}
          loading={exports_loading || deleting}
          networkStatus={exports_network_status}
          fetchMore={fetchMoreExports}
          onDelete={handleDelete}
        />
      </ModalBody>
      <ModalFooter>
        <Button
          variant="secondary"
          onClick={() => toggleModal()}
          leftIcon={<X size={16} />}
        >
          Close
        </Button>
      </ModalFooter>
    </Modal>
  );
}
