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
    run: { model: null, temperature: null, top_p: null, max_tokens: null }, // null means use provider defaults
    stream: { status: "idle", elapsedMs: 0, usage: null, lastError: null }
};

// Debug logging (enabled via ?debug=1)
const DEBUG = new URLSearchParams(window.location.search).has('debug');
function debugLog(type, data = {}) {
    if (DEBUG) {
        console.log(`[${new Date().toISOString()}] ${type}`, data);
    }
}

// Global logger for other modules
window.__omniDebugLog = debugLog;

// Get generation settings (only non-null values)
function getGenerationSettings() {
    const settings = {};
    if (state.run.temperature !== null) settings.temperature = state.run.temperature;
    if (state.run.top_p !== null) settings.top_p = state.run.top_p;
    if (state.run.max_tokens !== null) settings.max_tokens = state.run.max_tokens;
    return settings;
}

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
    let summary;
    if (state.run.temperature === null && state.run.top_p === null && state.run.max_tokens === null) {
        summary = 'Using provider defaults';
    } else {
        summary = `Temp: ${state.run.temperature ?? 'default'}, Top-P: ${state.run.top_p ?? 'default'}, Max: ${state.run.max_tokens ?? 'default'}`;
    }
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
    // Use the renderTranscript from render.js
    window.renderTranscript(messages);

    // Show/hide welcome panel based on messages
    const welcomePanel = document.getElementById('welcome-panel');
    if (welcomePanel) {
        if (messages.length === 0) {
            welcomePanel.classList.remove('hidden');
        } else {
            welcomePanel.classList.add('hidden');
        }
    }

    scrollToBottomIfNeeded();
}

