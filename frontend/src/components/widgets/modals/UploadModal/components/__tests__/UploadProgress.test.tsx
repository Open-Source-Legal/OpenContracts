/**
 * Coverage for ``UploadProgress`` — the two reporting modes introduced by
 * the truthful bulk-import progress rework:
 *
 * - file-count mode (``progressPercent`` undefined): completion derived
 *   from per-file statuses, "N / M completed (P%)" label, indeterminate
 *   bar while files are in flight;
 * - streamed-archive mode (``progressPercent`` set): completion derived
 *   from byte progress, "P% uploaded" label, always-determinate bar, with
 *   an optional ``statusText`` override.
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { UploadProgress } from "../UploadProgress";
import type {
  FileUploadPackage,
  UploadStatus,
} from "../../hooks/useUploadState";

// Stub the design-system Progress bar so assertions can read the computed
// value/variant without depending on @os-legal/ui internals.
vi.mock("@os-legal/ui", () => ({
  Progress: ({ value, variant }: { value: number; variant: string }) => (
    <div data-testid="progress" data-value={value} data-variant={variant} />
  ),
}));

const makeFile = (
  status: UploadStatus,
  name = "doc.pdf"
): FileUploadPackage => ({
  file: new File(["content"], name, { type: "application/pdf" }),
  formData: { title: name, description: "", slug: "" },
  status,
});

describe("UploadProgress", () => {
  it("reports success when every file finished without failures", () => {
    render(
      <UploadProgress files={[makeFile("success"), makeFile("success")]} />
    );

    expect(
      screen.getByText("All files uploaded successfully")
    ).toBeInTheDocument();
    expect(screen.getByText("2 / 2 completed (100%)")).toBeInTheDocument();
    expect(screen.getByTestId("progress")).toHaveAttribute(
      "data-variant",
      "determinate"
    );
  });

  it("reports completion with errors when a file failed", () => {
    render(
      <UploadProgress files={[makeFile("success"), makeFile("failed")]} />
    );

    expect(
      screen.getByText("Upload completed with errors")
    ).toBeInTheDocument();
    expect(screen.getByText("1 / 2 completed (100%)")).toBeInTheDocument();
  });

  it("shows an indeterminate uploading state while files are in flight", () => {
    render(
      <UploadProgress files={[makeFile("success"), makeFile("uploading")]} />
    );

    expect(screen.getByText("Uploading files...")).toBeInTheDocument();
    expect(screen.getByText("1 / 2 completed (50%)")).toBeInTheDocument();
    expect(screen.getByTestId("progress")).toHaveAttribute(
      "data-variant",
      "indeterminate"
    );
  });

  it("renders a 0% baseline for an empty file list", () => {
    render(<UploadProgress files={[]} />);

    expect(screen.getByText("0 / 0 completed (0%)")).toBeInTheDocument();
    expect(screen.getByTestId("progress")).toHaveAttribute("data-value", "0");
  });

  it("prefers statusText and byte progress when streaming an archive", () => {
    render(
      <UploadProgress
        files={[makeFile("uploading", "docs.zip")]}
        progressPercent={42}
        statusText="Uploading archive..."
      />
    );

    expect(screen.getByText("Uploading archive...")).toBeInTheDocument();
    expect(screen.getByText("42% uploaded")).toBeInTheDocument();
    // A live byte stream renders a determinate bar even before completion.
    expect(screen.getByTestId("progress")).toHaveAttribute(
      "data-variant",
      "determinate"
    );
  });

  it("derives the uploading label from byte progress below 100%", () => {
    render(
      <UploadProgress
        files={[makeFile("uploading", "docs.zip")]}
        progressPercent={30}
      />
    );

    expect(screen.getByText("Uploading files...")).toBeInTheDocument();
    expect(screen.getByText("30% uploaded")).toBeInTheDocument();
  });

  it("treats 100% byte progress as complete", () => {
    render(
      <UploadProgress
        files={[makeFile("uploading", "docs.zip")]}
        progressPercent={100}
      />
    );

    expect(
      screen.getByText("All files uploaded successfully")
    ).toBeInTheDocument();
    expect(screen.getByText("100% uploaded")).toBeInTheDocument();
  });
});
