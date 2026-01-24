// OmniAI WebUI Configuration

const LOCAL_API_BASE_URL = "http://127.0.0.1:8787"; // Local development backend
const DEFAULT_REMOTE_API_URL = ""; // Optional: set to your tunnel URL

// Environment detection
function isGitHubPages() {
    return window.location.hostname === 'omniplexity.github.io' ||
           window.location.hostname.endsWith('.github.io');
}

function isLocalhost() {
    return window.location.hostname === 'localhost' ||
           window.location.hostname === '127.0.0.1';
}

function normalizeApiBaseUrl(url) {
    if (!url) return null;
    return url.replace(/\/+$/, '');
}

function isFrontendOrigin(url) {
    try {
        const origin = new URL(url, window.location.origin).origin;
        return origin === window.location.origin;
    } catch {
        return false;
    }
}

function getStoredApiBaseUrl() {
    const stored = normalizeApiBaseUrl(localStorage.getItem('apiBaseUrl'));
    if (!stored) return null;
    if (isGitHubPages() && isFrontendOrigin(stored)) return null;
    return stored;
}

function getDefaultApiBaseUrl() {
    if (isLocalhost()) {
        return normalizeApiBaseUrl(LOCAL_API_BASE_URL);
    }

    const remote = normalizeApiBaseUrl(DEFAULT_REMOTE_API_URL);
    if (remote) return remote;

    return null;
}

function getApiBaseUrl() {
    return getStoredApiBaseUrl() || getDefaultApiBaseUrl();
}

function setApiBaseUrl(url) {
    const normalized = normalizeApiBaseUrl(url);
    if (normalized) {
        localStorage.setItem('apiBaseUrl', normalized);
    } else {
        localStorage.removeItem('apiBaseUrl');
    }
}

function hasBackendConfigured() {
    return Boolean(getApiBaseUrl());
}

function clearBackendConfig() {
    localStorage.removeItem('apiBaseUrl');
}
