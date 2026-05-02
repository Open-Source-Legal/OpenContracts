import { test, expect } from "./utils/coverage";
import { docScreenshot } from "./utils/docScreenshot";
import { MCPShareButton } from "../src/components/common/MCPShareButton";
import { MCPShareButtonTestWrapper } from "./MCPShareButtonTestWrapper";

test.describe("MCPShareButton", () => {
  test("renders public variant with Cable icon and endpoint URL", async ({
    mount,
    page,
  }) => {
    await mount(
      <MCPShareButtonTestWrapper>
        <MCPShareButton corpusSlug="my-public-corpus" isPublic={true} />
      </MCPShareButtonTestWrapper>
    );

    const trigger = page.getByTestId("mcp-share-button-trigger");
    await expect(trigger).toBeVisible();
    await expect(trigger).toHaveAttribute("aria-label", "Share MCP endpoint");

    await trigger.click();

    const urlInput = page.getByTestId("mcp-share-button-url-input");
    await expect(urlInput).toBeVisible();
    await expect(urlInput).toHaveValue(/\/mcp\/corpus\/my-public-corpus$/);

    await expect(
      page.getByTestId("mcp-share-button-copy-button")
    ).toBeVisible();
    await expect(
      page.getByText("Add this URL to your MCP client configuration.")
    ).toBeVisible();

    await docScreenshot(page, "corpus--mcp-share-button--public");
  });

  test("renders private variant with Lock icon and explanation", async ({
    mount,
    page,
  }) => {
    await mount(
      <MCPShareButtonTestWrapper>
        <MCPShareButton corpusSlug="my-private-corpus" isPublic={false} />
      </MCPShareButtonTestWrapper>
    );

    const trigger = page.getByTestId("mcp-share-button-trigger");
    await expect(trigger).toBeVisible();
    await expect(trigger).toHaveAttribute(
      "aria-label",
      "MCP endpoint (corpus is private)"
    );

    await trigger.click();

    await expect(
      page.getByText(
        "MCP endpoints are only exposed for public corpora. Make this corpus public from its settings to share it via the Model Context Protocol."
      )
    ).toBeVisible();
    await expect(
      page.getByText(
        "Once public, the endpoint will appear here for AI assistants to connect."
      )
    ).toBeVisible();

    await expect(page.getByTestId("mcp-share-button-url-input")).toHaveCount(0);
    await expect(page.getByTestId("mcp-share-button-copy-button")).toHaveCount(
      0
    );

    await docScreenshot(page, "corpus--mcp-share-button--private");
  });

  test("toggles popover on repeated clicks", async ({ mount, page }) => {
    await mount(
      <MCPShareButtonTestWrapper>
        <MCPShareButton corpusSlug="toggleable" isPublic={true} />
      </MCPShareButtonTestWrapper>
    );

    const trigger = page.getByTestId("mcp-share-button-trigger");
    await trigger.click();
    await expect(page.getByTestId("mcp-share-button-url-input")).toBeVisible();

    await trigger.click();
    await expect(trigger).toHaveAttribute("aria-expanded", "false");
    // Popover hides via visibility: hidden so it stays in the DOM but is no
    // longer visible to users.
    await expect(page.getByTestId("mcp-share-button-url-input")).toBeHidden();
  });

  test("defaults to public when isPublic is omitted", async ({
    mount,
    page,
  }) => {
    await mount(
      <MCPShareButtonTestWrapper>
        <MCPShareButton corpusSlug="default-public" />
      </MCPShareButtonTestWrapper>
    );

    const trigger = page.getByTestId("mcp-share-button-trigger");
    await expect(trigger).toHaveAttribute("aria-label", "Share MCP endpoint");

    await trigger.click();

    const urlInput = page.getByTestId("mcp-share-button-url-input");
    await expect(urlInput).toBeVisible();
    await expect(urlInput).toHaveValue(/\/mcp\/corpus\/default-public$/);
  });

  test("renders without label when showLabel is false", async ({
    mount,
    page,
  }) => {
    await mount(
      <MCPShareButtonTestWrapper>
        <MCPShareButton
          corpusSlug="no-label"
          isPublic={true}
          showLabel={false}
        />
      </MCPShareButtonTestWrapper>
    );

    const trigger = page.getByTestId("mcp-share-button-trigger");
    await expect(trigger).toBeVisible();
    await expect(trigger).not.toContainText("MCP");
  });

  test("renders small size variant", async ({ mount, page }) => {
    await mount(
      <MCPShareButtonTestWrapper>
        <MCPShareButton corpusSlug="small-size" isPublic={true} size="sm" />
      </MCPShareButtonTestWrapper>
    );

    const trigger = page.getByTestId("mcp-share-button-trigger");
    await expect(trigger).toBeVisible();
    // 14px Cable icon (size="sm" branch)
    await expect(trigger.locator("svg").first()).toHaveAttribute("width", "14");
  });

  test("renders small size variant for private corpora", async ({
    mount,
    page,
  }) => {
    await mount(
      <MCPShareButtonTestWrapper>
        <MCPShareButton corpusSlug="small-private" isPublic={false} size="sm" />
      </MCPShareButtonTestWrapper>
    );

    const trigger = page.getByTestId("mcp-share-button-trigger");
    await expect(trigger).toBeVisible();
    // 14px Lock icon (size="sm" branch on the !isPublic path)
    await expect(trigger.locator("svg").first()).toHaveAttribute("width", "14");
  });

  test("copy button switches to checkmark and 'Copied' aria-label after click", async ({
    mount,
    page,
    context,
  }) => {
    // Grant clipboard permissions so navigator.clipboard.writeText resolves
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);

    await mount(
      <MCPShareButtonTestWrapper>
        <MCPShareButton corpusSlug="copyable" isPublic={true} />
      </MCPShareButtonTestWrapper>
    );

    const trigger = page.getByTestId("mcp-share-button-trigger");
    await trigger.click();

    const copyButton = page.getByTestId("mcp-share-button-copy-button");
    await expect(copyButton).toHaveAttribute("aria-label", "Copy URL");

    await copyButton.click();

    await expect(copyButton).toHaveAttribute("aria-label", "Copied");
  });

  test("Escape key closes the popover", async ({ mount, page }) => {
    await mount(
      <MCPShareButtonTestWrapper>
        <MCPShareButton corpusSlug="escape-test" isPublic={true} />
      </MCPShareButtonTestWrapper>
    );

    const trigger = page.getByTestId("mcp-share-button-trigger");
    await trigger.click();
    await expect(page.getByTestId("mcp-share-button-url-input")).toBeVisible();

    await page.keyboard.press("Escape");
    await expect(trigger).toHaveAttribute("aria-expanded", "false");
    await expect(page.getByTestId("mcp-share-button-url-input")).toBeHidden();
  });
});
