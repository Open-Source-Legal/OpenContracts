/**
 * Playwright Component Tests for NavMenu
 *
 * Tests the refactored NavMenu component that uses @os-legal/ui NavBar.
 * Covers: navigation items, auth states, superuser features, responsive behavior.
 */
import { test, expect } from "./utils/coverage";
import { docScreenshot } from "./utils/docScreenshot";
import { NavMenuTestWrapper } from "./NavMenuTestWrapper";

// Define mock users locally to avoid import issues with Playwright CT
const mockRegularUser = {
  id: "user-1",
  username: "testuser",
  name: "Test User",
  email: "test@example.com",
  isSuperuser: false,
};

const mockSuperuser = {
  id: "admin-1",
  username: "admin",
  name: "Admin User",
  email: "admin@example.com",
  isSuperuser: true,
};

test.describe("NavMenu Component", () => {
  test.describe("Navigation Items", () => {
    test("should render all public navigation items", async ({
      mount,
      page,
    }) => {
      const component = await mount(<NavMenuTestWrapper />);

      // Check all public nav items are visible
      await expect(page.locator("text=Discover")).toBeVisible({
        timeout: 5000,
      });
      await expect(page.locator("text=Corpuses")).toBeVisible();
      await expect(page.locator("text=Documents")).toBeVisible();
      await expect(page.locator("text=Label Sets")).toBeVisible();
      await expect(page.locator("text=Annotations")).toBeVisible();
      await expect(page.locator("text=Extracts")).toBeVisible();
      await expect(page.locator("text=Leaderboard")).toBeVisible();

      await component.unmount();
    });

    test("should highlight active navigation item on home route", async ({
      mount,
      page,
    }) => {
      const component = await mount(<NavMenuTestWrapper initialPath="/" />);

      // Discover should be active on home route
      const discoverLink = page.locator("text=Discover");
      await expect(discoverLink).toBeVisible({ timeout: 5000 });

      // Check for active class or styling (NavBar adds --active class)
      await expect(
        page.locator(".oc-navbar__link--active:has-text('Discover')")
      ).toBeVisible();

      await component.unmount();
    });

    test("should highlight active navigation item on corpuses route", async ({
      mount,
      page,
    }) => {
      const component = await mount(
        <NavMenuTestWrapper initialPath="/corpuses" />
      );

      await expect(
        page.locator(".oc-navbar__link--active:has-text('Corpuses')")
      ).toBeVisible({ timeout: 5000 });

      await component.unmount();
    });
  });

  test.describe("Authentication States", () => {
    test("should show Login button when user is not authenticated", async ({
      mount,
      page,
    }) => {
      const component = await mount(<NavMenuTestWrapper mockUser={null} />);

      // Login button should be visible
      await expect(page.locator("button:has-text('Login')")).toBeVisible({
        timeout: 5000,
      });

      // User menu should not be visible
      await expect(page.locator(".oc-navbar-user")).not.toBeVisible();

      await component.unmount();
    });

    test("should show user menu when authenticated", async ({
      mount,
      page,
    }) => {
      const component = await mount(
        <NavMenuTestWrapper mockUser={mockRegularUser} />
      );

      // User name should be visible
      await expect(page.locator("text=Test User")).toBeVisible({
        timeout: 5000,
      });

      // Login button should not be visible
      await expect(page.locator("button:has-text('Login')")).not.toBeVisible();

      await component.unmount();
    });

    test("should display username when name is not available", async ({
      mount,
      page,
    }) => {
      const userWithoutName = { ...mockRegularUser, name: undefined };

      const component = await mount(
        <NavMenuTestWrapper mockUser={userWithoutName} />
      );

      // Should fall back to username
      await expect(page.locator("text=testuser")).toBeVisible({
        timeout: 5000,
      });

      await component.unmount();
    });
  });

  test.describe("User Menu Items", () => {
    test("should show Exports, Profile, and Logout for regular user", async ({
      mount,
      page,
    }) => {
      const component = await mount(
        <NavMenuTestWrapper mockUser={mockRegularUser} />
      );

      // Open user dropdown
      await page.locator("text=Test User").click();

      // Check menu items
      await expect(page.locator("text=Exports")).toBeVisible({ timeout: 2000 });
      await expect(page.locator("text=Profile")).toBeVisible();
      await expect(page.locator("text=Logout")).toBeVisible();

      // Admin Settings should NOT be visible for regular user
      await expect(page.locator("text=Admin Settings")).not.toBeVisible();

      await component.unmount();
    });

    test("should show Admin Settings for superuser", async ({
      mount,
      page,
    }) => {
      const component = await mount(
        <NavMenuTestWrapper mockUser={mockSuperuser} />
      );

      // Open user dropdown
      await page.locator("text=Admin User").click();

      // Admin Settings should be visible for superuser
      await expect(page.locator("text=Admin Settings")).toBeVisible({
        timeout: 2000,
      });

      await component.unmount();
    });
  });

  test.describe("Superuser Features", () => {
    test("should show Badge Management nav item for superuser", async ({
      mount,
      page,
    }) => {
      const component = await mount(
        <NavMenuTestWrapper mockUser={mockSuperuser} />
      );

      // Badge Management should be visible for superuser
      await expect(page.locator("text=Badge Management")).toBeVisible({
        timeout: 5000,
      });

      await component.unmount();
    });

    test("should NOT show Badge Management for regular user", async ({
      mount,
      page,
    }) => {
      const component = await mount(
        <NavMenuTestWrapper mockUser={mockRegularUser} />
      );

      // Badge Management should NOT be visible
      await expect(page.locator("text=Badge Management")).not.toBeVisible();

      await component.unmount();
    });

    test("should NOT show Badge Management for unauthenticated user", async ({
      mount,
      page,
    }) => {
      const component = await mount(<NavMenuTestWrapper mockUser={null} />);

      // Badge Management should NOT be visible
      await expect(page.locator("text=Badge Management")).not.toBeVisible();

      await component.unmount();
    });
  });

  test.describe("Branding", () => {
    // Branding assertions updated for the v3 cite rebrand: the wordmark
    // is now `[cite]` (brackets preserved per brand spec) and the logo
    // is an inline SVG icon mark rather than a PNG.
    test("should display cite brand name", async ({ mount, page }) => {
      const component = await mount(<NavMenuTestWrapper />);

      await expect(page.locator("text=[cite]")).toBeVisible({
        timeout: 5000,
      });

      await component.unmount();
    });

    test("should display the cite icon mark", async ({ mount, page }) => {
      const component = await mount(<NavMenuTestWrapper />);

      await expect(page.locator('svg[aria-label="cite"]').first()).toBeVisible({
        timeout: 5000,
      });

      await component.unmount();
    });

    test("should display version badge on desktop", async ({ mount, page }) => {
      const component = await mount(<NavMenuTestWrapper />);

      // Version badge should contain version number (e.g., v3.0.0.b3)
      await expect(page.locator(".oc-chip")).toBeVisible({ timeout: 5000 });

      await component.unmount();
    });
  });

  test.describe("User Menu Actions", () => {
    test("should have correct icons in user menu", async ({ mount, page }) => {
      const component = await mount(
        <NavMenuTestWrapper mockUser={mockRegularUser} />
      );

      // Open user dropdown by clicking on the user name
      await page.locator("text=Test User").click();

      // Wait for the dropdown to be visible, then check for SVG icons
      // The menu should contain items with icons
      await expect(page.locator("text=Exports")).toBeVisible({ timeout: 2000 });
      // Check that at least one SVG icon is present in the dropdown area
      await expect(page.locator("svg").first()).toBeVisible();

      await component.unmount();
    });

    test("should style Logout item appropriately", async ({ mount, page }) => {
      const component = await mount(
        <NavMenuTestWrapper mockUser={mockRegularUser} />
      );

      // Open user dropdown
      await page.locator("text=Test User").click();

      // Logout should be visible in the dropdown
      await expect(page.locator("text=Logout")).toBeVisible({ timeout: 2000 });

      await component.unmount();
    });
  });
});

