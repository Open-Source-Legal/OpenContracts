import { test, expect } from "./utils/coverage";
import { CorpusMapToggleTestWrapper } from "./CorpusMapToggleTestWrapper";
import { CORPUS_MAP_TOGGLE_TEST_CORPUS_ID } from "./CorpusMapToggleTestWrapper";
import { docScreenshot } from "./utils/docScreenshot";
import {
  corpusGeoInitialVariables,
  GET_GEOGRAPHIC_ANNOTATIONS_FOR_CORPUS,
} from "../src/graphql/queries/geographicAnnotations";

const PIN = (canonicalName: string, labelType: string) => ({
  __typename: "GeographicAnnotationPinType",
  canonicalName,
  labelType,
  lat: 46.6,
  lng: 2.2,
  documentCount: 3,
  sampleDocumentIds: ["RG9jdW1lbnRUeXBlOjE="],
});

// The toggle reuses corpusGeoInitialVariables (the same shared count query as
// CorpusMapView). Variables must match EXACTLY.
const geoMock = (pins: Array<Record<string, unknown>>) => ({
  request: {
    query: GET_GEOGRAPHIC_ANNOTATIONS_FOR_CORPUS,
    variables: corpusGeoInitialVariables(CORPUS_MAP_TOGGLE_TEST_CORPUS_ID),
  },
  result: { data: { geographicAnnotationsForCorpus: pins } },
});

test("CorpusMapToggle badges the place count when the corpus has places", async ({
  mount,
  page,
}) => {
  const mocks = [geoMock([PIN("France", "country"), PIN("Paris", "city")])];
  await mount(<CorpusMapToggleTestWrapper mocks={mocks} />);

  const toggle = page.getByTestId("corpus-map-toggle");
  await expect(toggle).toBeVisible({ timeout: 20000 });
  // Once loaded with places the badge shows the count and labels itself open-able.
  await expect(toggle).toContainText("2 places", { timeout: 20000 });
  await expect(toggle).toHaveAttribute("aria-label", /Open map — 2 places/);

  await docScreenshot(page, "corpus--map-toggle--with-places");
});

test("CorpusMapToggle stays muted but clickable when the corpus has no places", async ({
  mount,
  page,
}) => {
  const mocks = [geoMock([])];
  await mount(<CorpusMapToggleTestWrapper mocks={mocks} />);

  const toggle = page.getByTestId("corpus-map-toggle");
  await expect(toggle).toBeVisible({ timeout: 20000 });
  // Empty corpora resolve to "0 places" and the no-places aria-label, but the
  // button is still enabled so users can reach the empty-state guidance.
  await expect(toggle).toContainText("0 places", { timeout: 20000 });
  await expect(toggle).toHaveAttribute(
    "aria-label",
    "Open map — no places tagged yet"
  );
  await expect(toggle).toBeEnabled();

  await docScreenshot(page, "corpus--map-toggle--no-places");
});

test("CorpusMapToggle omits the count while the query is still loading", async ({
  mount,
  page,
}) => {
  // No matching mock resolves immediately, so the query stays in flight: the
  // badge renders its "Map" label without the "· N places" count suffix.
  await mount(<CorpusMapToggleTestWrapper mocks={[]} />);

  const toggle = page.getByTestId("corpus-map-toggle");
  await expect(toggle).toBeVisible({ timeout: 20000 });
  await expect(toggle).toContainText("Map");
  await expect(toggle).not.toContainText("places");
});
