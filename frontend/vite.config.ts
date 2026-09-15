import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react-swc";
import { docxodusWasmPlugin } from "./tooling/docxodusWasm";
import path from "path";

// Custom plugin to handle asset imports in Playwright tests
const assetPlugin = () => {
  return {
    name: "asset-plugin",
    load(id: string) {
      // Handle image imports by returning a mock URL
      if (id.match(/\.(png|jpe?g|gif|svg|webp)$/)) {
        return `export default "${path.basename(id)}";`;
      }
    },
  };
};

/**
 * Load the Istanbul instrumentation plugin via dynamic import().
 * vite-plugin-istanbul v8 is ESM-only (exports.require is null),
 * so a static top-level import fails when esbuild bundles the config
 * as CJS. Dynamic import() works in both contexts.
 */
async function loadIstanbulPlugins() {
  if (!process.env.COVERAGE) return [];
  const { default: istanbul } = await import("vite-plugin-istanbul");
  return [
    istanbul({
      include: "src/**/*.{ts,tsx}",
      exclude: [
        "node_modules",
        "src/**/*.test.{ts,tsx}",
        "src/setupTests.ts",
        "src/main.tsx",
      ],
      extension: [".ts", ".tsx"],
      // requireEnv is false because loadIstanbulPlugins() is only called when
      // process.env.COVERAGE is truthy (see the guard at the top of this function).
      // Setting requireEnv: true would require VITE_COVERAGE from .env files,
      // which the CI script doesn't set.
      requireEnv: false,
      // Playwright CT runs in build mode (vite build), so instrumentation must
      // be enabled for builds. This is safe because the entire plugin is only
      // loaded when COVERAGE=true (the guard above). Normal `yarn build` is
      // unaffected since COVERAGE is not set in production environments.
      forceBuildInstrument: true,
    }),
  ];
}

// https://vitejs.dev/config/
export default defineConfig(async () => {
  const istanbulPlugins = await loadIstanbulPlugins();
  return {
    base: "/",
    plugins: [
      react(),
      assetPlugin(),
      docxodusWasmPlugin(
        path.join(__dirname, "node_modules/docxodus/dist/wasm")
      ),
      // Instrument source code with Istanbul when collecting Playwright CT coverage
      ...istanbulPlugins,
    ],
    server: {
      // Explicitly bind to 127.0.0.1 (IPv4) so that Playwright's webServer
      // health-check URL (http://127.0.0.1:5173) works reliably in CI.
      // Without this, Vite may bind to ::1 (IPv6 localhost) on modern Linux,
      // causing the Playwright webServer timeout to expire.
      host: "127.0.0.1",
      proxy: {
        // Proxy WebSocket connections to Django backend
        "/ws": {
          target: "ws://localhost:8000",
          ws: true,
          changeOrigin: true,
        },
        // Also proxy GraphQL API calls to Django backend
        "/graphql": {
          target: "http://localhost:8000",
          changeOrigin: true,
        },
        // Proxy other API endpoints if needed
        "/api": {
          target: "http://localhost:8000",
          changeOrigin: true,
        },
      },
    },
    // Add asset handling for Playwright tests
    assetsInclude: [
      "**/*.png",
      "**/*.jpg",
      "**/*.jpeg",
      "**/*.svg",
      "**/*.gif",
      "**/*.webp",
      "**/*.wasm",
    ],
    // Exclude docxodus from dep optimization so import.meta.url resolves to
    // the real node_modules path (needed for WASM file auto-detection).
    optimizeDeps: {
      exclude: ["docxodus"],
      // Vite does not scan an excluded package, so its nested CommonJS
      // dependencies are never pre-bundled and reach the browser as raw CJS
      // ("does not provide an export named 'bind'"), which crashes the whole
      // dev-server app at boot. List them explicitly, as Vite's docs require
      // for excluded ESM packages with CJS dependencies.
      include: ["docxodus > bind-event-listener"],
    },
    // Better handling of assets in all environments
    resolve: {
      alias: {
        // Standard path aliases if needed
        "@": path.resolve(__dirname, "src"),
      },
    },
    // Handle static asset imports better in tests
    define: {
      // Add TEST environment variable that code can check
      // This will be false in production/development
      "import.meta.env.TEST": JSON.stringify(false),
    },
    build: {
      // Ensure proper handling of asset files
      assetsInlineLimit: 4096, // 4kb - files smaller than this will be inlined as base64
      rollupOptions: {
        output: {
          // Ensure proper handling of assets, especially for testing
          assetFileNames: "assets/[name].[ext]",
        },
      },
    },
    test: {
      globals: true,
      environment: "jsdom",
      setupFiles: "./src/setupTests.ts",
      css: true,
      reporters: ["verbose"],
      server: {
        deps: {
          // @os-legal/caml-react uses styled-components template literals in its
          // ESM bundle. Vitest's jsdom environment needs these inlined so the
          // styled-components CJS interop resolves correctly. (vitest 4 removed
          // the top-level `test.deps.inline` option in favour of
          // `test.server.deps.inline`.)
          //
          // docxodus 12.x imports `@atlaskit/pragmatic-drag-and-drop/element/
          // adapter` and friends. That package publishes per-directory
          // `package.json` entry points with no top-level `exports` map, so
          // Node's ESM loader rejects the subpath with
          // ERR_UNSUPPORTED_DIR_IMPORT when vitest externalizes docxodus.
          // Inlining routes docxodus through Vite's resolver, which handles
          // directory entry points, matching what the browser build does.
          inline: ["@os-legal/caml-react", "docxodus"],
        },
      },
      // More specific include pattern
      include: ["src/**/*.test.{ts,tsx}"],
      // Explicitly exclude Playwright directories and node_modules
      exclude: [
        "node_modules",
        "tests",
        "tests-examples",
        "dist",
        ".idea",
        ".git",
        ".cache",
      ],
      alias: {
        "^.+\\.(css|less|scss|sass|png|jpg|jpeg|gif|svg|webp)$": path.resolve(
          __dirname,
          "src/__mocks__/fileMock.ts"
        ),
      },
      coverage: {
        provider: "istanbul",
        reporter: ["text", "json", "html", "lcov"],
        reportsDirectory: "./coverage/unit",
        // Adjust coverage include/exclude if needed, based on the new test patterns
        include: ["src/**/*.{ts,tsx}"], // Keep covering src
        exclude: [
          "src/**/*.test.{ts,tsx}", // Exclude test files themselves
          "src/setupTests.ts", // Exclude setup file
          "src/main.tsx", // Exclude entry point if desired
          // Add any other files/patterns to exclude from coverage
        ],
        // Count every file matched by `include`, not just files imported by a
        // test. Without this, the provider silently drops untested files from
        // the lcov, shrinking the `frontend-unit` denominator and misaligning
        // with the Istanbul-instrumented component/e2e lcovs (which enumerate
        // all source files). Aligning the per-file universe is required for
        // the merged `frontend` lcov to be meaningful.
        all: true,
      },
    },
  };
});
