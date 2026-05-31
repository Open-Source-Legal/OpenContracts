import { test, expect } from "@playwright/experimental-ct-react";
import { AnnotationMapTestWrapper } from "./AnnotationMapTestWrapper";
import {
  CITY_PIN,
  COUNTRY_PIN,
  MAP_TEST_HEIGHT,
} from "./annotationMapFixtures";

test("AnnotationMap renders a country pin marker at the country zoom band", async ({
  mount,
  page,
}) => {
  const component = await mount(
    <AnnotationMapTestWrapper
      pins={[COUNTRY_PIN, CITY_PIN]}
      center={[46.6, 2.2]}
      zoom={3}
      height={MAP_TEST_HEIGHT}
    />
  );

  // The map region renders with an accessible label.
  await expect(
    page.getByRole("region", {
      name: "Map of geographic document annotations",
    })
  ).toBeVisible({ timeout: 20000 });

  // At zoom 3 (country band) exactly one marker (France) should be shown.
  const markers = page.locator(".leaflet-marker-icon");
  await expect(markers).toHaveCount(1, { timeout: 20000 });
  await expect(markers.first()).toHaveAttribute("alt", /France/);
  await expect(component).toBeVisible();
});

test("AnnotationMap click on a pin opens the side panel with document links", async ({
  mount,
  page,
}) => {
  let clicked: string | null = null;
  const component = await mount(
    <AnnotationMapTestWrapper
      pins={[COUNTRY_PIN, CITY_PIN]}
      center={[46.6, 2.2]}
      zoom={3}
      height={MAP_TEST_HEIGHT}
      onPinClick={(pin) => {
        clicked = pin.canonicalName;
      }}
    />
  );

  const marker = page.locator(".leaflet-marker-icon").first();
  await expect(marker).toBeVisible({ timeout: 20000 });
  await marker.click();

  // The side panel (driven by the click) shows the place + document links.
  await expect(component).toContainText("France");
  await expect(component).toContainText("12 documents");
  const docButtons = component.getByRole("button", { name: /Open document/ });
  await expect(docButtons).toHaveCount(2);

  // The onPinClick callback fired with the selected pin.
  await expect.poll(() => clicked).toBe("France");
});

test("AnnotationMap zoom band selects city pins at high zoom", async ({
  mount,
  page,
}) => {
  await mount(
    <AnnotationMapTestWrapper
      pins={[COUNTRY_PIN, CITY_PIN]}
      center={[48.8566, 2.3522]}
      zoom={8}
      height={MAP_TEST_HEIGHT}
    />
  );

  // At zoom 8 (city band) only the city pin (Paris) should be shown.
  const markers = page.locator(".leaflet-marker-icon");
  await expect(markers).toHaveCount(1, { timeout: 20000 });
  await expect(markers.first()).toHaveAttribute("alt", /Paris/);
});
