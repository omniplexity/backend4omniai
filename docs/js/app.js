// OmniAI WebUI Main Application Controller

let currentConversationId = null;
let currentStreamingParser = null;
let streamingStartTime = null;
let currentGenerationId = null;

// Routing
function getRoute() {
    const hash = window.location.hash.slice(1);
    return hash || 'login';
}

function setRoute(route) {
    window.location.hash = route;
}

function handleRouteChange() {
    const route = getRoute();
    const user = getCurrentUser();

    if (!user && route !== 'register') {
        showView('login-view');
        return;
    }

    // Check admin access for admin routes
    if (route === 'admin' && (!user || user.role !== 'admin')) {
        setRoute('chat');
        return;
    }

    switch (route) {
        case 'login':
            showView('login-view');
            break;
        case 'register':
            showView('register-view');
            break;
        case 'admin':
            if (user && user.role === 'admin') {
                showView('admin-view');
                initializeAdmin();
            } else {
                setRoute('chat');
            }
            break;
        case 'chat':
            if (user) {
                showView('chat-view');
                initializeChat();
            } else {
                setRoute('login');
            }
            break;
        default:
            setRoute('chat');
    }
}

// Authentication
async function initializeAuth() {
    const user = getCurrentUser();
    updateUserDisplay(user);

    if (user) {
        setRoute('chat');
    } else {
        setRoute('login');
    }
}

function updateUserDisplay(user) {
    const userDisplay = document.getElementById('user-display');
    if (user) {
        userDisplay.textContent = user.username;
        // Show admin link if user is admin
        const adminLink = document.getElementById('admin-link');
        if (user.role === 'admin') {
            adminLink.classList.remove('hidden');
        } else {
            adminLink.classList.add('hidden');
        }
    } else {
        userDisplay.textContent = '';
        document.getElementById('admin-link').classList.add('hidden');
    }
}

document.getElementById('login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;

    try {
        await handleLogin(username, password);
        updateUserDisplay(getCurrentUser());
        setRoute('chat');
    } catch (error) {
        document.getElementById('login-error').textContent = error.message;
        document.getElementById('login-error').classList.remove('hidden');
    }
});

document.getElementById('register-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const inviteCode = document.getElementById('invite-code').value;
    const username = document.getElementById('reg-username').value;
    const password = document.getElementById('reg-password').value;

    try {
        await handleRegister(inviteCode, username, password);
        updateUserDisplay(getCurrentUser());
        setRoute('chat');
    } catch (error) {
        document.getElementById('register-error').textContent = error.message;
        document.getElementById('register-error').classList.remove('hidden');
    }
});

document.getElementById('show-register').addEventListener('click', (e) => {
    e.preventDefault();
    setRoute('register');
});

document.getElementById('show-login').addEventListener('click', (e) => {
    e.preventDefault();
    setRoute('login');
});

document.getElementById('logout-btn').addEventListener('click', async () => {
    await handleLogout();
    setRoute('login');
});

// Backend URL setting
document.getElementById('save-url-btn').addEventListener('click', () => {
    const url = document.getElementById('api-base-url').value.trim();
    if (url) {
        setApiBaseUrl(url);
        alert('API Base URL saved. Please refresh the page.');
    }
});

// Chat initialization
async function initializeChat() {
    try {
        await loadProviders();
        await loadConversations();
        updateSettingsInputs();

        const savedConversationId = getCurrentConversationId();
        if (savedConversationId) {
            await selectConversation(savedConversationId);
        } else {
            await createNewConversation();
        }
    } catch (error) {
        showError('Failed to initialize chat: ' + error.message);
    }
}

// Admin initialization
async function initializeAdmin() {
    try {
        await loadAdminData();
    } catch (error) {
        showError('Failed to initialize admin panel: ' + error.message);
    }
}

async function loadProviders() {
    try {
        const providers = await getProviders();
        renderProviders(providers);
    } catch (error) {
        console.error('Failed to load providers:', error);
    }
}

async function loadConversations(query = '') {
    try {
        const conversations = await getConversations(query);
        renderConversations(conversations);
    } catch (error) {
        console.error('Failed to load conversations:', error);
    }
}

// Conversation management
async function createNewConversation() {
    try {
        const conversation = await createConversation();
        setCurrentConversationId(conversation.id);
        currentConversationId = conversation.id;
        renderTranscript([]);
        updateStatusLine('Ready');
    } catch (error) {
        showError('Failed to create conversation: ' + error.message);
    }
}

async function selectConversation(conversationId) {
    try {
        const messages = await getConversationMessages(conversationId);
        currentConversationId = conversationId;
        setCurrentConversationId(conversationId);
        renderTranscript(messages);
        updateStatusLine('Ready');
    } catch (error) {
        showError('Failed to load conversation: ' + error.message);
    }
}

async function renameConversation(conversationId, currentTitle) {
    const newTitle = prompt('Enter new title:', currentTitle || '');
    if (newTitle !== null && newTitle.trim() !== '') {
        try {
            await updateConversation(conversationId, newTitle.trim());
            await loadConversations();
        } catch (error) {
            showError('Failed to rename conversation: ' + error.message);
        }
    }
}

async function deleteConversation(conversationId) {
    if (confirm('Are you sure you want to delete this conversation?')) {
        try {
            await deleteConversation(conversationId);
            if (currentConversationId === conversationId) {
                await createNewConversation();
            }
            await loadConversations();
        } catch (error) {
            showError('Failed to delete conversation: ' + error.message);
        }
    }
}

