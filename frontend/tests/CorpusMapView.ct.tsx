import { test, expect } from "./utils/coverage";
import { CorpusMapViewTestWrapper } from "./CorpusMapViewTestWrapper";
import { CORPUS_MAP_TEST_CORPUS_ID } from "./CorpusMapViewTestWrapper";
import { docScreenshot } from "./utils/docScreenshot";
import {
  corpusGeoInitialVariables,
  GET_GEOGRAPHIC_ANNOTATIONS_FOR_CORPUS,
} from "../src/graphql/queries/geographicAnnotations";

// __typename is required in the mock RESULT so MockedProvider materialises the
// pins (matching the DiscoverMapPanel mocks even with addTypename={false}).
const FRANCE_PIN = {
  __typename: "GeographicAnnotationPinType",
  canonicalName: "France",
  labelType: "country",
  lat: 46.6,
  lng: 2.2,
  documentCount: 12,
  sampleDocumentIds: ["RG9jdW1lbnRUeXBlOjE=", "RG9jdW1lbnRUeXBlOjI="],
};

const PARIS_PIN = {
  __typename: "GeographicAnnotationPinType",
  canonicalName: "Paris",
  labelType: "city",
  lat: 48.8566,
  lng: 2.3522,
  documentCount: 4,
  sampleDocumentIds: ["RG9jdW1lbnRUeXBlOjM="],
};

// CorpusMapView fetches the whole corpus once via corpusGeoInitialVariables
// (no bbox, all label types). Variables must match EXACTLY; cache-and-network
// can issue the request more than once, so each mock is provided twice.
const geoMock = (pins: Array<Record<string, unknown>>) => ({
  request: {
    query: GET_GEOGRAPHIC_ANNOTATIONS_FOR_CORPUS,
    variables: corpusGeoInitialVariables(CORPUS_MAP_TEST_CORPUS_ID),
  },
  result: { data: { geographicAnnotationsForCorpus: pins } },
});

// Error variant of the same request. With no pins ever materialised, the query
// failure surfaces the `role="alert"` placeholder rather than a stale map.
const geoErrorMock = () => ({
  request: {
    query: GET_GEOGRAPHIC_ANNOTATIONS_FOR_CORPUS,
    variables: corpusGeoInitialVariables(CORPUS_MAP_TEST_CORPUS_ID),
  },
  error: new Error("Network failure"),
});

test("CorpusMapView renders corpus pins and reveals corpus documents on click", async ({
  mount,
  page,
}) => {
  const mocks = [
    geoMock([FRANCE_PIN, PARIS_PIN]),
    geoMock([FRANCE_PIN, PARIS_PIN]),
  ];
  const component = await mount(<CorpusMapViewTestWrapper mocks={mocks} />);

  // The header badges the place count for the whole corpus (both bands).
  await expect(page.getByTestId("corpus-map-count")).toContainText("2 places", {
    timeout: 20000,
  });

  // The reusable map region renders and auto-fits to the coarsest band
  // (country), so the France marker is shown at the framed zoom.
  await expect(
    page.getByRole("region", {
      name: "Map of geographic document annotations",
    })
  ).toBeVisible({ timeout: 20000 });
  const markers = page.locator(".leaflet-marker-icon");
  await expect(markers).toHaveCount(1, { timeout: 20000 });
  await expect(markers.first()).toHaveAttribute("alt", /France/);

  // Clicking a pin reveals that place's corpus-scoped documents in the side
  // panel (the query is corpus-scoped + permission-filtered server-side, so a
  // pin can only ever list documents from this corpus the user may see).
  await markers.first().click();
  await expect(component).toContainText("France");
  await expect(component).toContainText("12 documents");
  await expect(
    component.getByRole("button", { name: /Open document/ })
  ).toHaveCount(2);

  await docScreenshot(page, "corpus--map-view--with-pins");
});

test("CorpusMapView shows the empty state pointing at the Location Tagger agent", async ({
  mount,
  page,
}) => {
  const mocks = [geoMock([]), geoMock([])];
  await mount(<CorpusMapViewTestWrapper mocks={mocks} />);

  const empty = page.getByTestId("corpus-map-empty");
  await expect(empty).toBeVisible({ timeout: 20000 });
  await expect(empty).toContainText("No places on the map yet");
  await expect(empty).toContainText("Location Tagger");

  // The map region is not rendered when there are no pins.
  await expect(
    page.getByRole("region", {
      name: "Map of geographic document annotations",
    })
  ).toHaveCount(0);

  await docScreenshot(page, "corpus--map-view--empty");
});

test("CorpusMapView shows the error placeholder when the geo query fails", async ({
  mount,
  page,
}) => {
  // cache-and-network can issue the request more than once; fail both.
  const mocks = [geoErrorMock(), geoErrorMock()];
  await mount(<CorpusMapViewTestWrapper mocks={mocks} />);

  const errorPlaceholder = page.getByTestId("corpus-map-error");
  await expect(errorPlaceholder).toBeVisible({ timeout: 20000 });
  await expect(errorPlaceholder).toHaveAttribute("role", "alert");
  await expect(errorPlaceholder).toContainText("Could not load the map");

  // No map and no stale pins are shown when the load fails with nothing cached.
  await expect(
    page.getByRole("region", {
      name: "Map of geographic document annotations",
    })
  ).toHaveCount(0);

  await docScreenshot(page, "corpus--map-view--load-error");
});

test("CorpusMapView deep-link ?pin=Paris opens zoomed to Paris with the side panel", async ({
  mount,
  page,
}) => {
  const mocks = [
    geoMock([FRANCE_PIN, PARIS_PIN]),
    geoMock([FRANCE_PIN, PARIS_PIN]),
  ];
  const component = await mount(
    <CorpusMapViewTestWrapper mocks={mocks} focusPin="Paris" />
  );

  // The deep-link focus flies to the city band and opens the side panel for
  // Paris with its corpus-scoped document — no click required.
  await expect(component).toContainText("Paris", { timeout: 20000 });
  await expect(component).toContainText("4 documents");
  await expect(
    component.getByRole("button", { name: /Open document/ })
  ).toHaveCount(1);

  // Zoomed to the city band, only the Paris (city) marker is shown.
  const markers = page.locator(".leaflet-marker-icon");
  await expect(markers).toHaveCount(1, { timeout: 20000 });
  await expect(markers.first()).toHaveAttribute("alt", /Paris/);
});