function renderComposer() {
    // Update send button state
    const providerId = getSelectedProvider();
    const modelId = getSelectedModel();
    const sendBtn = document.getElementById('send-btn');
    sendBtn.disabled = !providerId || !modelId || !currentConversationId || state.stream.status === 'streaming';

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

// Settings drawer rendering is now handled by loadSettingsUI()

function renderToasts() {
    const toastHost = document.getElementById('toastHost');
    toastHost.innerHTML = '';

    if (state.stream.lastError) {
        const toast = document.createElement('div');
        toast.className = 'toast error';
        toast.innerHTML = `
            <div>Error: ${state.stream.lastError.message}</div>
            <button onclick="this.parentElement.remove()">×</button>
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
            pill.classList.remove('visible');
        };
        document.body.appendChild(pill);
    } else {
        pill.classList.add('visible');
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
    try {
        const user = await checkAuth();
        updateUserDisplay(user);

        if (user) {
            setRoute('chat');
        } else {
            setRoute('login');
        }
    } catch (error) {
        console.warn('Auth check failed:', error);
        updateUserDisplay(null);
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

// Backend URL setting removed from UI

// Chat initialization
async function initializeChat() {
    try {
        await loadProviders();
        await loadConversations();
        updateSendButtonState();

        // Always ensure we have an active conversation
        let conversationReady = false;

        // Try to restore saved conversation
        const savedConversationId = getCurrentConversationId();
        if (savedConversationId) {
            try {
                // Don't show error on fail - we'll create a new conversation instead
                await selectConversation(savedConversationId, false);
                conversationReady = true;
            } catch (error) {
                // Clear stale conversation ID and create new one
                console.warn('Saved conversation not found, clearing and creating new one');
                setCurrentConversationId(null);
                currentConversationId = null;
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
            setCurrentConversationId(null);
            currentConversationId = null;
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
        // Auto-select provider if none selected
        autoSelectProvider(providers);
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
        state.activeThreadId = conversation.id;
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

async function selectConversation(conversationId, showErrorOnFail = true) {
    try {
        const messages = await getConversationMessages(conversationId);
        currentConversationId = conversationId;
        setCurrentConversationId(conversationId);
        state.activeThreadId = conversationId;
        renderTranscript(messages);
        updateStatusLine('Ready');
    } catch (error) {
        if (showErrorOnFail) {
            showError('Failed to load conversation: ' + error.message);
        }
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
on('provider-select', 'change', async (e) => {
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

on('model-select', 'change', (e) => {
    setSelectedModel(e.target.value);
    updateSendButtonState();
});

function updateSendButtonState() {
    const providerId = getSelectedProvider();
    const modelId = getSelectedModel();
    const sendBtn = el('send-btn');
    if (sendBtn) sendBtn.disabled = !providerId || !modelId || state.stream.status === 'streaming';
}

function autoSelectProvider(providers) {
    let selectedProvider = getSelectedProvider();
    if (!selectedProvider) {
        // Prefer LM Studio if available
        const lmStudio = providers.find(p => p.name.toLowerCase().includes('lm studio') || p.provider_id.toLowerCase().includes('lmstudio'));
        if (lmStudio) {
            selectedProvider = lmStudio.provider_id;
        } else if (providers.length > 0) {
            selectedProvider = providers[0].provider_id;
        }
        if (selectedProvider) {
            setSelectedProvider(selectedProvider);
            const select = el('provider-select');
            if (select) select.value = selectedProvider;
            // Trigger change to load models
            select.dispatchEvent(new Event('change'));
        }
    }
}

// Settings drawer open/close
on('settings-btn', 'click', () => {
    const drawer = el('settingsDrawer');
    if (drawer) {
        drawer.classList.remove('hidden');
        loadSettingsUI();
    }
});

on('close-settings-btn', 'click', () => {
    const drawer = el('settingsDrawer');
    if (drawer) drawer.classList.add('hidden');
});

// Load current settings into UI
function loadSettingsUI() {
    // Appearance
    const themeEl = el('setting-theme');
    const fontSizeEl = el('setting-font-size');
    const layoutEl = el('setting-layout');
    if (themeEl) themeEl.value = getSetting('theme');
    if (fontSizeEl) fontSizeEl.value = getSetting('fontSize');
    if (layoutEl) layoutEl.value = getSetting('layout');

    // Chat Behavior
    const autoScrollEl = el('setting-auto-scroll');
    const enterSendEl = el('setting-enter-send');
    const timestampsEl = el('setting-timestamps');
    const streamEl = el('setting-stream-response');
    if (autoScrollEl) autoScrollEl.checked = getSetting('autoScroll');
    if (enterSendEl) enterSendEl.checked = getSetting('enterToSend');
    if (timestampsEl) timestampsEl.checked = getSetting('showTimestamps');
    if (streamEl) streamEl.checked = getSetting('streamResponse');

    // Generation Settings
    const temperatureEl = el('setting-temperature');
    const topPEl = el('setting-top-p');
    const maxTokensEl = el('setting-max-tokens');
    if (temperatureEl) temperatureEl.value = state.run.temperature ?? '';
    if (topPEl) topPEl.value = state.run.top_p ?? '';
    if (maxTokensEl) maxTokensEl.value = state.run.max_tokens ?? '';

    // Provider Defaults
    const rememberProviderEl = el('setting-remember-provider');
    const rememberModelEl = el('setting-remember-model');
    if (rememberProviderEl) rememberProviderEl.checked = getSetting('rememberProvider');
    if (rememberModelEl) rememberModelEl.checked = getSetting('rememberModel');
}

// Settings change handlers - Appearance
on('setting-theme', 'change', (e) => setSetting('theme', e.target.value));
on('setting-font-size', 'change', (e) => setSetting('fontSize', e.target.value));
on('setting-layout', 'change', (e) => setSetting('layout', e.target.value));

// Settings change handlers - Chat Behavior
on('setting-auto-scroll', 'change', (e) => setSetting('autoScroll', e.target.checked));
on('setting-enter-send', 'change', (e) => setSetting('enterToSend', e.target.checked));
on('setting-timestamps', 'change', (e) => setSetting('showTimestamps', e.target.checked));
on('setting-stream-response', 'change', (e) => setSetting('streamResponse', e.target.checked));

// Settings change handlers - Generation Settings
on('setting-temperature', 'input', (e) => {
    const val = e.target.value.trim();
    state.run.temperature = val === '' ? null : parseFloat(val);
    renderTopbar();
});
on('setting-top-p', 'input', (e) => {
    const val = e.target.value.trim();
    state.run.top_p = val === '' ? null : parseFloat(val);
    renderTopbar();
});
on('setting-max-tokens', 'input', (e) => {
    const val = e.target.value.trim();
    state.run.max_tokens = val === '' ? null : parseInt(val, 10);
    renderTopbar();
});

// Settings change handlers - Provider Defaults
on('setting-remember-provider', 'change', (e) => setSetting('rememberProvider', e.target.checked));
on('setting-remember-model', 'change', (e) => setSetting('rememberModel', e.target.checked));

// Reset generation settings
on('reset-generation-settings-btn', 'click', () => {
    state.run.temperature = null;
    state.run.top_p = null;
    state.run.max_tokens = null;
    loadSettingsUI(); // Reload UI to reflect changes
    renderTopbar();
});

// Data actions
on('clear-history-btn', 'click', async () => {
    if (confirm('Are you sure you want to clear all conversation history? This cannot be undone.')) {
        // TODO: Implement clear history via API
        showError('Clear history not yet implemented');
    }
});

on('export-data-btn', 'click', () => {
    // Export settings and conversation data as JSON
    const data = {
        settings: getAllSettings(),
        exportedAt: new Date().toISOString(),
    };
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `omniai-settings-${new Date().toISOString().split('T')[0]}.json`;
    a.click();
    URL.revokeObjectURL(url);
});

// Message sending
on('send-btn', 'click', () => {
    debugLog('SEND_CLICK');
    sendMessage().catch(error => {
        debugLog('SEND_ERROR', { error: error.message });
        console.error('Send error:', error);
    });
});
on('message-input', 'keydown', (e) => {
    // Respect enterToSend setting
    if (e.key === 'Enter' && !e.shiftKey && getSetting('enterToSend')) {
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

    streamingStartTime = Date.now();
    updateStatusLine('Streaming...');

    try {
        // Model tuning is handled by LM Studio - we just specify provider/model
        currentStreamingParser = await streamChat(
            currentConversationId,
            providerId,
            modelId,
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

on('cancel-btn', 'click', cancelStreaming);

on('retry-btn', 'click', async () => {
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
on('sidebar-toggle', 'click', () => {
    const sidebar = document.getElementById('sidebar');
    sidebar.classList.toggle('open');
});

on('new-conversation-btn', 'click', () => {
    debugLog('NEW_CHAT_CLICK');
    createNewConversation().catch(error => {
        debugLog('NEW_CHAT_ERROR', { error: error.message });
        console.error('New chat error:', error);
    });
});

on('search-conversations', 'input', (e) => {
    loadConversations(e.target.value);
});

// Welcome panel suggestion chips
document.addEventListener('click', (e) => {
    if (e.target.classList.contains('suggestion-chip')) {
        const message = e.target.textContent;
        const input = document.getElementById('message-input');
        if (input) {
            input.value = message;
            input.focus();
            // Hide welcome panel
            const welcomePanel = document.getElementById('welcome-panel');
            if (welcomePanel) welcomePanel.classList.add('hidden');
        }
    }
});

on('dismiss-error', 'click', hideError);

on('retry-stream', 'click', () => {
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
on('test-me', 'click', async () => {
    try {
        const result = await getMe();
        const diagEl = el('diag-results');
        if (diagEl) diagEl.textContent = JSON.stringify(result, null, 2);
    } catch (error) {
        const diagEl = el('diag-results');
        if (diagEl) diagEl.textContent = 'Error: ' + error.message;
    }
});

on('test-providers', 'click', async () => {
    try {
        const result = await getProviders();
        const diagEl = el('diag-results');
        if (diagEl) diagEl.textContent = JSON.stringify(result, null, 2);
    } catch (error) {
        const diagEl = el('diag-results');
        if (diagEl) diagEl.textContent = 'Error: ' + error.message;
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

// Single-init guard for UI bindings
function bindUI() {
    if (window.__omniBound) return;
    window.__omniBound = true;

    // Authentication
    on('login-form', 'submit', async (e) => {
        e.preventDefault();
        const username = el('username')?.value;
        const password = el('password')?.value;

        try {
            await handleLogin(username, password);
            updateUserDisplay(getCurrentUser());
            setRoute('chat');
        } catch (error) {
            const errorEl = el('login-error');
            if (errorEl) {
                errorEl.textContent = error.message;
                errorEl.classList.remove('hidden');
            }
        }
    });

    on('register-form', 'submit', async (e) => {
        e.preventDefault();
        const inviteCode = el('invite-code')?.value;
        const username = el('reg-username')?.value;
        const password = el('reg-password')?.value;

        try {
            await handleRegister(inviteCode, username, password);
            updateUserDisplay(getCurrentUser());
            setRoute('chat');
        } catch (error) {
            const errorEl = el('register-error');
            if (errorEl) {
                errorEl.textContent = error.message;
                errorEl.classList.remove('hidden');
            }
        }
    });

    on('show-register', 'click', (e) => {
        e.preventDefault();
        setRoute('register');
    });

    on('show-login', 'click', (e) => {
        e.preventDefault();
        setRoute('login');
    });

    on('logout-btn', 'click', async () => {
        await handleLogout();
        setRoute('login');
    });

    // Provider/Model handling
    on('provider-select', 'change', async (e) => {
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

    on('model-select', 'change', (e) => {
        setSelectedModel(e.target.value);
        updateSendButtonState();
    });

    // Settings drawer open/close
    on('settings-btn', 'click', () => {
        const drawer = el('settingsDrawer');
        if (drawer) {
            drawer.classList.remove('hidden');
            loadSettingsUI();
        }
    });

    on('close-settings-btn', 'click', () => {
        const drawer = el('settingsDrawer');
        if (drawer) drawer.classList.add('hidden');
    });

    // Settings change handlers - Appearance
    on('setting-theme', 'change', (e) => setSetting('theme', e.target.value));
    on('setting-font-size', 'change', (e) => setSetting('fontSize', e.target.value));
    on('setting-layout', 'change', (e) => setSetting('layout', e.target.value));

    // Settings change handlers - Chat Behavior
    on('setting-auto-scroll', 'change', (e) => setSetting('autoScroll', e.target.checked));
    on('setting-enter-send', 'change', (e) => setSetting('enterToSend', e.target.checked));
    on('setting-timestamps', 'change', (e) => setSetting('showTimestamps', e.target.checked));
    on('setting-stream-response', 'change', (e) => setSetting('streamResponse', e.target.checked));

    // Settings change handlers - Generation Settings
    on('setting-temperature', 'input', (e) => {
        const val = e.target.value.trim();
        state.run.temperature = val === '' ? null : parseFloat(val);
        renderTopbar();
    });
    on('setting-top-p', 'input', (e) => {
        const val = e.target.value.trim();
        state.run.top_p = val === '' ? null : parseFloat(val);
        renderTopbar();
    });
    on('setting-max-tokens', 'input', (e) => {
        const val = e.target.value.trim();
        state.run.max_tokens = val === '' ? null : parseInt(val, 10);
        renderTopbar();
    });

    // Settings change handlers - Provider Defaults
    on('setting-remember-provider', 'change', (e) => setSetting('rememberProvider', e.target.checked));
    on('setting-remember-model', 'change', (e) => setSetting('rememberModel', e.target.checked));

    // Reset generation settings
    on('reset-generation-settings-btn', 'click', () => {
        state.run.temperature = null;
        state.run.top_p = null;
        state.run.max_tokens = null;
        loadSettingsUI(); // Reload UI to reflect changes
        renderTopbar();
    });

    // Data actions
    on('clear-history-btn', 'click', async () => {
        if (confirm('Are you sure you want to clear all conversation history? This cannot be undone.')) {
            // TODO: Implement clear history via API
            showError('Clear history not yet implemented');
        }
    });

    on('export-data-btn', 'click', () => {
        // Export settings and conversation data as JSON
        const data = {
            settings: getAllSettings(),
            exportedAt: new Date().toISOString(),
        };
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const a = document.createElement('a');
        a.href = url;
        a.download = `omniai-settings-${new Date().toISOString().split('T')[0]}.json`;
        a.click();
        URL.revokeObjectURL(url);
    });

    // Message sending
    on('send-btn', 'click', () => {
        debugLog('SEND_CLICK');
        sendMessage().catch(error => {
            debugLog('SEND_ERROR', { error: error.message });
            console.error('Send error:', error);
        });
    });
    on('message-input', 'keydown', (e) => {
        // Respect enterToSend setting
        if (e.key === 'Enter' && !e.shiftKey && getSetting('enterToSend')) {
            e.preventDefault();
            sendMessage();
        } else if (e.key === 'Escape') {
            cancelStreaming();
        }
    });

    on('cancel-btn', 'click', cancelStreaming);

    on('retry-btn', 'click', async () => {
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
    on('sidebar-toggle', 'click', () => {
        const sidebar = document.getElementById('sidebar');
        sidebar.classList.toggle('open');
    });

    on('new-conversation-btn', 'click', () => {
        debugLog('NEW_CHAT_CLICK');
        createNewConversation().catch(error => {
            debugLog('NEW_CHAT_ERROR', { error: error.message });
            console.error('New chat error:', error);
        });
    });

    on('search-conversations', 'input', (e) => {
        loadConversations(e.target.value);
    });

    on('dismiss-error', 'click', hideError);

    on('retry-stream', 'click', () => {
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
    on('test-me', 'click', async () => {
        try {
            const result = await getMe();
            const diagEl = el('diag-results');
            if (diagEl) diagEl.textContent = JSON.stringify(result, null, 2);
        } catch (error) {
            const diagEl = el('diag-results');
            if (diagEl) diagEl.textContent = 'Error: ' + error.message;
        }
    });

    on('test-providers', 'click', async () => {
        try {
            const result = await getProviders();
            const diagEl = el('diag-results');
            if (diagEl) diagEl.textContent = JSON.stringify(result, null, 2);
        } catch (error) {
            const diagEl = el('diag-results');
            if (diagEl) diagEl.textContent = 'Error: ' + error.message;
        }
    });
}

// Initialize app
document.addEventListener('DOMContentLoaded', async () => {
    bindUI();
    window.addEventListener('hashchange', handleRouteChange);
    await initializeAuth();
    handleRouteChange();
});