import React from "react";
import {
  test,
  expect,
  type MountResult,
} from "@playwright/experimental-ct-react";
import { docScreenshot } from "./utils/docScreenshot";
import { FilterToLabelSelector } from "../src/components/widgets/model-filters/FilterToLabelSelector";
import { LabelType } from "../src/types/graphql-api";
import { MockedProvider } from "@apollo/client/testing";
import { GET_ANNOTATION_LABELS } from "../src/graphql/queries";

// Simple mock for the query
const mocks = [
  {
    request: {
      query: GET_ANNOTATION_LABELS,
      variables: { labelType: LabelType.TokenLabel },
    },
    result: {
      data: {
        annotationLabels: {
          edges: [
            {
              node: {
                id: "label-1",
                text: "Test Label",
                description: "Test Description",
                icon: null,
                labelType: LabelType.TokenLabel,
              },
            },
          ],
        },
      },
    },
  },
];

test("FilterToLabelSelector renders correctly", async ({ mount, page }) => {
  // Mount the component with mocked Apollo provider
  const component = await mount(
    <MockedProvider mocks={mocks} addTypename={false}>
      <FilterToLabelSelector label_type={LabelType.TokenLabel} />
    </MockedProvider>
  );

  // Check for the basic structure - the label text should be visible
  await expect(component.locator("text=Filter by Label")).toBeVisible({
    timeout: 5000,
  });

  // Check for the dropdown
  await expect(
    component.locator("text=Select a label to filter...")
  ).toBeVisible({
    timeout: 5000,
  });

  await docScreenshot(page, "filters--label-selector--default");
});
