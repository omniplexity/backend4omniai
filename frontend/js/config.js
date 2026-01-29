const runtime = {
  data: null,
};

export async function loadConfig() {
  if (runtime.data) {
    return runtime.data;
  }
  const res = await fetch("./runtime-config.json", { cache: "no-store" });
  if (!res.ok) {
    throw new Error("Unable to load runtime config");
  }
  runtime.data = await res.json();
  return runtime.data;
}

export function apiBaseUrl() {
  if (!runtime.data?.API_BASE_URL) {
    throw new Error("API_BASE_URL not configured");
  }
  return runtime.data.API_BASE_URL.replace(/\/+$/, "");
}
