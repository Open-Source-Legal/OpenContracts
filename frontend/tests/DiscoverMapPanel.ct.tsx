import { test, expect } from "./utils/coverage";
import { DiscoverMapPanelTestWrapper } from "./DiscoverMapPanelTestWrapper";
import { GET_GLOBAL_GEOGRAPHIC_ANNOTATIONS } from "../src/graphql/queries/geographicAnnotations";

const GEO_PINS = [
  {
    // __typename is required in the mock RESULT so Apollo's normalised cache
    // materialises the pin (MockedProvider needs it even with
    // addTypename={false} on the request side).
    __typename: "GeographicAnnotationPinType",
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
// cache-and-network can issue the request more than once, so the mock is
// provided twice.
const geoMock = {
  request: {
    query: GET_GLOBAL_GEOGRAPHIC_ANNOTATIONS,
    variables: {
      bbox: null,
      zoom: 2,
      labelTypes: ["country", "state", "city"],
    },
  },
  result: { data: { globalGeographicAnnotations: GEO_PINS } },
};

test("DiscoverMapPanel renders pins from globalGeographicAnnotations", async ({
  mount,
  page,
}) => {
  await mount(<DiscoverMapPanelTestWrapper mocks={[geoMock, geoMock]} />);

  // The reusable map region renders inside the panel.
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
