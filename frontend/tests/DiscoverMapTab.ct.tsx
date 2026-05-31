import { test, expect } from "@playwright/experimental-ct-react";
import { DiscoverMapTabTestWrapper } from "./DiscoverMapTabTestWrapper";
import { GET_GLOBAL_GEOGRAPHIC_ANNOTATIONS } from "../src/graphql/queries/geographicAnnotations";

const GEO_PINS = [
  {
    canonicalName: "Germany",
    labelType: "country",
    lat: 51.0,
    lng: 9.0,
    documentCount: 7,
    sampleDocumentIds: ["RG9jdW1lbnRUeXBlOjE="],
  },
];

// DiscoverMapPanel seeds its query with a whole-world bbox (null) at the map
// default zoom (2) and the full label-type set. Variables must match EXACTLY.
const geoMock = {
  request: {
    query: GET_GLOBAL_GEOGRAPHIC_ANNOTATIONS,
    variables: {
      bbox: null,
      zoom: 2,
      labelTypes: ["country", "state", "city"],
    },
  },
  result: {
    data: { globalGeographicAnnotations: GEO_PINS },
  },
};

test("Discover Map tab renders pins from globalGeographicAnnotations", async ({
  mount,
  page,
}) => {
  // cache-and-network may issue the same request more than once; provide the
  // mock twice so a refetch is also satisfied.
  await mount(<DiscoverMapTabTestWrapper mocks={[geoMock, geoMock]} />);

  // The map region renders inside the Map tab.
  await expect(
    page.getByRole("region", {
      name: "Map of geographic document annotations",
    })
  ).toBeVisible({ timeout: 20000 });

  // The mocked country pin renders as a marker (country band at default zoom).
  await expect(page.locator(".leaflet-marker-icon")).toHaveCount(1, {
    timeout: 20000,
  });
});
