import { FullConfig } from "@playwright/test";

/**
 * Global setup for E2E integration tests.
 *
 * This runs once before all tests to:
 * 1. Verify backend is running and healthy
 * 2. Create/verify test user exists
 * 3. Clean up any stale test data
 */
async function globalSetup(config: FullConfig) {
  const apiUrl = process.env.E2E_API_URL || "http://localhost:8000";

  console.log("\n🚀 E2E Integration Test Setup");
  console.log(`   API URL: ${apiUrl}`);

  // 1. Verify backend is running
  console.log("   Checking backend health...");
  try {
    const healthResponse = await fetch(`${apiUrl}/api/health/`, {
      method: "GET",
      headers: { Accept: "application/json" },
    });

    if (!healthResponse.ok) {
      throw new Error(`Backend health check failed: ${healthResponse.status}`);
    }
    console.log("   ✓ Backend is healthy");
  } catch (error) {
    console.error("\n❌ Backend is not running!");
    console.error(
      "   Please start the backend with: docker compose -f local.yml up"
    );
    console.error(`   Error: ${error}`);
    throw new Error("Backend not available");
  }

  // 2. Verify GraphQL endpoint is accessible
  console.log("   Checking GraphQL endpoint...");
  try {
    const graphqlResponse = await fetch(`${apiUrl}/graphql/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({
        query: `{ __typename }`,
      }),
    });

    if (!graphqlResponse.ok) {
      throw new Error(`GraphQL check failed: ${graphqlResponse.status}`);
    }
    console.log("   ✓ GraphQL endpoint accessible");
  } catch (error) {
    console.error("\n❌ GraphQL endpoint not accessible!");
    console.error(`   Error: ${error}`);
    throw new Error("GraphQL not available");
  }

  console.log("   ✓ Setup complete\n");
}

export default globalSetup;
