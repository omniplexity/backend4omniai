// OmniAI WebUI Configuration

const DEFAULT_API_BASE_URL = "https://rossie-chargeful-plentifully.ngrok-free.dev"; // ngrok tunnel URL

function getApiBaseUrl() {
    const stored = localStorage.getItem('apiBaseUrl');
    return stored || DEFAULT_API_BASE_URL;
}

function setApiBaseUrl(url) {
    localStorage.setItem('apiBaseUrl', url);
}