// OmniAI WebUI Local Storage State Management

const STORAGE_KEYS = {
    PROVIDER: 'selectedProvider',
    MODEL: 'selectedModel',
    TEMPERATURE: 'temperature',
    TOP_P: 'topP',
    MAX_TOKENS: 'maxTokens',
    CONVERSATION_ID: 'currentConversationId',
    API_BASE_URL: 'apiBaseUrl',
};

// Provider/Model settings
function getSelectedProvider() {
    return localStorage.getItem(STORAGE_KEYS.PROVIDER) || '';
}

function setSelectedProvider(providerId) {
    localStorage.setItem(STORAGE_KEYS.PROVIDER, providerId);
}

function getSelectedModel() {
    return localStorage.getItem(STORAGE_KEYS.MODEL) || '';
}

function setSelectedModel(modelId) {
    localStorage.setItem(STORAGE_KEYS.MODEL, modelId);
}

// Generation settings
function getTemperature() {
    const stored = localStorage.getItem(STORAGE_KEYS.TEMPERATURE);
    return stored ? parseFloat(stored) : 0.7;
}

function setTemperature(temp) {
    localStorage.setItem(STORAGE_KEYS.TEMPERATURE, temp.toString());
}

function getTopP() {
    const stored = localStorage.getItem(STORAGE_KEYS.TOP_P);
    return stored ? parseFloat(stored) : 1.0;
}

function setTopP(topP) {
    localStorage.setItem(STORAGE_KEYS.TOP_P, topP.toString());
}

function getMaxTokens() {
    const stored = localStorage.getItem(STORAGE_KEYS.MAX_TOKENS);
    return stored ? parseInt(stored, 10) : null;
}

function setMaxTokens(maxTokens) {
    if (maxTokens) {
        localStorage.setItem(STORAGE_KEYS.MAX_TOKENS, maxTokens.toString());
    } else {
        localStorage.removeItem(STORAGE_KEYS.MAX_TOKENS);
    }
}

// Current conversation
function getCurrentConversationId() {
    return localStorage.getItem(STORAGE_KEYS.CONVERSATION_ID) || null;
}

function setCurrentConversationId(conversationId) {
    if (conversationId) {
        localStorage.setItem(STORAGE_KEYS.CONVERSATION_ID, conversationId);
    } else {
        localStorage.removeItem(STORAGE_KEYS.CONVERSATION_ID);
    }
}

// Get all generation settings as object
function getGenerationSettings() {
    return {
        temperature: getTemperature(),
        top_p: getTopP(),
        max_tokens: getMaxTokens(),
    };
}

// Set all generation settings from object
function setGenerationSettings(settings) {
    if (settings.temperature !== undefined) setTemperature(settings.temperature);
    if (settings.top_p !== undefined) setTopP(settings.top_p);
    if (settings.max_tokens !== undefined) setMaxTokens(settings.max_tokens);
}

// API Base URL (delegated to config.js)
function getStoredApiBaseUrl() {
    return localStorage.getItem(STORAGE_KEYS.API_BASE_URL);
}

function setStoredApiBaseUrl(url) {
    if (url) {
        localStorage.setItem(STORAGE_KEYS.API_BASE_URL, url);
    } else {
        localStorage.removeItem(STORAGE_KEYS.API_BASE_URL);
    }
}