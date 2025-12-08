import { FullConfig } from "@playwright/test";

/**
 * Global teardown for E2E integration tests.
 *
 * This runs once after all tests to:
 * 1. Clean up test data created during tests
 * 2. Report summary statistics
 */
async function globalTeardown(config: FullConfig) {
  console.log("\n🧹 E2E Integration Test Teardown");

  // For now, we don't automatically clean up test data
  // as it can be useful for debugging failed tests.
  // Add cleanup logic here if needed in the future.

  console.log("   ✓ Teardown complete\n");
}

export default globalTeardown;