// Provider/Model handling
document.getElementById('provider-select').addEventListener('change', async (e) => {
    const providerId = e.target.value;
    setSelectedProvider(providerId);

    if (providerId) {
        try {
            const models = await getProviderModels(providerId);
            renderModels(models);
        } catch (error) {
            showError('Failed to load models: ' + error.message);
            renderModels([]);
        }
    } else {
        renderModels([]);
    }
});

document.getElementById('model-select').addEventListener('change', (e) => {
    setSelectedModel(e.target.value);
});

// Settings
document.getElementById('temperature').addEventListener('input', (e) => {
    setTemperature(parseFloat(e.target.value));
});

document.getElementById('top-p').addEventListener('input', (e) => {
    setTopP(parseFloat(e.target.value));
});

document.getElementById('max-tokens').addEventListener('input', (e) => {
    const value = e.target.value ? parseInt(e.target.value, 10) : null;
    setMaxTokens(value);
});

// Message sending
document.getElementById('send-btn').addEventListener('click', sendMessage);
document.getElementById('message-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    } else if (e.key === 'Escape') {
        cancelStreaming();
    }
});

async function sendMessage() {
    if (!currentConversationId) return;

    const messageInput = document.getElementById('message-input');
    const content = messageInput.value.trim();
    if (!content) return;

    const providerId = getSelectedProvider();
    const modelId = getSelectedModel();

    if (!providerId || !modelId) {
        showError('Please select a provider and model first.');
        return;
    }

    try {
        disableSendButton();
        clearMessageInput();

        // Create user message
        const userMessage = { role: 'user', content };
        renderTranscript([...document.querySelectorAll('.message')].map(el => ({
            role: el.classList.contains('user') ? 'user' : 'assistant',
            content: el.innerHTML.replace(/<br>/g, '\n')
        })).concat(userMessage));

        // Start streaming
        await startStreaming(content, providerId, modelId);

    } catch (error) {
        showError('Failed to send message: ' + error.message);
        enableSendButton();
    }
}

async function startStreaming(content, providerId, modelId) {
    if (currentStreamingParser) {
        currentStreamingParser.stop();
    }

    const settings = getGenerationSettings();
    streamingStartTime = Date.now();
    updateStatusLine('Streaming...');

    try {
        currentStreamingParser = await streamChat(
            currentConversationId,
            providerId,
            modelId,
            settings,
            handleStreamEvent,
            handleStreamError,
            handleStreamDisconnect
        );
        showCancelButton();
    } catch (error) {
        handleStreamError(error);
    }
}

function handleStreamEvent(event) {
    switch (event.type) {
        case 'delta':
            appendToLastMessage(event.content);
            break;
        case 'usage':
            updateStatusLine('Streaming...', null, event.usage);
            break;
        case 'done':
            finalizeStreaming();
            break;
        case 'generation_id':
            currentGenerationId = event.generation_id;
            break;
        default:
            console.warn('Unknown stream event:', event);
    }
}

function handleStreamError(error) {
    console.error('Stream error:', error);
    showError('Streaming error: ' + error.message);
    finalizeStreaming();
}

function handleStreamDisconnect() {
    showDisconnectBanner();
    finalizeStreaming();
}

function finalizeStreaming() {
    if (currentStreamingParser) {
        currentStreamingParser.stop();
        currentStreamingParser = null;
    }

    finalizeLastMessage();
    const elapsed = streamingStartTime ? (Date.now() - streamingStartTime) / 1000 : null;
    updateStatusLine('Ready', elapsed);
    enableSendButton();
    showRetryButton();
    currentGenerationId = null;
    streamingStartTime = null;
    hideDisconnectBanner();
}

function cancelStreaming() {
    if (currentStreamingParser && currentGenerationId) {
        cancelGeneration(currentGenerationId).catch(error => {
            console.warn('Failed to cancel generation:', error);
        });
        currentStreamingParser.stop();
        finalizeStreaming();
        updateStatusLine('Canceled');
        showRetryButton();
    }
}

document.getElementById('cancel-btn').addEventListener('click', cancelStreaming);

document.getElementById('retry-btn').addEventListener('click', async () => {
    if (!currentConversationId) return;

    try {
        await retryLastMessage(currentConversationId);
        // Refresh conversation to get updated messages
        await selectConversation(currentConversationId);
    } catch (error) {
        showError('Failed to retry: ' + error.message);
    }
});

// Other UI
document.getElementById('new-conversation-btn').addEventListener('click', createNewConversation);

document.getElementById('search-conversations').addEventListener('input', (e) => {
    loadConversations(e.target.value);
});

document.getElementById('dismiss-error').addEventListener('click', hideError);

document.getElementById('retry-stream').addEventListener('click', () => {
    hideDisconnectBanner();
    // Retry would need to be implemented based on last message
});

// Diagnostics
document.getElementById('test-me').addEventListener('click', async () => {
    try {
        const result = await getMe();
        document.getElementById('diag-results').textContent = JSON.stringify(result, null, 2);
    } catch (error) {
        document.getElementById('diag-results').textContent = 'Error: ' + error.message;
    }
});

document.getElementById('test-providers').addEventListener('click', async () => {
    try {
        const result = await getProviders();
        document.getElementById('diag-results').textContent = JSON.stringify(result, null, 2);
    } catch (error) {
        document.getElementById('diag-results').textContent = 'Error: ' + error.message;
    }
});

// Initialize app
document.addEventListener('DOMContentLoaded', async () => {
    window.addEventListener('hashchange', handleRouteChange);
    await initializeAuth();
    handleRouteChange();

    // Load saved API URL
    document.getElementById('api-base-url').value = getApiBaseUrl();
});