// OmniAI WebUI Configuration

// Default backend URL - localhost for development, tunnel for production
window.OMNI_API_BASE_URL = "http://localhost:8787";

function getApiBaseUrl() {
    // Check URL query param first (for developers)
    const urlParams = new URLSearchParams(window.location.search);
    const apiParam = urlParams.get('api');
    if (apiParam) {
        return apiParam;
    }

    // Check localStorage override
    const stored = localStorage.getItem('omni_api_base_url');
    if (stored) {
        return stored;
    }

    // Fallback to default
    return window.OMNI_API_BASE_URL;
}

// Optional: Set localStorage override (for developers)
function setApiBaseUrl(url) {
    if (url) {
        localStorage.setItem('omni_api_base_url', url);
    } else {
        localStorage.removeItem('omni_api_base_url');
    }
}