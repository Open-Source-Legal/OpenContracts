import React from "react";
import { test, expect } from "./utils/coverage";
import { MemoryRouter } from "react-router-dom";
import { ExtractListCard } from "../src/components/extracts/ExtractListCard";
import type { ExtractType } from "../src/types/graphql-api";
import { docScreenshot } from "./utils/docScreenshot";

/**
 * Minimal smoke tests for ``ExtractListCard``.
 *
 * The card is purely presentational — it renders an extract's name, a
 * derived status label, and a small stats line. The wrapper only needs a
 * ``MemoryRouter`` because the component uses ``useNavigate`` for the
 * default click handler (overridden in tests via ``onView``).
 */

const baseExtract = {
  id: "RXh0cmFjdFR5cGU6MQ==",
  name: "Q4 contract review",
  created: "2025-12-01T12:00:00Z",
  fullDocumentList: [
    { id: "doc-1" },
    { id: "doc-2" },
    { id: "doc-3" },
  ] as never,
  fieldset: {
    id: "fs-1",
    name: "Standard fieldset",
    fullColumnList: [{ id: "col-1" }, { id: "col-2" }],
  } as never,
  corpus: {
    id: "corpus-1",
    title: "Vendor agreements",
  } as never,
  myPermissions: ["READ"],
} as unknown as ExtractType;

test.describe("ExtractListCard", () => {
  test("renders extract name, status, and stats", async ({ mount, page }) => {
    const component = await mount(
      <MemoryRouter>
        <ExtractListCard extract={baseExtract} />
      </MemoryRouter>
    );

    await expect(component.getByText("Q4 contract review")).toBeVisible();
    await expect(component.getByText(/3 documents/)).toBeVisible();
    await expect(component.getByText(/from Vendor agreements/)).toBeVisible();

    await docScreenshot(page, "extracts--list-card--default");
  });

  test("highlights selected card", async ({ mount }) => {
    const component = await mount(
      <MemoryRouter>
        <ExtractListCard extract={baseExtract} isSelected />
      </MemoryRouter>
    );

    await expect(component.getByText("Q4 contract review")).toBeVisible();
  });

  test("invokes onView when clicked", async ({ mount }) => {
    let viewed = false;
    const component = await mount(
      <MemoryRouter>
        <ExtractListCard
          extract={baseExtract}
          onView={() => {
            viewed = true;
          }}
        />
      </MemoryRouter>
    );

    await component.getByText("Q4 contract review").click();
    await expect(() => expect(viewed).toBe(true)).toPass();
  });
});
