import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react-swc";
import fs from "fs";
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

// Serve docxodus WASM files from node_modules with correct MIME types.
// Vite's dep optimizer rewrites import.meta.url, breaking auto-detection
// of sibling WASM files. We exclude docxodus from optimization (below)
// so import.meta.url resolves to the real node_modules path, then this
// middleware serves the _framework files that the .NET WASM loader fetches.
const docxodusWasmPlugin = () => {
  const MIME_TYPES: Record<string, string> = {
    ".js": "application/javascript",
    ".wasm": "application/wasm",
    ".json": "application/json",
    ".dat": "application/octet-stream",
  };

  return {
    name: "docxodus-wasm-server",
    configureServer(server: { middlewares: { use: Function } }) {
      server.middlewares.use(
        (
          req: { url?: string },
          res: {
            setHeader: Function;
            writeHead: Function;
            end: Function;
          },
          next: Function
        ) => {
          const url = req.url || "";
          // Match requests for docxodus WASM framework files
          const match = url.match(/\/node_modules\/docxodus\/dist\/wasm\/(.*)/);
          if (!match) return next();

          const filePath = path.join(
            __dirname,
            "node_modules/docxodus/dist/wasm",
            match[1]
          );
          const ext = path.extname(filePath);
          const mimeType = MIME_TYPES[ext] || "application/octet-stream";

          try {
            const data = fs.readFileSync(filePath);
            res.setHeader("Content-Type", mimeType);
            res.setHeader("Access-Control-Allow-Origin", "*");
            res.end(data);
          } catch {
            next();
          }
        }
      );
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
      docxodusWasmPlugin(),
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
      deps: {
        // @os-legal/caml-react uses styled-components template literals in its
        // ESM bundle. Vitest's jsdom environment needs these inlined so the
        // styled-components CJS interop resolves correctly.
        inline: ["@os-legal/caml-react"],
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
        // Use Istanbul (statement-level) instead of v8 (physical-line-level)
        // so this suite measures coverage on the same yardstick as the
        // Playwright component and E2E suites (which use vite-plugin-istanbul
        // + nyc). Without this, the merged `frontend` Codecov flag's
        // denominator was dominated by v8's inclusive line counting (~3x
        // larger per file than Istanbul statement counting), which deflated
        // the badge to ~44% even when the same code paths reported ~60% under
        // the Istanbul-based component flag. Trade-off: Istanbul instruments
        // source ahead of test execution, so unit-test runtime grows somewhat.
        provider: "istanbul",
        reporter: ["text", "json", "html", "lcov"],
        reportsDirectory: "./coverage/unit",
        include: ["src/**/*.{ts,tsx}"],
        exclude: [
          "src/**/*.test.{ts,tsx}",
          "src/setupTests.ts",
          "src/main.tsx",
        ],
        // Enumerate every include-matched file, not just files imported by a
        // test. Required for the per-file universe to match the Istanbul-
        // based component/e2e lcovs so the merged `frontend` flag aggregates
        // cleanly.
        all: true,
      },
    },
  };
});
