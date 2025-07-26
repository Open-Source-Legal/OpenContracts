import { useEffect, useRef, useState } from "react";

import _ from "lodash";

import { useMutation, useQuery, useReactiveVar } from "@apollo/client";

import { LabelSetEditModal } from "../components/labelsets/LabelSetEditModal";
import { CRUDModal } from "../components/widgets/CRUD/CRUDModal";
import { LabelsetCards } from "../components/labelsets/LabelSetCards";
import {
  CreateLabelsetInputs,
  CreateLabelsetOutputs,
  CREATE_LABELSET,
} from "../graphql/mutations";
import {
  newLabelSetForm_Schema,
  newLabelSetForm_Ui_Schema,
} from "../components/forms/schemas";
import {
  authToken,
  labelsetSearchTerm,
  openedLabelset,
  selectedLabelsetIds,
  showNewLabelsetModal,
} from "../graphql/cache";
import { ActionDropdownItem } from "../components/types";
import { CardLayout } from "../components/layout/CardLayout";
import { CreateAndSearchBar } from "../components/layout/CreateAndSearchBar";
import { useLocation } from "react-router-dom";
import {
  GetLabelsetsWithLabelsInputs,
  GetLabelsetsWithLabelsOutputs,
  REQUEST_LABELSETS_WITH_ALL_LABELS,
} from "../graphql/queries";
import { LabelSetType } from "../types/graphql-api";
import { toast } from "react-toastify";

export const Labelsets = () => {
  const [createLabelset, { loading: create_labelset_loading }] = useMutation<
    CreateLabelsetOutputs,
    CreateLabelsetInputs
  >(CREATE_LABELSET);

  const debouncedSearch = useRef(
    _.debounce((searchTerm) => {
      labelsetSearchTerm(searchTerm);
    }, 1000)
  );

  const handleSearchChange = (value: string) => {
    setSearchCache(value);
    debouncedSearch.current(value);
  };

  const show_new_label_modal = useReactiveVar(showNewLabelsetModal);
  const selected_labelset_ids = useReactiveVar(selectedLabelsetIds);
  const labelset_search_term = useReactiveVar(labelsetSearchTerm);
  const opened_labelset = useReactiveVar(openedLabelset);
  const auth_token = useReactiveVar(authToken);

  const [searchCache, setSearchCache] = useState<string>(labelset_search_term);

  const { refetch, loading, error, data, fetchMore } = useQuery<
    GetLabelsetsWithLabelsOutputs,
    GetLabelsetsWithLabelsInputs
  >(REQUEST_LABELSETS_WITH_ALL_LABELS, {
    variables: {
      textSearch: labelset_search_term,
    },
    notifyOnNetworkStatusChange: true, // required to get loading signal on fetchMore
  });

  const items: LabelSetType[] = data?.labelsets?.edges
    ? data.labelsets.edges.map((edge) => edge.node)
    : [];

  /**
   * Load the labelsets
   */

  /**
   * Setup mutaton to create new labelset
   */
  const handleCreateLabelset = (values: CreateLabelsetInputs) => {
    createLabelset({ variables: { ...values } })
      .then((data) => {
        refetch();
        showNewLabelsetModal(false);
        toast.success("SUCCESS!\nSuccessfully created new labelset.");
      })
      .catch((err) => {
        toast.error("ERROR!\nFailed to created new labelset.");
        showNewLabelsetModal(false);
      });
  };

  /**
   * Build array of available actions
   */

  let button_actions: ActionDropdownItem[] = [];

  if (auth_token) {
    button_actions.push({
      key: "Labelset_action_0",
      title: "Create Label Set",
      icon: "plus",
      color: "blue",
      action_function: () => showNewLabelsetModal(true),
    });
    if (selected_labelset_ids.length > 0) {
      button_actions.push({
        key: `Labelset_action_${button_actions.length}`,
        title: "Delete Label Set(s)",
        icon: "remove circle",
        color: "blue",
        action_function: () => console.log("Delete label sets"),
      });
    }
  }

  return (
    <CardLayout
      Modals={
        <>
          {opened_labelset ? (
            <LabelSetEditModal
              open={opened_labelset !== null}
              toggleModal={() => openedLabelset(null)}
            />
          ) : (
            <></>
          )}

          {show_new_label_modal ? (
            <CRUDModal
              open={show_new_label_modal}
              mode="CREATE"
              oldInstance={{}}
              modelName="labelset"
              uiSchema={newLabelSetForm_Ui_Schema}
              dataSchema={newLabelSetForm_Schema}
              onSubmit={handleCreateLabelset}
              onClose={() => showNewLabelsetModal(false)}
              hasFile={true}
              fileField="icon"
              fileLabel="Labelset Icon"
              fileIsImage={true}
              acceptedFileTypes="image/*"
              loading={create_labelset_loading}
            />
          ) : (
            <></>
          )}
        </>
      }
      SearchBar={
        <CreateAndSearchBar
          onChange={(value: string) => handleSearchChange(value)}
          actions={button_actions}
          placeholder="Search for corpus..."
          value={searchCache}
        />
      }
    >
      <LabelsetCards
        pageInfo={data?.labelsets?.pageInfo ? data.labelsets.pageInfo : null}
        items={items}
        loading={loading}
        loading_message="Loading Labelsets..."
        fetchMore={fetchMore}
      />
    </CardLayout>
  );
};
