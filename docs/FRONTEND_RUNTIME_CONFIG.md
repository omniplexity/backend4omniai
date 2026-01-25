# Frontend Runtime Config

OmniAI loads a runtime config file at startup to avoid rebuilding the frontend when the API hostname changes.

## Why this exists

GitHub Pages is static-only. The browser must call the public API hostname directly, so the base URL needs to be configurable without rebuilding the JavaScript bundle.

## File location

- Source: `frontend/public/runtime-config.json`
- Built output: `frontend/dist/runtime-config.json`

Vite copies `public/*` into `dist/*` unchanged.

## Editing for GitHub Pages

Update `runtime-config.json` in the repo to the desired API hostname and redeploy the static site:

```json
{
  "apiBaseUrl": "http://localhost:8787"
}
```

The runtime config is loaded before the app boots and exposed via `window.__RUNTIME_CONFIG__`.
The loader resolves `runtime-config.json` relative to the built JS bundle location, so deep links do not break.
If the file is missing, the app falls back to same-origin (useful when co-hosting frontend + backend).

## BASE_URL and GitHub Pages paths

The loader fetches:

```
${import.meta.env.BASE_URL}runtime-config.json
```

This works for both:
- User site: `/` (e.g. `https://omniplexity.github.io/`)
- Project site: `/repo/` (e.g. `https://omniplexity.github.io/omni/`)

## Troubleshooting

- **404 runtime-config.json**: check that the file exists in `frontend/public/` and that the correct BASE_URL is used on GitHub Pages.
- **Wrong apiBaseUrl**: update the JSON and redeploy. Confirm CORS allows `https://omniplexity.github.io`.
- **Mixed content**: when the site is HTTPS, `apiBaseUrl` must be HTTPS.
