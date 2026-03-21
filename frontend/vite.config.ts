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

// https://vitejs.dev/config/
export default defineConfig({
  base: "/",
  plugins: [react(), assetPlugin(), docxodusWasmPlugin()],
  server: {
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
      reporter: ["text", "json", "html"],
      // Adjust coverage include/exclude if needed, based on the new test patterns
      include: ["src/**/*.{ts,tsx}"], // Keep covering src
      exclude: [
        "src/**/*.test.{ts,tsx}", // Exclude test files themselves
        "src/setupTests.ts", // Exclude setup file
        "src/main.tsx", // Exclude entry point if desired
        // Add any other files/patterns to exclude from coverage
      ],
    },
  },
});
