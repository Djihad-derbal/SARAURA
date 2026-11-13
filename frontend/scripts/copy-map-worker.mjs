// MapLibre runs its tile work in a web worker that must be served as its own file.
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
mkdirSync(resolve(root, "public"), { recursive: true });
copyFileSync(resolve(root, "node_modules/maplibre-gl/dist/maplibre-gl-worker.mjs"), resolve(root, "public/maplibre-gl-worker.mjs"));
