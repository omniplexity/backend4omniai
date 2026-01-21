// OmniAI WebUI Configuration

const LOCAL_API_BASE_URL = "http://127.0.0.1:8787"; // Local development backend

// Environment detection
function isGitHubPages() {
    return window.location.hostname === 'omniplexity.github.io' ||
           window.location.hostname.endsWith('.github.io');
}

function isLocalhost() {
    return window.location.hostname === 'localhost' ||
           window.location.hostname === '127.0.0.1';
}

function getApiBaseUrl() {
    const stored = localStorage.getItem('apiBaseUrl');
    if (stored) return stored;

    // On GitHub Pages, require explicit backend configuration
    if (isGitHubPages()) {
        return null; // Signal that backend URL needs to be configured
    }

    // Local development default
    return LOCAL_API_BASE_URL;
}

function setApiBaseUrl(url) {
    if (url) {
        localStorage.setItem('apiBaseUrl', url);
    } else {
        localStorage.removeItem('apiBaseUrl');
    }
}

function hasBackendConfigured() {
    return getApiBaseUrl() !== null;
}

function clearBackendConfig() {
    localStorage.removeItem('apiBaseUrl');
}