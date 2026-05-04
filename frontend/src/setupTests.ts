// jest-dom adds custom jest matchers for asserting on DOM nodes.
// allows you to do things like:
// expect(element).toHaveTextContent(/react/i)
// learn more: https://github.com/testing-library/jest-dom
import "@testing-library/jest-dom";

// React 18 requires this flag so it knows the environment supports
// act(...). Without it, our React-18-native renderHook helper
// (`src/test-utils/renderHook.tsx`) emits a "current testing environment
// is not configured to support act(...)" warning.
(
  globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;
// import { vi } from "vitest";

// Mock static assets for tests - this will be handled by moduleNameMapper in vitest.config.ts
// vi.mock(/\.(css|less|scss|sass|png|jpg|jpeg|gif|svg|webp)$/i, () => {
//   // Return an object with a default export, simulating the asset import
//   // You can customize the mock value if needed (e.g., return an empty object or specific string)
//   return { default: "mock-asset" };
// });
