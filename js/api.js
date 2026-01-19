// OmniAI WebUI API Client

let csrfToken = null;

function getCsrfToken() {
    return localStorage.getItem('csrfToken');
}

function setCsrfToken(token) {
    csrfToken = token;
    localStorage.setItem('csrfToken', token);
}

async function apiRequest(endpoint, options = {}) {
    const baseUrl = getApiBaseUrl();
    const url = `${baseUrl}${endpoint}`;

    const headers = {
        'Content-Type': 'application/json',
        'ngrok-skip-browser-warning': 'true', // Skip ngrok free tier interstitial
        ...options.headers,
    };

    // Add CSRF token for state-changing requests (POST/PATCH/DELETE)
    if (['POST', 'PATCH', 'DELETE'].includes((options.method || 'GET').toUpperCase())) {
        const token = getCsrfToken();
        if (token) {
            headers['X-CSRF-Token'] = token;
        }
    }

    try {
        const response = await fetch(url, {
            ...options,
            headers,
            credentials: 'include', // Always include credentials for session cookies
        });

        // Handle CSRF token from response
        const responseCsrfToken = response.headers.get('X-CSRF-Token');
        if (responseCsrfToken) {
            setCsrfToken(responseCsrfToken);
        }

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.message || `HTTP ${response.status}`);
        }

        return await response.json();
    } catch (error) {
        console.error('API request failed:', error);
        throw error;
    }
}

// Auth endpoints
async function login(username, password) {
    const response = await apiRequest('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
    });
    if (response.csrf_token) {
        setCsrfToken(response.csrf_token);
    }
    return response;
}

async function register(inviteCode, username, password) {
    const response = await apiRequest('/auth/register', {
        method: 'POST',
        body: JSON.stringify({ invite_code: inviteCode, username, password }),
    });
    if (response.csrf_token) {
        setCsrfToken(response.csrf_token);
    }
    return response;
}

async function logout() {
    await apiRequest('/auth/logout', { method: 'POST' });
    localStorage.removeItem('csrfToken');
}

async function getMe() {
    return await apiRequest('/auth/me');
}

// Provider endpoints
async function getProviders() {
    return await apiRequest('/providers');
}

async function getProviderModels(providerId) {
    const response = await apiRequest(`/providers/${providerId}/models`);
    // Backend returns {models: [...]} - unwrap and normalize field names
    return (response.models || []).map(m => ({
        id: m.id,
        name: m.label || m.id  // Use label as name, fallback to id
    }));
}

async function getProviderHealth(providerId) {
    return await apiRequest(`/providers/${providerId}/health`);
}

// Conversation endpoints
async function getConversations(query = '') {
    const params = query ? `?q=${encodeURIComponent(query)}` : '';
    return await apiRequest(`/conversations${params}`);
}

async function createConversation(title = '') {
    return await apiRequest('/conversations', {
        method: 'POST',
        body: JSON.stringify({ title }),
    });
}

async function getConversation(conversationId) {
    return await apiRequest(`/conversations/${conversationId}`);
}

async function updateConversation(conversationId, title) {
    return await apiRequest(`/conversations/${conversationId}`, {
        method: 'PATCH',
        body: JSON.stringify({ title }),
    });
}

async function deleteConversation(conversationId) {
    await apiRequest(`/conversations/${conversationId}`, { method: 'DELETE' });
}

async function getConversationMessages(conversationId) {
    return await apiRequest(`/conversations/${conversationId}/messages`);
}

async function createMessage(conversationId, content, providerId, modelId, settings = {}) {
    return await apiRequest(`/conversations/${conversationId}/messages`, {
        method: 'POST',
        body: JSON.stringify({
            content,
            provider_id: providerId,
            model_id: modelId,
            generation_settings: settings,
        }),
    });
}

// Chat endpoints
async function cancelGeneration(generationId) {
    await apiRequest(`/chat/cancel/${generationId}`, { method: 'POST' });
}

async function retryLastMessage(conversationId) {
    return await apiRequest(`/chat/retry`, {
        method: 'POST',
        body: JSON.stringify({ conversation_id: conversationId }),
    });
}