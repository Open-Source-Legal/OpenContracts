/**
 * GraphQL mock builders for `FieldsetModal` Playwright CT tests.
 *
 * Split into a separate module from `FieldsetModalTestWrapper.tsx` because
 * Playwright CT's babel plugin requires that wrapper files only export
 * mountable components.
 */
import { MockedResponse } from "@apollo/client/testing";
import { REQUEST_GET_FIELDSET } from "../src/graphql/queries";
import { FieldsetType, ColumnType } from "../src/types/graphql-api";
import { DEFAULT_EXTRACT_TASK_NAME } from "../src/components/widgets/modals/CreateColumnModal";

export { DEFAULT_EXTRACT_TASK_NAME };

export const buildGetFieldsetMock = (
  id: string,
  payload: Partial<FieldsetType> & {
    fullColumnList?: ColumnType[];
  }
): MockedResponse => ({
  request: { query: REQUEST_GET_FIELDSET, variables: { id } },
  result: {
    data: {
      fieldset: {
        __typename: "FieldsetType",
        id,
        name: payload.name ?? "Test Fieldset",
        description: payload.description ?? "",
        inUse: payload.inUse ?? false,
        creator: { __typename: "UserType", id: "u1", username: "alice" },
        fullColumnList: (payload.fullColumnList ?? []).map((col) => ({
          __typename: "ColumnType",
          mustContainText: null,
          extractIsList: false,
          instructions: "",
          matchText: "",
          limitToLabel: "",
          query: "",
          taskName: DEFAULT_EXTRACT_TASK_NAME,
          outputType: "str",
          ...col,
        })),
      },
    },
  },
});
