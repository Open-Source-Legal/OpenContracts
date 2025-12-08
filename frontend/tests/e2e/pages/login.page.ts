import { Page, Locator, expect } from "@playwright/test";

/**
 * Page Object for the Login page.
 *
 * Encapsulates login-related interactions and assertions.
 */
export class LoginPage {
  readonly page: Page;
  readonly usernameInput: Locator;
  readonly passwordInput: Locator;
  readonly loginButton: Locator;
  readonly errorMessage: Locator;

  constructor(page: Page) {
    this.page = page;
    this.usernameInput = page
      .locator(
        'input[name="username"], input[name="email"], input[type="email"]'
      )
      .first();
    this.passwordInput = page
      .locator('input[name="password"], input[type="password"]')
      .first();
    this.loginButton = page
      .locator(
        'button[type="submit"], button:has-text("Login"), button:has-text("Sign in")'
      )
      .first();
    this.errorMessage = page
      .locator('[class*="error"], [role="alert"]')
      .first();
  }

  async goto() {
    await this.page.goto("/login");
    await expect(this.usernameInput).toBeVisible({ timeout: 10000 });
  }

  async login(username: string, password: string) {
    await this.usernameInput.fill(username);
    await this.passwordInput.fill(password);
    await this.loginButton.click();
  }

  async expectLoginSuccess() {
    // Should navigate away from login page
    await expect(this.page).not.toHaveURL(/\/login/, { timeout: 15000 });
  }

  async expectLoginError() {
    await expect(this.errorMessage).toBeVisible({ timeout: 5000 });
  }
}
