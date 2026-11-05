// Generates types/api.ts from the FastAPI app's OpenAPI schema.
// Run with `pnpm run generate:api-types` after changing a backend schema or route.
// It imports the app without starting it, so it needs backend/app/.env but no services.
import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const frontendDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const backendDir = resolve(frontendDir, "../../backend/app");
const tempDir = mkdtempSync(join(tmpdir(), "openapi-"));
const schemaPath = join(tempDir, "openapi.json");

function run(command, args, cwd) {
  const result = spawnSync(command, args, { cwd, stdio: "inherit", shell: true });
  if (result.status !== 0) process.exit(result.status ?? 1);
}

try {
  // Written to a file, because the app's logging also uses stdout.
  const exportSchema = [
    "import json, sys",
    "from main import app",
    "open(sys.argv[1], 'w', encoding='utf-8').write(json.dumps(app.openapi()))",
  ].join("; ");
  run("uv", ["run", "--no-sync", "python", "-c", `"${exportSchema}"`, `"${schemaPath}"`], backendDir);
  run("pnpm", ["exec", "openapi-typescript", `"${schemaPath}"`, "-o", "types/api.ts"], frontendDir);
} finally {
  rmSync(tempDir, { recursive: true, force: true });
}