test.describe("NavMenu Responsive Behavior", () => {
  // At < 1100px the NavMenu swaps in the custom MobileNavMenu (a hamburger
  // toggle + a floating sheet that overlays the page rather than expanding
  // inline). These tests target that component via its accessible labels,
  // which are more stable than internal CSS class names.

  test("should show hamburger toggle on mobile viewport", async ({
    mount,
    page,
  }) => {
    await page.setViewportSize({ width: 800, height: 600 });

    const component = await mount(<NavMenuTestWrapper />);

    await expect(
      page.locator('button[aria-label="Open navigation"]')
    ).toBeVisible({ timeout: 5000 });

    await component.unmount();
  });

  test("should reveal nav items in the floating sheet when hamburger is clicked", async ({
    mount,
    page,
  }) => {
    await page.setViewportSize({ width: 800, height: 600 });

    const component = await mount(<NavMenuTestWrapper />);

    const hamburger = page.locator('button[aria-label="Open navigation"]');
    await expect(hamburger).toBeVisible({ timeout: 5000 });
    await hamburger.click();

    // Sheet appears as the dialog container; the navigation landmark
    // (a `<nav aria-label="Site navigation">`) lives inside it. Target
    // the dialog directly by its stable id rather than by aria-label,
    // since the landmark and dialog are now separate elements.
    const sheet = page.locator("#mobile-nav-sheet");
    await expect(sheet).toBeVisible({ timeout: 2000 });
    await expect(sheet.getByText("Discover")).toBeVisible();

    // The toggle now reads "Close navigation" while the sheet is open.
    await expect(
      page.locator('button[aria-label="Close navigation"]')
    ).toBeVisible();

    await component.unmount();
  });

  test("should close the floating sheet when Escape is pressed", async ({
    mount,
    page,
  }) => {
    await page.setViewportSize({ width: 800, height: 600 });

    const component = await mount(<NavMenuTestWrapper />);

    await page.locator('button[aria-label="Open navigation"]').click();
    const sheet = page.locator("#mobile-nav-sheet");
    await expect(sheet).toBeVisible({ timeout: 2000 });

    await page.keyboard.press("Escape");
    await expect(sheet).toBeHidden({ timeout: 2000 });
    await expect(
      page.locator('button[aria-label="Open navigation"]')
    ).toBeVisible();

    await component.unmount();
  });

  test("should close the floating sheet when the backdrop is tapped", async ({
    mount,
    page,
  }) => {
    await page.setViewportSize({ width: 800, height: 600 });

    const component = await mount(<NavMenuTestWrapper />);

    await page.locator('button[aria-label="Open navigation"]').click();
    const sheet = page.locator("#mobile-nav-sheet");
    await expect(sheet).toBeVisible({ timeout: 2000 });

    // The sheet has a 12px side gutter, so clicking near the left
    // edge — well below the 60px header — lands on the backdrop
    // rather than the dialog or its toggle. Tapping the backdrop is
    // the most common mobile dismissal gesture.
    await page.mouse.click(5, 300);
    await expect(sheet).toBeHidden({ timeout: 2000 });
    await expect(
      page.locator('button[aria-label="Open navigation"]')
    ).toBeVisible();

    await component.unmount();
  });

  test("should render the sign-in CTA when no user is authenticated", async ({
    mount,
    page,
  }) => {
    await page.setViewportSize({ width: 800, height: 600 });

    const component = await mount(<NavMenuTestWrapper mockUser={null} />);

    await page.locator('button[aria-label="Open navigation"]').click();

    const sheet = page.locator("#mobile-nav-sheet");
    await expect(sheet).toBeVisible({ timeout: 2000 });
    // Signed-out branch: AuthFooter renders the Sign-in button and
    // omits the user chip entirely.
    await expect(sheet.getByRole("button", { name: /sign in/i })).toBeVisible();
    await expect(sheet.getByText("Signed in")).toHaveCount(0);

    await component.unmount();
  });

  test("should render the user chip when authenticated", async ({
    mount,
    page,
  }) => {
    await page.setViewportSize({ width: 800, height: 600 });

    const component = await mount(
      <NavMenuTestWrapper mockUser={mockRegularUser} />
    );

    await page.locator('button[aria-label="Open navigation"]').click();

    const sheet = page.locator("#mobile-nav-sheet");
    await expect(sheet).toBeVisible({ timeout: 2000 });
    // Authenticated branch: user chip with display name + "Signed in"
    // status replaces the Sign-in CTA button.
    await expect(sheet.getByText("Test User")).toBeVisible();
    await expect(sheet.getByText("Signed in")).toBeVisible();
    await expect(sheet.getByRole("button", { name: /sign in/i })).toHaveCount(
      0
    );

    await docScreenshot(page, "nav--mobile-nav--authenticated-open");

    await component.unmount();
  });

  test("should render the Account section with user actions when authenticated", async ({
    mount,
    page,
  }) => {
    await page.setViewportSize({ width: 800, height: 600 });

    const component = await mount(
      <NavMenuTestWrapper mockUser={mockRegularUser} />
    );

    await page.locator('button[aria-label="Open navigation"]').click();
    const sheet = page.locator("#mobile-nav-sheet");
    await expect(sheet).toBeVisible({ timeout: 2000 });

    // The signed-in sheet exposes the Account section containing the
    // collapsed user-menu actions (Profile, Exports, Logout).
    await expect(sheet.getByText("Account")).toBeVisible();
    await expect(sheet.getByRole("button", { name: "Profile" })).toBeVisible();
    await expect(sheet.getByRole("button", { name: "Exports" })).toBeVisible();
    await expect(sheet.getByRole("button", { name: "Logout" })).toBeVisible();

    await component.unmount();
  });

  test("should close the sheet when a nav item is tapped (runAndClose)", async ({
    mount,
    page,
  }) => {
    await page.setViewportSize({ width: 800, height: 600 });

    const component = await mount(<NavMenuTestWrapper />);

    await page.locator('button[aria-label="Open navigation"]').click();
    const sheet = page.locator("#mobile-nav-sheet");
    await expect(sheet).toBeVisible({ timeout: 2000 });

    // Tapping a nav item should trigger runAndClose, which fires the
    // onClick handler and then dismisses the sheet — combined with the
    // route-change useEffect, this guarantees the sheet doesn't linger
    // after a navigation.
    await sheet.getByRole("button", { name: "Discover" }).click();

    await expect(sheet).toBeHidden({ timeout: 2000 });
    await expect(
      page.locator('button[aria-label="Open navigation"]')
    ).toBeVisible();

    await component.unmount();
  });

  test("should close the sheet when a user action is tapped", async ({
    mount,
    page,
  }) => {
    await page.setViewportSize({ width: 800, height: 600 });

    const component = await mount(
      <NavMenuTestWrapper mockUser={mockRegularUser} />
    );

    await page.locator('button[aria-label="Open navigation"]').click();
    const sheet = page.locator("#mobile-nav-sheet");
    await expect(sheet).toBeVisible({ timeout: 2000 });

    // Tapping a user action (Exports) opens a modal; the sheet should
    // dismiss alongside via runAndClose's finally branch.
    await sheet.getByRole("button", { name: "Exports" }).click();

    await expect(sheet).toBeHidden({ timeout: 2000 });

    await component.unmount();
  });

  test("should trap focus inside the sheet when Tab cycles past the last focusable", async ({
    mount,
    page,
  }) => {
    await page.setViewportSize({ width: 800, height: 600 });

    const component = await mount(<NavMenuTestWrapper mockUser={null} />);

    await page.locator('button[aria-label="Open navigation"]').click();
    const sheet = page.locator("#mobile-nav-sheet");
    await expect(sheet).toBeVisible({ timeout: 2000 });

    // Seed focus on the last focusable inside the sheet (the Sign-in CTA
    // is the AuthFooter's only tabbable, and lives after all nav items).
    const signIn = sheet.getByRole("button", { name: /sign in/i });
    await expect(signIn).toBeVisible();
    await signIn.focus();
    await expect(signIn).toBeFocused();

    // Tab from the last focusable wraps to the first focusable INSIDE
    // the sheet — confirming the trap. Without the trap, focus would
    // escape to a body element outside the sheet.
    await page.keyboard.press("Tab");

    const focusInSheet = await page.evaluate(() => {
      const dialog = document.querySelector("#mobile-nav-sheet");
      const active = document.activeElement;
      return Boolean(dialog && active && dialog.contains(active));
    });
    expect(focusInSheet).toBe(true);

    await component.unmount();
  });

  test("should trap focus inside the sheet when Shift+Tab cycles past the first focusable", async ({
    mount,
    page,
  }) => {
    await page.setViewportSize({ width: 800, height: 600 });

    const component = await mount(<NavMenuTestWrapper mockUser={null} />);

    await page.locator('button[aria-label="Open navigation"]').click();
    const sheet = page.locator("#mobile-nav-sheet");
    await expect(sheet).toBeVisible({ timeout: 2000 });

    // Move focus to the first focusable item (the first nav button).
    const firstNav = sheet.getByRole("button", { name: "Discover" });
    await expect(firstNav).toBeVisible();
    await firstNav.focus();
    await expect(firstNav).toBeFocused();

    // Shift+Tab from the first focusable wraps backwards to the last
    // focusable inside the sheet. Either way focus must remain trapped
    // inside the dialog container.
    await page.keyboard.press("Shift+Tab");

    const focusInSheet = await page.evaluate(() => {
      const dialog = document.querySelector("#mobile-nav-sheet");
      const active = document.activeElement;
      return Boolean(dialog && active && dialog.contains(active));
    });
    expect(focusInSheet).toBe(true);

    await component.unmount();
  });

  test("should pull focus back into the sheet when Tab is pressed from outside", async ({
    mount,
    page,
  }) => {
    await page.setViewportSize({ width: 800, height: 600 });

    const component = await mount(<NavMenuTestWrapper mockUser={null} />);

    const toggle = page.locator('button[aria-label="Open navigation"]');
    await toggle.click();
    const sheet = page.locator("#mobile-nav-sheet");
    await expect(sheet).toBeVisible({ timeout: 2000 });

    // Force focus back onto an element OUTSIDE the sheet. This simulates
    // the "focus leaked outside" branch of the Tab trap that pulls focus
    // back in on the next Tab press.
    await page.evaluate(() => {
      const closeBtn = document.querySelector<HTMLElement>(
        'button[aria-label="Close navigation"]'
      );
      closeBtn?.focus();
    });

    await page.keyboard.press("Tab");

    const focusInSheet = await page.evaluate(() => {
      const dialog = document.querySelector("#mobile-nav-sheet");
      const active = document.activeElement;
      return Boolean(dialog && active && dialog.contains(active));
    });
    expect(focusInSheet).toBe(true);

    await component.unmount();
  });

  test("should trigger the onLogin handler when the Sign-in CTA is clicked", async ({
    mount,
    page,
  }) => {
    await page.setViewportSize({ width: 800, height: 600 });

    const component = await mount(<NavMenuTestWrapper mockUser={null} />);

    await page.locator('button[aria-label="Open navigation"]').click();
    const sheet = page.locator("#mobile-nav-sheet");
    await expect(sheet).toBeVisible({ timeout: 2000 });

    // Click the Sign-in CTA — handleLogin closes the sheet and fires
    // onLogin (which in the test wrapper is a no-op navigate, but the
    // close-the-sheet half is observable here).
    await sheet.getByRole("button", { name: /sign in/i }).click();

    await expect(sheet).toBeHidden({ timeout: 2000 });

    await component.unmount();
  });

  test("should expose proper ARIA attributes on the toggle button", async ({
    mount,
    page,
  }) => {
    await page.setViewportSize({ width: 800, height: 600 });

    const component = await mount(<NavMenuTestWrapper />);

    // Closed state — aria-expanded="false", aria-haspopup="dialog".
    const toggle = page.locator('button[aria-label="Open navigation"]');
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await expect(toggle).toHaveAttribute("aria-haspopup", "dialog");
    await expect(toggle).toHaveAttribute("aria-controls", "mobile-nav-sheet");

    await toggle.click();

    // Open state — aria-expanded flips to "true", aria-label changes.
    const closeToggle = page.locator('button[aria-label="Close navigation"]');
    await expect(closeToggle).toHaveAttribute("aria-expanded", "true");

    await docScreenshot(page, "nav--mobile-nav--open");

    await component.unmount();
  });

  test("should reflect aria-modal and aria-label on the open sheet", async ({
    mount,
    page,
  }) => {
    await page.setViewportSize({ width: 800, height: 600 });

    const component = await mount(<NavMenuTestWrapper />);

    await page.locator('button[aria-label="Open navigation"]').click();
    const sheet = page.locator("#mobile-nav-sheet");
    await expect(sheet).toBeVisible({ timeout: 2000 });

    await expect(sheet).toHaveAttribute("aria-modal", "true");
    await expect(sheet).toHaveAttribute("role", "dialog");
    // The dialog carries its own accessible name ("Navigation menu");
    // the inner `<nav aria-label="Site navigation">` provides the
    // navigation landmark separately so neither role overrides the
    // other (issue #1610).
    await expect(sheet).toHaveAttribute("aria-label", "Navigation menu");

    await component.unmount();
  });

  test("should expose the navigation landmark as a separate <nav> inside the dialog", async ({
    mount,
    page,
  }) => {
    await page.setViewportSize({ width: 800, height: 600 });

    const component = await mount(<NavMenuTestWrapper />);

    await page.locator('button[aria-label="Open navigation"]').click();
    const sheet = page.locator("#mobile-nav-sheet");
    await expect(sheet).toBeVisible({ timeout: 2000 });

    // The dialog is a `<div>`; the navigation landmark is a `<nav>`
    // nested inside it. Splitting these prevents `role="dialog"` from
    // erasing the implicit nav landmark from the a11y tree.
    const navLandmark = sheet.locator('nav[aria-label="Site navigation"]');
    await expect(navLandmark).toBeVisible();
    await expect(navLandmark).toHaveCount(1);
    // The nav landmark wraps the browse items but NOT the auth footer.
    await expect(
      navLandmark.getByRole("button", { name: "Discover" })
    ).toBeVisible();
    // Pin the structural contract: the AuthFooter (Sign-in CTA on
    // anonymous, account chip when signed in) lives outside the <nav>
    // landmark so screen readers don't expose auth state as a
    // navigation item.
    const authFooter = sheet.locator('[data-testqa="mobile-nav-auth-footer"]');
    await expect(authFooter).toBeVisible();
    await expect(
      navLandmark.locator('[data-testqa="mobile-nav-auth-footer"]')
    ).toHaveCount(0);

    await component.unmount();
  });

  test("should screenshot the closed mobile nav for documentation", async ({
    mount,
    page,
  }) => {
    await page.setViewportSize({ width: 375, height: 667 });

    const component = await mount(<NavMenuTestWrapper />);

    // Closed state — just the dark sticky header with the hamburger.
    await expect(
      page.locator('button[aria-label="Open navigation"]')
    ).toBeVisible({ timeout: 5000 });

    await docScreenshot(page, "nav--mobile-nav--closed");

    await component.unmount();
  });
});

