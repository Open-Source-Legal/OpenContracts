import fs from "node:fs";
import path from "node:path";
import type { Plugin } from "vite";

const MIME_TYPES: Record<string, string> = {
  ".js": "application/javascript",
  ".wasm": "application/wasm",
  ".json": "application/json",
  ".dat": "application/octet-stream",
};

function isContained(root: string, candidate: string): boolean {
  const relative = path.relative(root, candidate);
  return (
    relative !== ".." &&
    !relative.startsWith(`..${path.sep}`) &&
    !path.isAbsolute(relative)
  );
}

/** Package the runtime for production and serve it safely in development. */
export function docxodusWasmPlugin(assetRoot: string): Plugin {
  const prefix = "/node_modules/docxodus/dist/wasm/";
  return {
    name: "docxodus-wasm-server",
    generateBundle() {
      // Docxodus imports the runtime dynamically, so Vite cannot discover it.
      // Keep its relative file layout intact for the .NET runtime loader.
      const emitDirectory = (directory: string) => {
        for (const entry of fs.readdirSync(directory, {
          withFileTypes: true,
        })) {
          const sourcePath = path.join(directory, entry.name);
          if (entry.isDirectory()) emitDirectory(sourcePath);
          else if (entry.isFile()) {
            const relative = path.relative(assetRoot, sourcePath);
            this.emitFile({
              type: "asset",
              fileName: `docxodus-wasm/${relative.split(path.sep).join("/")}`,
              source: fs.readFileSync(sourcePath),
            });
          }
        }
      };
      emitDirectory(assetRoot);
    },
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const pathname = (req.url || "").split("?")[0];
        if (!pathname.startsWith(prefix)) return next();
        const deny = () => {
          res.writeHead(403);
          res.end();
        };
        try {
          const suffix = decodeURIComponent(pathname.slice(prefix.length));
          const root = fs.realpathSync(assetRoot);
          const candidate = path.resolve(root, suffix);
          if (!isContained(root, candidate)) return deny();
          // Resolve symlinks too: a lexical prefix check alone is insufficient.
          const filePath = fs.realpathSync(candidate);
          if (!isContained(root, filePath)) return deny();
          const mimeType =
            MIME_TYPES[path.extname(filePath)] || "application/octet-stream";
          const data = fs.readFileSync(filePath);
          res.setHeader("Content-Type", mimeType);
          res.end(data);
        } catch (error) {
          if (error instanceof URIError) return deny();
          next();
        }
      });
    },
  };
}
