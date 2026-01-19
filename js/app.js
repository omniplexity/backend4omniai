// OmniAI WebUI Main Application Controller

// Defensive DOM helpers - prevent crashes on missing elements
const el = (id) => document.getElementById(id);
const on = (id, evt, fn) => {
    const n = el(id);
    if (n) n.addEventListener(evt, fn);
    else console.warn(`Element with id '${id}' not found, skipping event listener for '${evt}'`);
};

// Centralized State
let state = {
    session: { user: null },
    threads: [],
    activeThreadId: null,
    run: { model: null, temperature: 0.7, top_p: 1, max_tokens: 1024 },
    stream: { status: "idle", elapsedMs: 0, usage: null, lastError: null }
};

// Legacy variables (to be phased out)
let currentConversationId = null;
let currentStreamingParser = null;
let streamingStartTime = null;
let currentGenerationId = null;

// Render Functions
function renderTopbar() {
    const user = state.session.user;
    const userDisplay = document.getElementById('user-display');
    if (user) {
        userDisplay.textContent = user.username;
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

    // Run settings summary
    const summary = `Temp: ${state.run.temperature}, Top-P: ${state.run.top_p}, Max: ${state.run.max_tokens}`;
    document.getElementById('run-settings-summary').textContent = summary;

    // Connection indicator
    const indicator = document.getElementById('connection-indicator');
    indicator.textContent = '● Connected'; // TODO: Update based on actual connection status
}

function renderSidebar() {
    renderConversations(state.threads);
}

function renderChatHeader() {
    const activeThread = state.threads.find(t => t.id === state.activeThreadId);
    const title = activeThread?.title || 'New Chat';
    document.getElementById('chat-title').textContent = title;
}

function renderTranscript(messages) {
    const transcript = document.getElementById('transcript');
    transcript.innerHTML = '';

    messages.forEach(message => {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${message.role}`;
        messageDiv.innerHTML = message.content.replace(/\n/g, '<br>');
        transcript.appendChild(messageDiv);
    });

    scrollToBottomIfNeeded();
}

function renderComposer() {
    // Update send button state
    const providerId = getSelectedProvider();
    const modelId = getSelectedModel();
    const sendBtn = document.getElementById('send-btn');
    sendBtn.disabled = !providerId || !modelId || state.stream.status === 'streaming';

    // Show/hide cancel/retry buttons
    const cancelBtn = document.getElementById('cancel-btn');
    const retryBtn = document.getElementById('retry-btn');

    if (state.stream.status === 'streaming') {
        cancelBtn.classList.remove('hidden');
        retryBtn.classList.add('hidden');
    } else if (state.stream.status === 'error' || state.stream.status === 'cancelled') {
        cancelBtn.classList.add('hidden');
        retryBtn.classList.remove('hidden');
    } else {
        cancelBtn.classList.add('hidden');
        retryBtn.classList.add('hidden');
    }
}

function renderSettingsDrawer() {
    // Sync drawer inputs with state
    document.getElementById('drawer-temperature').value = state.run.temperature;
    document.getElementById('drawer-top-p').value = state.run.top_p;
    document.getElementById('drawer-max-tokens').value = state.run.max_tokens;

    // TODO: Load presets from localStorage
}

function renderToasts() {
    const toastHost = document.getElementById('toastHost');
    toastHost.innerHTML = '';

    if (state.stream.lastError) {
        const toast = document.createElement('div');
        toast.className = 'toast error';
        toast.innerHTML = `
            <div>Error: ${state.stream.lastError.message}</div>
            <button onclick="this.parentElement.remove()">�</button>
        `;
        toastHost.appendChild(toast);
    }
}

function updateStatusLine(text, elapsed = null, usage = null) {
    const statusText = document.getElementById('status-text');
    const elapsedTime = document.getElementById('elapsed-time');
    const tokenUsage = document.getElementById('token-usage');

    statusText.textContent = text;

    if (elapsed !== null) {
        elapsedTime.textContent = `${elapsed.toFixed(1)}s`;
    } else {
        elapsedTime.textContent = '';
    }

    if (usage) {
        const total = usage.prompt_tokens + usage.completion_tokens;
        tokenUsage.textContent = `${total} tokens`;
    } else {
        tokenUsage.textContent = '';
    }
}

// Auto-scroll logic
function scrollToBottomIfNeeded() {
    const transcript = document.getElementById('transcript');
    const isAtBottom = transcript.scrollHeight - transcript.scrollTop - transcript.clientHeight < 100;

    if (isAtBottom) {
        transcript.scrollTop = transcript.scrollHeight;
    } else {
        // Show jump to latest pill if not at bottom and new content arrived
        showJumpToLatest();
    }
}

function showJumpToLatest() {
    let pill = document.getElementById('jump-to-latest');
    if (!pill) {
        pill = document.createElement('button');
        pill.id = 'jump-to-latest';
        pill.textContent = 'Jump to latest';
        pill.className = 'jump-pill';
        pill.onclick = () => {
            document.getElementById('transcript').scrollTop = document.getElementById('transcript').scrollHeight;
            pill.remove();
        };
        document.getElementById('transcript').appendChild(pill);
    }
}

// Incremental transcript updates
function appendToLastMessage(content) {
    const transcript = document.getElementById('transcript');
    const lastMessage = transcript.lastElementChild;
    if (lastMessage && lastMessage.classList.contains('assistant')) {
        lastMessage.innerHTML += content.replace(/\n/g, '<br>');
        scrollToBottomIfNeeded();
    }
}

function finalizeLastMessage() {
    const transcript = document.getElementById('transcript');
    const lastMessage = transcript.lastElementChild;
    if (lastMessage && lastMessage.classList.contains('assistant')) {
        lastMessage.classList.remove('streaming');
    }
}

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
on('save-url-btn', 'click', () => {
    const urlInput = el('api-base-url');
    if (urlInput) {
        const url = urlInput.value.trim();
        if (url) {
            setApiBaseUrl(url);
            alert('API Base URL saved. Please refresh the page.');
        }
    }
});

// Chat initialization
async function initializeChat() {
    try {
        await loadProviders();
        await loadConversations();
        updateSettingsInputs();
        updateSendButtonState();

        // Always ensure we have an active conversation
        let conversationReady = false;

        // Try to restore saved conversation
        const savedConversationId = getCurrentConversationId();
        if (savedConversationId) {
            try {
                await selectConversation(savedConversationId);
                conversationReady = true;
            } catch (error) {
                console.warn('Saved conversation not found, will create new one');
            }
        }

        // If no conversation yet, create one
        if (!conversationReady) {
            console.log('Creating new conversation...');
            await createNewConversation();
        }

        // Final check - ensure we have a conversation
        if (!currentConversationId) {
            console.error('Failed to establish conversation, retrying...');
            await createNewConversation();
        }

        console.log('Chat initialized with conversation:', currentConversationId);
    } catch (error) {
        showError('Failed to initialize chat: ' + error.message);
        // Last resort - try to create a conversation anyway
        try {
            await createNewConversation();
        } catch (e) {
            console.error('Could not create fallback conversation:', e);
        }
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
        // Refresh conversation list to show the new one
        await loadConversations();
        console.log('Created new conversation:', conversation.id);
    } catch (error) {
        showError('Failed to create conversation: ' + error.message);
        throw error; // Re-throw so callers know it failed
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
        throw error; // Re-throw so callers can handle (e.g., create new conversation)
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

async function deleteConversationUI(conversationId) {
    if (confirm('Are you sure you want to delete this conversation?')) {
        try {
            await deleteConversation(conversationId); // Calls API function from api.js
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
    // Clear model selection when provider changes
    setSelectedModel('');
    updateSendButtonState();

    if (providerId) {
        try {
            const models = await getProviderModels(providerId);
            renderModels(models);
            updateSendButtonState();
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
    updateSendButtonState();
});

function updateSendButtonState() {
    const providerId = getSelectedProvider();
    const modelId = getSelectedModel();
    const sendBtn = document.getElementById('send-btn');
    sendBtn.disabled = !providerId || !modelId;
}

// Settings - use correct drawer element IDs with defensive helpers
on('drawer-temperature', 'input', (e) => {
    setTemperature(parseFloat(e.target.value));
});

on('drawer-top-p', 'input', (e) => {
    setTopP(parseFloat(e.target.value));
});

on('drawer-max-tokens', 'input', (e) => {
    const value = e.target.value ? parseInt(e.target.value, 10) : null;
    setMaxTokens(value);
});

// Settings drawer open/close
on('settings-btn', 'click', () => {
    const drawer = el('settingsDrawer');
    if (drawer) drawer.classList.remove('hidden');
});

on('close-settings-btn', 'click', () => {
    const drawer = el('settingsDrawer');
    if (drawer) drawer.classList.add('hidden');
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

        // Add user message to transcript (visual update)
        const transcript = document.getElementById('transcript');
        const userDiv = document.createElement('div');
        userDiv.className = 'message user';
        userDiv.innerHTML = content.replace(/\n/g, '<br>');
        transcript.appendChild(userDiv);

        // First, append the user message to the conversation via API
        await appendMessage(currentConversationId, content);

        // Add empty assistant message placeholder for streaming
        const assistantDiv = document.createElement('div');
        assistantDiv.className = 'message assistant streaming';
        assistantDiv.textContent = '...';
        transcript.appendChild(assistantDiv);
        transcript.scrollTop = transcript.scrollHeight;

        // Start streaming (now the message is in the conversation)
        await startStreaming(providerId, modelId);

    } catch (error) {
        showError('Failed to send message: ' + error.message);
        enableSendButton();
    }
}

async function startStreaming(providerId, modelId) {
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

// Conversation actions
on('rename-chat-btn', 'click', () => {
    if (currentConversationId) {
        const activeThread = state.threads.find(t => t.id === currentConversationId);
        renameConversation(currentConversationId, activeThread?.title);
    }
});

on('delete-chat-btn', 'click', () => {
    if (currentConversationId) {
        deleteConversationUI(currentConversationId);
    }
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

// Global error handlers - surface crashes to the user
window.addEventListener('error', (event) => {
    console.error('Global error:', event.error);
    const errorDisplay = el('error-display');
    if (errorDisplay) {
        errorDisplay.textContent = `JavaScript Error: ${event.error?.message || 'Unknown error'}`;
        errorDisplay.classList.remove('hidden');
    }
});

window.addEventListener('unhandledrejection', (event) => {
    console.error('Unhandled promise rejection:', event.reason);
    const errorDisplay = el('error-display');
    if (errorDisplay) {
        errorDisplay.textContent = `Promise Error: ${event.reason?.message || 'Unknown promise error'}`;
        errorDisplay.classList.remove('hidden');
    }
});

// Initialize app
document.addEventListener('DOMContentLoaded', async () => {
    window.addEventListener('hashchange', handleRouteChange);
    await initializeAuth();
    handleRouteChange();

    // Load saved API URL (defensive access)
    const apiUrlInput = el('api-base-url');
    if (apiUrlInput) apiUrlInput.value = getApiBaseUrl();
});