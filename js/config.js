// OmniAI WebUI Configuration

const DEFAULT_API_BASE_URL = "https://your-tunnel-or-domain"; // Replace with actual tunnel URL

function getApiBaseUrl() {
    const stored = localStorage.getItem('apiBaseUrl');
    return stored || DEFAULT_API_BASE_URL;
}

function setApiBaseUrl(url) {
    localStorage.setItem('apiBaseUrl', url);
}