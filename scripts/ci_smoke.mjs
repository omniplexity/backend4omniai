import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const cfgPath = path.resolve(__dirname, "..", "frontend", "public", "runtime-config.json");

function fail(message) {
  console.error(message);
  process.exit(1);
}

let raw;
try {
  raw = fs.readFileSync(cfgPath, "utf8");
} catch (err) {
  fail(`Missing runtime config at ${cfgPath}`);
}

let cfg;
try {
  cfg = JSON.parse(raw);
} catch (err) {
  fail(`Invalid JSON in runtime config: ${err.message}`);
}

const apiBaseUrl = typeof cfg.apiBaseUrl === "string" ? cfg.apiBaseUrl.trim() : "";
if (!apiBaseUrl) {
  fail("runtime-config.json missing apiBaseUrl");
}

let apiUrl;
try {
  apiUrl = new URL(apiBaseUrl);
} catch (err) {
  fail(`Invalid apiBaseUrl: ${apiBaseUrl}`);
}

if (!/^https?:$/.test(apiUrl.protocol)) {
  fail(`apiBaseUrl must be http(s): ${apiBaseUrl}`);
}

const healthUrl = new URL("/health", apiUrl.toString());
const timeoutMs = Number.parseInt(process.env.OMNIAI_SMOKE_TIMEOUT_MS || "5000", 10);

const controller = new AbortController();
const timeout = setTimeout(() => controller.abort(), timeoutMs);

try {
  const res = await fetch(healthUrl.toString(), {
    cache: "no-store",
    signal: controller.signal,
  });
  if (!res.ok) {
    fail(`Health check failed: HTTP ${res.status}`);
  }
  console.log(`Health check ok: ${healthUrl}`);
} catch (err) {
  fail(`Health check error: ${err.message || err}`);
} finally {
  clearTimeout(timeout);
}
