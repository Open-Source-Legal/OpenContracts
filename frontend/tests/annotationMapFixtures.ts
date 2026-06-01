import type { GeographicAnnotationPin } from "../src/components/maps/types";

/** Explicit DOM height so Leaflet paints tiles/markers in the test viewport. */
export const MAP_TEST_HEIGHT = "500px";

export const COUNTRY_PIN: GeographicAnnotationPin = {
  canonicalName: "France",
  labelType: "country",
  lat: 46.6,
  lng: 2.2,
  documentCount: 12,
  sampleDocumentIds: ["RG9jdW1lbnRUeXBlOjE=", "RG9jdW1lbnRUeXBlOjI="],
};

export const CITY_PIN: GeographicAnnotationPin = {
  canonicalName: "Paris",
  labelType: "city",
  lat: 48.8566,
  lng: 2.3522,
  documentCount: 4,
  sampleDocumentIds: ["RG9jdW1lbnRUeXBlOjM="],
};
