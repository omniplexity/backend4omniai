// OmniAI WebUI Configuration

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8787"; // Local development backend

function getApiBaseUrl() {
    const stored = localStorage.getItem('apiBaseUrl');
    return stored || DEFAULT_API_BASE_URL;
}

function setApiBaseUrl(url) {
    localStorage.setItem('apiBaseUrl', url);
}