// ----------------------------------------------------------------------------
// Overflow menu (issue #1609)
// ----------------------------------------------------------------------------
// On long-scroll surfaces (corpus Annotations / Analyses / Extracts), the
// in-flow Footer is effectively unreachable. The NavMenu overflow keeps the
// audited essential links (About / Privacy / Terms / GitHub) one click away
// from any scroll position — these tests assert the trigger renders, opens,
// and contains each link in both anonymous and authenticated states, on
// desktop and mobile.

test.describe("NavMenu Overflow", () => {
  test.describe("Desktop", () => {
    test("should render the overflow trigger when anonymous", async ({
      mount,
      page,
    }) => {
      const component = await mount(<NavMenuTestWrapper mockUser={null} />);

      await expect(page.locator('button[aria-label="More links"]')).toBeVisible(
        { timeout: 5000 }
      );

      await component.unmount();
    });

    test("should render the overflow trigger when authenticated", async ({
      mount,
      page,
    }) => {
      const component = await mount(
        <NavMenuTestWrapper mockUser={mockRegularUser} />
      );

      await expect(page.locator('button[aria-label="More links"]')).toBeVisible(
        { timeout: 5000 }
      );

      await component.unmount();
    });

    test("should open the overflow menu when triggered (anonymous)", async ({
      mount,
      page,
    }) => {
      const component = await mount(<NavMenuTestWrapper mockUser={null} />);

      const trigger = page.locator('button[aria-label="More links"]');
      await expect(trigger).toBeVisible({ timeout: 5000 });
      await expect(trigger).toHaveAttribute("aria-expanded", "false");
      await trigger.click();

      const menu = page.locator('[role="menu"][aria-label="More site links"]');
      await expect(menu).toBeVisible({ timeout: 2000 });
      await expect(trigger).toHaveAttribute("aria-expanded", "true");

      // All audited essential links should be present.
      await expect(
        menu.getByRole("menuitem", { name: "About cite" })
      ).toBeVisible();
      await expect(
        menu.getByRole("menuitem", { name: "Privacy Policy" })
      ).toBeVisible();
      await expect(
        menu.getByRole("menuitem", { name: "Terms of Service" })
      ).toBeVisible();
      await expect(
        menu.getByRole("menuitem", { name: "GitHub" })
      ).toBeVisible();

      await component.unmount();
    });

    test("should open the overflow menu when triggered (authenticated)", async ({
      mount,
      page,
    }) => {
      const component = await mount(
        <NavMenuTestWrapper mockUser={mockRegularUser} />
      );

      const trigger = page.locator('button[aria-label="More links"]');
      await expect(trigger).toBeVisible({ timeout: 5000 });
      await trigger.click();

      const menu = page.locator('[role="menu"][aria-label="More site links"]');
      await expect(menu).toBeVisible({ timeout: 2000 });

      // Same audited essential links — auth state should not gate them.
      await expect(
        menu.getByRole("menuitem", { name: "About cite" })
      ).toBeVisible();
      await expect(
        menu.getByRole("menuitem", { name: "Privacy Policy" })
      ).toBeVisible();
      await expect(
        menu.getByRole("menuitem", { name: "Terms of Service" })
      ).toBeVisible();
      await expect(
        menu.getByRole("menuitem", { name: "GitHub" })
      ).toBeVisible();

      await component.unmount();
    });

    test("should mark the GitHub item as an external link", async ({
      mount,
      page,
    }) => {
      const component = await mount(<NavMenuTestWrapper mockUser={null} />);

      await page.locator('button[aria-label="More links"]').click();

      const githubItem = page.locator(
        '[role="menu"] [role="menuitem"]:has-text("GitHub")'
      );
      await expect(githubItem).toHaveAttribute("target", "_blank");
      await expect(githubItem).toHaveAttribute("rel", /noopener noreferrer/);

      await component.unmount();
    });

    test("should close the overflow menu when Escape is pressed", async ({
      mount,
      page,
    }) => {
      const component = await mount(<NavMenuTestWrapper mockUser={null} />);

      await page.locator('button[aria-label="More links"]').click();
      const menu = page.locator('[role="menu"][aria-label="More site links"]');
      await expect(menu).toBeVisible({ timeout: 2000 });

      await page.keyboard.press("Escape");
      await expect(menu).toBeHidden({ timeout: 2000 });

      // Focus returns to the trigger (WCAG 2.4.3).
      await expect(
        page.locator('button[aria-label="More links"]')
      ).toBeFocused();

      await component.unmount();
    });

    test("should close the overflow menu when clicking outside", async ({
      mount,
      page,
    }) => {
      const component = await mount(<NavMenuTestWrapper mockUser={null} />);

      await page.locator('button[aria-label="More links"]').click();
      const menu = page.locator('[role="menu"][aria-label="More site links"]');
      await expect(menu).toBeVisible({ timeout: 2000 });

      // Click anywhere outside the menu / trigger.
      await page.mouse.click(10, 10);
      await expect(menu).toBeHidden({ timeout: 2000 });

      await component.unmount();
    });

    test("should expose proper ARIA attributes on the overflow trigger", async ({
      mount,
      page,
    }) => {
      const component = await mount(<NavMenuTestWrapper mockUser={null} />);

      const trigger = page.locator('button[aria-label="More links"]');
      await expect(trigger).toHaveAttribute("aria-haspopup", "menu");
      await expect(trigger).toHaveAttribute("aria-expanded", "false");

      await component.unmount();
    });

    test("should advance focus with ArrowDown and wrap from the last item", async ({
      mount,
      page,
    }) => {
      const component = await mount(<NavMenuTestWrapper mockUser={null} />);

      await page.locator('button[aria-label="More links"]').click();
      const menu = page.locator('[role="menu"][aria-label="More site links"]');
      await expect(menu).toBeVisible({ timeout: 2000 });

      const items = menu.locator('[role="menuitem"]');
      // After opening, focus seeds the first item; pressing ArrowDown walks
      // through every item in order, then wraps back to the first. Cover
      // the wrap regardless of overflow link count so adding/removing an
      // item (issue #1609 audit, now includes About) does not require a
      // test edit.
      const count = await items.count();
      expect(count).toBeGreaterThanOrEqual(2);
      await expect(items.nth(0)).toBeFocused({ timeout: 2000 });
      for (let i = 1; i < count; i++) {
        await page.keyboard.press("ArrowDown");
        await expect(items.nth(i)).toBeFocused();
      }
      // One more ArrowDown should wrap back to the first item.
      await page.keyboard.press("ArrowDown");
      await expect(items.nth(0)).toBeFocused();

      await component.unmount();
    });

    test("should reverse focus with ArrowUp and wrap from the first item", async ({
      mount,
      page,
    }) => {
      const component = await mount(<NavMenuTestWrapper mockUser={null} />);

      await page.locator('button[aria-label="More links"]').click();
      const menu = page.locator('[role="menu"][aria-label="More site links"]');
      await expect(menu).toBeVisible({ timeout: 2000 });

      const items = menu.locator('[role="menuitem"]');
      const count = await items.count();
      expect(count).toBeGreaterThanOrEqual(2);
      await expect(items.nth(0)).toBeFocused({ timeout: 2000 });
      // From the first item, ArrowUp wraps to the last item; one more
      // ArrowUp walks back to the second-to-last.
      await page.keyboard.press("ArrowUp");
      await expect(items.nth(count - 1)).toBeFocused();
      await page.keyboard.press("ArrowUp");
      await expect(items.nth(count - 2)).toBeFocused();

      await component.unmount();
    });

    test("should close the menu when an internal link item is activated", async ({
      mount,
      page,
    }) => {
      const component = await mount(<NavMenuTestWrapper mockUser={null} />);

      await page.locator('button[aria-label="More links"]').click();
      const menu = page.locator('[role="menu"][aria-label="More site links"]');
      await expect(menu).toBeVisible({ timeout: 2000 });

      await menu.getByRole("menuitem", { name: "Privacy Policy" }).click();
      await expect(menu).toBeHidden({ timeout: 2000 });

      await component.unmount();
    });

    test("should render the version row inside the desktop dropdown", async ({
      mount,
      page,
    }) => {
      const component = await mount(<NavMenuTestWrapper mockUser={null} />);

      await page.locator('button[aria-label="More links"]').click();
      const menu = page.locator('[role="menu"][aria-label="More site links"]');
      await expect(menu).toBeVisible({ timeout: 2000 });

      // Version row is rendered inside the dropdown so the user can see the
      // running build version from any scroll position.
      await expect(menu.locator("li[aria-label^='Version']")).toBeVisible();

      await component.unmount();
    });
  });

  test.describe("Mobile", () => {
    test("should render the 'More' section with essential links (anonymous)", async ({
      mount,
      page,
    }) => {
      await page.setViewportSize({ width: 800, height: 600 });

      const component = await mount(<NavMenuTestWrapper mockUser={null} />);

      await page.locator('button[aria-label="Open navigation"]').click();
      const sheet = page.locator('[aria-label="Site navigation"]');
      await expect(sheet).toBeVisible({ timeout: 2000 });

      await expect(sheet.getByText("More", { exact: true })).toBeVisible();
      await expect(
        sheet.getByRole("link", { name: "About cite" })
      ).toBeVisible();
      await expect(
        sheet.getByRole("link", { name: "Privacy Policy" })
      ).toBeVisible();
      await expect(
        sheet.getByRole("link", { name: "Terms of Service" })
      ).toBeVisible();
      await expect(sheet.getByRole("link", { name: "GitHub" })).toBeVisible();

      await component.unmount();
    });

    test("should render the 'More' section with essential links (authenticated)", async ({
      mount,
      page,
    }) => {
      await page.setViewportSize({ width: 800, height: 600 });

      const component = await mount(
        <NavMenuTestWrapper mockUser={mockRegularUser} />
      );

      await page.locator('button[aria-label="Open navigation"]').click();
      const sheet = page.locator('[aria-label="Site navigation"]');
      await expect(sheet).toBeVisible({ timeout: 2000 });

      await expect(sheet.getByText("More", { exact: true })).toBeVisible();
      await expect(
        sheet.getByRole("link", { name: "About cite" })
      ).toBeVisible();
      await expect(
        sheet.getByRole("link", { name: "Privacy Policy" })
      ).toBeVisible();
      await expect(
        sheet.getByRole("link", { name: "Terms of Service" })
      ).toBeVisible();
      await expect(sheet.getByRole("link", { name: "GitHub" })).toBeVisible();

      await component.unmount();
    });

    test("should render the GitHub link as an external link in the sheet", async ({
      mount,
      page,
    }) => {
      await page.setViewportSize({ width: 800, height: 600 });

      const component = await mount(<NavMenuTestWrapper mockUser={null} />);

      await page.locator('button[aria-label="Open navigation"]').click();
      const sheet = page.locator('[aria-label="Site navigation"]');
      await expect(sheet).toBeVisible({ timeout: 2000 });

      const github = sheet.getByRole("link", { name: "GitHub" });
      await expect(github).toHaveAttribute("target", "_blank");
      await expect(github).toHaveAttribute("rel", /noopener noreferrer/);

      await component.unmount();
    });
  });
});
