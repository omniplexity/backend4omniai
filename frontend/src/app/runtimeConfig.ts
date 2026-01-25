export type RuntimeConfig = { apiBaseUrl: string; source: "runtime-config" | "fallback" };

function normalizeBase(url: string): string {
  const trimmed = url.trim();
  const parsed = new URL(trimmed);
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new Error("apiBaseUrl must be http(s)");
  }
  return parsed.toString().replace(/\/+$/, "");
}

type RawRuntimeConfig = Partial<{ apiBaseUrl: string }>;

declare global {
  interface Window {
    __RUNTIME_CONFIG__?: RawRuntimeConfig | null;
    __RUNTIME_CONFIG_PROMISE__?: Promise<RawRuntimeConfig | null>;
  }
}

async function resolveRuntimeConfig(): Promise<RawRuntimeConfig | null> {
  if (typeof window !== "undefined") {
    const direct = window.__RUNTIME_CONFIG__;
    if (direct && typeof direct.apiBaseUrl === "string") {
      return direct;
    }
    const promise = window.__RUNTIME_CONFIG_PROMISE__;
    if (promise) {
      try {
        const resolved = await promise;
        if (resolved && typeof resolved.apiBaseUrl === "string") {
          return resolved;
        }
      } catch {
        // fall through to fetch
      }
    }
  }

  let cfgUrl: string;
  if (typeof document !== "undefined") {
    const moduleScript = document.querySelector("script[type=\"module\"][src]") as HTMLScriptElement | null;
    const moduleSrc = moduleScript?.src;
    if (moduleSrc) {
      const base = new URL(".", moduleSrc);
      cfgUrl = new URL("../runtime-config.json", base).toString();
    } else {
      const baseUrl = import.meta.env.BASE_URL ?? "/";
      const baseWithSlash = baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`;
      cfgUrl = `${baseWithSlash}runtime-config.json`;
    }
  } else {
    const baseUrl = import.meta.env.BASE_URL ?? "/";
    const baseWithSlash = baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`;
    cfgUrl = `${baseWithSlash}runtime-config.json`;
  }
  cfgUrl = `${cfgUrl}?v=${Date.now()}`;

  try {
    const res = await fetch(cfgUrl, { cache: "no-store" });
    if (!res.ok) {
      return null;
    }
    return (await res.json()) as RawRuntimeConfig;
  } catch {
    return null;
  }
}

export async function loadRuntimeConfig(): Promise<RuntimeConfig> {
  const resolved = await resolveRuntimeConfig();
  if (resolved?.apiBaseUrl) {
    return { apiBaseUrl: normalizeBase(resolved.apiBaseUrl), source: "runtime-config" };
  }

  return { apiBaseUrl: window.location.origin, source: "fallback" };
}
