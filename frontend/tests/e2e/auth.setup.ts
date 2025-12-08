import { test as setup, expect } from "@playwright/test";
import path from "path";

const authFile = path.join(__dirname, ".auth/user.json");

/**
 * Authentication setup - runs before all other tests.
 *
 * Logs in via the UI and saves the auth state (cookies, localStorage)
 * for reuse in subsequent tests.
 */
setup("authenticate", async ({ page }) => {
  const testUser = process.env.E2E_TEST_USER || "admin@example.com";
  const testPassword = process.env.E2E_TEST_PASSWORD || "admin";

  console.log(`   Authenticating as ${testUser}...`);

  // Go to login page
  await page.goto("/login");

  // Wait for login form to be visible
  await expect(
    page.locator('input[name="username"], input[type="email"]')
  ).toBeVisible({
    timeout: 10000,
  });

  // Fill in credentials
  // The login form might use different field names, try common patterns
  const usernameInput = page
    .locator('input[name="username"], input[name="email"], input[type="email"]')
    .first();
  const passwordInput = page
    .locator('input[name="password"], input[type="password"]')
    .first();

  await usernameInput.fill(testUser);
  await passwordInput.fill(testPassword);

  // Click login button
  const loginButton = page
    .locator(
      'button[type="submit"], button:has-text("Login"), button:has-text("Sign in")'
    )
    .first();
  await loginButton.click();

  // Wait for successful login - should redirect away from login page
  // and show authenticated content (e.g., dashboard, corpuses list)
  await expect(page).not.toHaveURL(/\/login/, { timeout: 15000 });

  // Verify we're authenticated by checking for user-specific UI elements
  // This might be a user menu, avatar, or dashboard content
  await page.waitForLoadState("networkidle");

  console.log("   ✓ Authentication successful");

  // Save auth state for reuse
  await page.context().storageState({ path: authFile });
  console.log(`   ✓ Auth state saved to ${authFile}`);
});
