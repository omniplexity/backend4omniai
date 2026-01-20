// OmniAI WebUI Main Application Controller
// Single-init pattern with defensive DOM bindings

(function() {
    'use strict';

    // ============================================
    // STATE
    // ============================================

    let state = {
        session: { user: null },
        threads: [],
        activeThreadId: null,
        run: { model: null, temperature: 0.7, top_p: 1, max_tokens: 1024 },
        stream: { status: 'idle', elapsedMs: 0, usage: null, lastError: null }
    };

    // Streaming state
    let currentStreamingParser = null;
    let streamingStartTime = null;
    let currentGenerationId = null;
    let currentConversationId = null;

    // UI state
    let sidebarOpen = false;
    let settingsDrawerOpen = false;
    let rightDrawerOpen = false;
    let controlsPanelOpen = false;
    let userScrolledUp = false;

    // ============================================
    // UTILITY FUNCTIONS
    // ============================================

    function $(id) {
        return document.getElementById(id);
    }

    function $$(selector) {
        return document.querySelectorAll(selector);
    }

    function bindClick(id, handler) {
        const el = $(id);
        if (el) {
            el.addEventListener('click', handler);
        }
    }

    function bindEvent(id, event, handler) {
        const el = $(id);
        if (el) {
            el.addEventListener(event, handler);
        }
    }

    function show(id) {
        const el = $(id);
        if (el) el.classList.remove('hidden');
    }

    function hide(id) {
        const el = $(id);
        if (el) el.classList.add('hidden');
    }

    function toggle(id, force) {
        const el = $(id);
        if (el) el.classList.toggle('hidden', !force);
    }

    // ============================================
    // ROUTING
    // ============================================

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

        // Unauthenticated users can only access login/register
        if (!user && route !== 'register') {
            showView('login-view');
            return;
        }

        // Admin route requires admin role
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

    // ============================================
    // VIEW MANAGEMENT
    // ============================================

    function showView(viewId) {
        $$('.view').forEach(view => view.classList.add('hidden'));
        const view = $(viewId);
        if (view) view.classList.remove('hidden');
    }

    // ============================================
    // USER DISPLAY
    // ============================================

    function updateUserDisplay(user) {
        const displays = ['user-display', 'sidebar-user-display', 'admin-user-display'];
        displays.forEach(id => {
            const el = $(id);
            if (el) {
                el.textContent = user ? user.username || user.email || 'User' : '';
            }
        });

        // Show/hide admin link
        const adminLink = $('admin-link');
        if (adminLink) {
            if (user && user.role === 'admin') {
                adminLink.classList.remove('hidden');
            } else {
                adminLink.classList.add('hidden');
            }
        }

        // Update state
        state.session.user = user;
    }

    // ============================================
    // SIDEBAR
    // ============================================

    function toggleSidebar(open) {
        sidebarOpen = open !== undefined ? open : !sidebarOpen;
        const sidebar = $('sidebar');
        const backdrop = $('sidebar-backdrop');
        const toggle = $('sidebar-toggle');

        if (sidebar) sidebar.classList.toggle('open', sidebarOpen);
        if (backdrop) backdrop.classList.toggle('visible', sidebarOpen);
        if (backdrop) backdrop.classList.toggle('hidden', !sidebarOpen);
        if (toggle) toggle.setAttribute('aria-expanded', sidebarOpen);
    }

    function closeSidebar() {
        toggleSidebar(false);
    }

    // ============================================
    // SETTINGS DRAWER
    // ============================================

    function toggleSettingsDrawer(open) {
        settingsDrawerOpen = open !== undefined ? open : !settingsDrawerOpen;
        const drawer = $('settingsDrawer');
        if (drawer) {
            drawer.classList.toggle('hidden', !settingsDrawerOpen);
        }

        // Close controls panel if settings drawer opens
        if (settingsDrawerOpen) {
            closeControlsPanel();
        }
    }

    function closeSettingsDrawer() {
        toggleSettingsDrawer(false);
    }

    // ============================================
    // CONTROLS PANEL
    // ============================================

    function toggleControlsPanel(open) {
        controlsPanelOpen = open !== undefined ? open : !controlsPanelOpen;
        const panel = $('controls-panel');
        if (panel) {
            panel.classList.toggle('hidden', !controlsPanelOpen);
        }

        // Close settings drawer if controls panel opens
        if (controlsPanelOpen) {
            closeSettingsDrawer();
            closeRightDrawer();
            syncQuickControls();
        }
    }

    function closeControlsPanel() {
        toggleControlsPanel(false);
    }

    function syncQuickControls() {
        const temp = getTemperature();
        const topP = getTopP();
        const maxTokens = getMaxTokens();

        const quickTemp = $('quick-temperature');
        const quickTopP = $('quick-top-p');
        const quickMaxTokens = $('quick-max-tokens');
        const tempDisplay = $('temp-display');
        const topPDisplay = $('top-p-display');

        if (quickTemp) quickTemp.value = temp;
        if (quickTopP) quickTopP.value = topP;
        if (quickMaxTokens) quickMaxTokens.value = maxTokens || '';
        if (tempDisplay) tempDisplay.textContent = temp.toFixed(1);
        if (topPDisplay) topPDisplay.textContent = topP.toFixed(2);
    }

    // ============================================
    // RIGHT DRAWER
    // ============================================

    function toggleRightDrawer(open) {
        rightDrawerOpen = open !== undefined ? open : !rightDrawerOpen;
        const drawer = $('right-drawer');
        if (drawer) {
            drawer.classList.toggle('hidden', !rightDrawerOpen);
        }

        // Close other panels when right drawer opens
        if (rightDrawerOpen) {
            closeSettingsDrawer();
            closeControlsPanel();
            syncRightDrawerSettings();
        }
    }

    function closeRightDrawer() {
        toggleRightDrawer(false);
    }

    function syncRightDrawerSettings() {
        const temp = getTemperature();
        const topP = getTopP();
        const maxTokens = getMaxTokens();

        // Generation tab
        const genTemp = $('drawer-gen-temperature');
        const genTempRange = $('drawer-gen-temperature-range');
        const genTopP = $('drawer-gen-top-p');
        const genTopPRange = $('drawer-gen-top-p-range');
        const genMaxTokens = $('drawer-gen-max-tokens');

        if (genTemp) genTemp.value = temp;
        if (genTempRange) genTempRange.value = temp;
        if (genTopP) genTopP.value = topP;
        if (genTopPRange) genTopPRange.value = topP;
        if (genMaxTokens) genMaxTokens.value = maxTokens || '';

        // Update controls pill
        updateControlsPill();
    }

    function updateControlsPill() {
        const temp = getTemperature();
        const topP = getTopP();
        const maxTokens = getMaxTokens();
        const pill = $('controls-pill');

        if (pill) {
            const parts = [];
            parts.push(`Temp ${temp.toFixed(1)}`);
            parts.push(`Top-P ${topP.toFixed(1)}`);
            if (maxTokens) {
                parts.push(`Tokens ${maxTokens}`);
            } else {
                parts.push('Tokens Auto');
            }
            pill.textContent = parts.join(' · ');
        }
    }

    function switchDrawerTab(tabName) {
        // Update tab buttons
        const tabs = $$('.drawer-tab');
        tabs.forEach(tab => {
            tab.classList.toggle('active', tab.dataset.tab === tabName);
        });

        // Update sections
        const sections = $$('.drawer-section');
        sections.forEach(section => {
            section.classList.toggle('active', section.id === `drawer-${tabName}-section`);
        });
    }

    // ============================================
    // SETTINGS SYNC
    // ============================================

    function syncDrawerSettings() {
        const temp = getTemperature();
        const topP = getTopP();
        const maxTokens = getMaxTokens();

        const drawerTemp = $('drawer-temperature');
        const drawerTempRange = $('drawer-temperature-range');
        const drawerTopP = $('drawer-top-p');
        const drawerTopPRange = $('drawer-top-p-range');
        const drawerMaxTokens = $('drawer-max-tokens');

        if (drawerTemp) drawerTemp.value = temp;
        if (drawerTempRange) drawerTempRange.value = temp;
        if (drawerTopP) drawerTopP.value = topP;
        if (drawerTopPRange) drawerTopPRange.value = topP;
        if (drawerMaxTokens) drawerMaxTokens.value = maxTokens || '';
    }

    function updateApiBaseUrlInput() {
        const input = $('api-base-url');
        if (input) {
            input.value = getApiBaseUrl();
        }
    }

    // ============================================
    // CONNECTION STATUS
    // ============================================

    let healthCheckInterval = null;
    let healthCheckBackoff = 1000; // Start with 1s backoff
    const maxBackoff = 30000; // Max 30s
    let lastHealthError = null;

    function updateConnectionStatus(status, error = null) {
        const indicator = $('connection-indicator');
        const text = $('connection-text');

        if (indicator) {
            indicator.classList.remove('online', 'offline', 'connecting');
            indicator.classList.add(status);

            // Set tooltip with error reason
            if (error) {
                indicator.title = `Connection failed: ${error}`;
            } else {
                indicator.title = status === 'online' ? 'Connected to backend' : status === 'offline' ? 'Backend unreachable' : 'Connecting...';
            }
        }

        if (text) {
            const labels = {
                online: 'Online',
                offline: 'Offline',
                connecting: 'Connecting...'
            };
            text.textContent = labels[status] || 'Unknown';
        }

        lastHealthError = error;
    }

    async function performHealthCheck() {
        try {
            const baseUrl = getApiBaseUrl();
            const response = await fetch(`${baseUrl}/health`, {
                method: 'GET',
                credentials: 'include',
                signal: AbortSignal.timeout(5000) // 5s timeout
            });

            if (response.ok) {
                updateConnectionStatus('online');
                healthCheckBackoff = 1000; // Reset backoff on success
                return true;
            } else {
                throw new Error(`HTTP ${response.status}`);
            }
        } catch (error) {
            let errorReason = 'Network error';
            if (error.name === 'TimeoutError') {
                errorReason = 'Timeout';
            } else if (error.message.includes('Failed to fetch') || error.message.includes('NetworkError')) {
                errorReason = 'Network unreachable';
            } else if (error.message.includes('CORS')) {
                errorReason = 'CORS policy blocked';
            } else if (error.message.includes('404')) {
                errorReason = 'Endpoint not found';
            } else if (error.message.includes('403')) {
                errorReason = 'Forbidden';
            } else if (error.message.includes('TLS') || error.message.includes('SSL')) {
                errorReason = 'TLS/SSL error';
            }

            updateConnectionStatus('offline', errorReason);
            return false;
        }
    }

    function startHealthCheck() {
        if (healthCheckInterval) {
            clearInterval(healthCheckInterval);
        }

        // Initial check
        performHealthCheck();

        // Periodic check every 10 seconds
        healthCheckInterval = setInterval(async () => {
            const success = await performHealthCheck();
            if (!success) {
                // Exponential backoff on failure
                healthCheckBackoff = Math.min(healthCheckBackoff * 2, maxBackoff);
                clearInterval(healthCheckInterval);
                setTimeout(() => {
                    startHealthCheck(); // Restart with new backoff
                }, healthCheckBackoff);
            }
        }, 10000);
    }

    function stopHealthCheck() {
        if (healthCheckInterval) {
            clearInterval(healthCheckInterval);
            healthCheckInterval = null;
        }
    }

    // ============================================
    // CHAT HEADER
    // ============================================

    function updateChatTitle(title) {
        const titleEl = $('chat-title');
        if (titleEl) {
            titleEl.textContent = title || 'New Chat';
        }
    }

    // ============================================
    // EMPTY STATE
    // ============================================

    function showEmptyState() {
        const emptyState = $('empty-state');
        if (emptyState) emptyState.classList.remove('hidden');
    }

    function hideEmptyState() {
        const emptyState = $('empty-state');
        if (emptyState) emptyState.classList.add('hidden');
    }

    // ============================================
    // STATUS LINE
    // ============================================

    function updateStatusLine(text, elapsed = null, usage = null) {
        const statusText = $('status-text');
        const elapsedTime = $('elapsed-time');
        const tokenUsage = $('token-usage');

        if (statusText) statusText.textContent = text;

        if (elapsedTime) {
            elapsedTime.textContent = elapsed !== null ? `${elapsed.toFixed(1)}s` : '';
        }

        if (tokenUsage) {
            if (usage) {
                const parts = [];
                if (usage.prompt_tokens !== undefined) parts.push(`P:${usage.prompt_tokens}`);
                if (usage.completion_tokens !== undefined) parts.push(`C:${usage.completion_tokens}`);
                if (usage.total_tokens !== undefined) parts.push(`T:${usage.total_tokens}`);
                tokenUsage.textContent = parts.join(' ');
            } else {
                tokenUsage.textContent = '';
            }
        }
    }

    // ============================================
    // COMPOSER STATE
    // ============================================

    function updateComposerState() {
        const providerId = getSelectedProvider();
        const modelId = getSelectedModel();
        const sendBtn = $('send-btn');
        const cancelBtn = $('cancel-btn');
        const messageInput = $('message-input');

        const isStreaming = state.stream.status === 'streaming';
        const hasInput = messageInput && messageInput.value.trim().length > 0;
        const hasProviderModel = providerId && modelId;

        if (sendBtn) {
            sendBtn.disabled = isStreaming || !hasInput || !hasProviderModel;
            sendBtn.classList.toggle('hidden', isStreaming);
        }

        if (cancelBtn) {
            cancelBtn.classList.toggle('hidden', !isStreaming);
        }
    }

    function clearMessageInput() {
        const input = $('message-input');
        if (input) {
            input.value = '';
            input.style.height = 'auto';
        }
        updateComposerState();
    }

    // ============================================
    // AUTO-RESIZE TEXTAREA
    // ============================================

    function autoResizeTextarea(textarea) {
        if (!textarea) return;
        textarea.style.height = 'auto';
        textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
    }

    // ============================================
    // SCROLL MANAGEMENT
    // ============================================

    function isNearBottom(element, threshold = 100) {
        if (!element) return true;
        return element.scrollHeight - element.scrollTop - element.clientHeight < threshold;
    }

    function scrollToBottom(element) {
        if (!element) return;
        element.scrollTop = element.scrollHeight;
    }

    function scrollToBottomIfNeeded() {
        const transcript = $('transcript');
        if (!transcript) return;

        if (!userScrolledUp && isNearBottom(transcript)) {
            scrollToBottom(transcript);
            hideJumpToLatest();
        } else if (!isNearBottom(transcript)) {
            showJumpToLatest();
        }
    }

    function showJumpToLatest() {
        const pill = $('jump-to-latest');
        if (pill) pill.classList.remove('hidden');
    }

    function hideJumpToLatest() {
        const pill = $('jump-to-latest');
        if (pill) pill.classList.add('hidden');
    }

    function handleTranscriptScroll() {
        const transcript = $('transcript');
        if (!transcript) return;

        userScrolledUp = !isNearBottom(transcript);

        if (isNearBottom(transcript)) {
            hideJumpToLatest();
        }
    }

    // ============================================
    // TOAST NOTIFICATIONS
    // ============================================

    function showToast(message, type = 'info', duration = 4000) {
        const host = $('toastHost');
        if (!host) return;

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `
            <span>${message}</span>
            <button class="btn-close" onclick="this.parentElement.remove()">
                <span class="icon-close"></span>
            </button>
        `;

        host.appendChild(toast);

        if (duration > 0) {
            setTimeout(() => {
                toast.remove();
            }, duration);
        }
    }

    function showError(message) {
        showToast(message, 'error', 6000);
    }

    function showSuccess(message) {
        showToast(message, 'success');
    }

    // ============================================
    // BANNERS
    // ============================================

    function showErrorBanner(message) {
        const banner = $('error-banner');
        const messageEl = $('error-message');
        if (banner && messageEl) {
            messageEl.textContent = message;
            banner.classList.remove('hidden');
        }
    }

    function hideErrorBanner() {
        const banner = $('error-banner');
        if (banner) banner.classList.add('hidden');
    }

    function showDisconnectBanner() {
        const banner = $('disconnect-banner');
        if (banner) banner.classList.remove('hidden');
    }

    function hideDisconnectBanner() {
        const banner = $('disconnect-banner');
        if (banner) banner.classList.add('hidden');
    }

    // ============================================
    // TRANSCRIPT RENDERING
    // ============================================

    function renderTranscriptMessages(messages) {
        const transcript = $('transcript');
        if (!transcript) return;

        // Clear existing messages but keep empty state
        const emptyState = $('empty-state');
        transcript.innerHTML = '';

        if (messages.length === 0) {
            if (emptyState) transcript.appendChild(emptyState);
            showEmptyState();
            return;
        }

        hideEmptyState();

        messages.forEach((msg, index) => {
            const card = createMessageCard(msg, index);
            transcript.appendChild(card);
        });

        scrollToBottom(transcript);
    }

    function addMessageToTranscript(role, content, isStreaming = false) {
        const transcript = $('transcript');
        if (!transcript) return;

        hideEmptyState();

        const msg = { role, content };
        const card = createMessageCard(msg, -1);
        if (isStreaming) {
            card.classList.add('streaming');
        }
        transcript.appendChild(card);
        scrollToBottomIfNeeded();

        return card;
    }

    function appendToLastMessage(content) {
        const transcript = $('transcript');
        if (!transcript) return;

        const lastCard = transcript.querySelector('.message-card.streaming');
        if (lastCard) {
            const contentEl = lastCard.querySelector('.message-content');
            if (contentEl) {
                contentEl.innerHTML = renderMessageContent(contentEl.textContent + content);
            }
        }

        scrollToBottomIfNeeded();
    }

    function finalizeLastMessage() {
        const transcript = $('transcript');
        if (!transcript) return;

        const streamingCards = transcript.querySelectorAll('.message-card.streaming');
        streamingCards.forEach(card => card.classList.remove('streaming'));
    }

    // ============================================
    // AUTHENTICATION
    // ============================================

    async function initializeAuth() {
        const user = getCurrentUser();
        updateUserDisplay(user);

        if (user) {
            setRoute('chat');
        } else {
            setRoute('login');
        }
    }

    async function handleLoginSubmit(e) {
        e.preventDefault();
        const username = $('username')?.value;
        const password = $('password')?.value;

        if (!username || !password) return;

        try {
            await handleLogin(username, password);
            updateUserDisplay(getCurrentUser());
            setRoute('chat');
        } catch (error) {
            const errorEl = $('login-error');
            if (errorEl) {
                errorEl.textContent = error.message;
                errorEl.classList.remove('hidden');
            }
        }
    }

    async function handleRegisterSubmit(e) {
        e.preventDefault();
        const inviteCode = $('invite-code')?.value;
        const username = $('reg-username')?.value;
        const password = $('reg-password')?.value;

        if (!inviteCode || !username || !password) return;

        try {
            await handleRegister(inviteCode, username, password);
            updateUserDisplay(getCurrentUser());
            setRoute('chat');
        } catch (error) {
            const errorEl = $('register-error');
            if (errorEl) {
                errorEl.textContent = error.message;
                errorEl.classList.remove('hidden');
            }
        }
    }

    async function handleLogoutClick() {
        await handleLogout();
        updateUserDisplay(null);
        setRoute('login');
    }

    // ============================================
    // CHAT INITIALIZATION
    // ============================================

    async function initializeChat() {
        try {
            updateConnectionStatus('connecting');
            await loadProviders();
            await loadConversations();
            syncDrawerSettings();
            updateApiBaseUrlInput();
            updateComposerState();

            const savedConversationId = getCurrentConversationId();
            if (savedConversationId) {
                try {
                    await selectConversation(savedConversationId);
                } catch (error) {
                    console.warn('Saved conversation not found, creating new one');
                    await createNewConversation();
                }
            } else {
                await createNewConversation();
            }
        } catch (error) {
            updateConnectionStatus('offline');
            showError('Failed to initialize chat: ' + error.message);
        }
    }

    // ============================================
    // PROVIDERS & MODELS
    // ============================================

    async function loadProviders() {
        try {
            const providers = await getProviders();
            renderProviders(providers);
        } catch (error) {
            console.error('Failed to load providers:', error);
        }
    }

    async function handleProviderChange(e) {
        const providerId = e.target.value;
        setSelectedProvider(providerId);
        setSelectedModel('');
        updateComposerState();

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
    }

    function handleModelChange(e) {
        setSelectedModel(e.target.value);
        updateComposerState();
    }

    // ============================================
    // CONVERSATIONS
    // ============================================

    async function loadConversations(query = '') {
        try {
            const conversations = await getConversations(query);
            state.threads = conversations;
            renderConversations(conversations);
        } catch (error) {
            console.error('Failed to load conversations:', error);
        }
    }

    async function createNewConversation() {
        try {
            const conversation = await createConversation();
            currentConversationId = conversation.id;
            setCurrentConversationId(conversation.id);
            state.activeThreadId = conversation.id;
            renderTranscriptMessages([]);
            updateChatTitle('New Chat');
            updateStatusLine('Ready');
            await loadConversations();
        } catch (error) {
            showError('Failed to create conversation: ' + error.message);
        }
    }

    async function selectConversation(conversationId) {
        try {
            const messages = await getConversationMessages(conversationId);
            currentConversationId = conversationId;
            state.activeThreadId = conversationId;
            setCurrentConversationId(conversationId);
            renderTranscriptMessages(messages);

            // Find and set title
            const conversation = state.threads.find(t => t.id === conversationId);
            updateChatTitle(conversation?.title || 'Chat');
            updateStatusLine('Ready');

            // Update sidebar selection
            highlightActiveConversation(conversationId);

            // Close sidebar on mobile
            if (window.innerWidth <= 768) {
                closeSidebar();
            }
        } catch (error) {
            showError('Failed to load conversation: ' + error.message);
            throw error;
        }
    }

    function highlightActiveConversation(conversationId) {
        const list = $('conversations-list');
        if (!list) return;

        list.querySelectorAll('li').forEach(li => {
            li.classList.toggle('active', li.dataset.id === String(conversationId));
        });
    }

    async function renameCurrentConversation() {
        if (!currentConversationId) return;

        const conversation = state.threads.find(t => t.id === currentConversationId);
        const currentTitle = conversation?.title || '';
        const newTitle = prompt('Enter new title:', currentTitle);

        if (newTitle !== null && newTitle.trim() !== '') {
            try {
                await updateConversation(currentConversationId, newTitle.trim());
                updateChatTitle(newTitle.trim());
                await loadConversations();
            } catch (error) {
                showError('Failed to rename conversation: ' + error.message);
            }
        }
    }

    async function deleteCurrentConversation() {
        if (!currentConversationId) return;

        if (confirm('Are you sure you want to delete this conversation?')) {
            try {
                await deleteConversation(currentConversationId);
                await createNewConversation();
                await loadConversations();
            } catch (error) {
                showError('Failed to delete conversation: ' + error.message);
            }
        }
    }

    // ============================================
    // MESSAGE SENDING
    // ============================================

    async function sendMessage() {
        if (!currentConversationId) return;

        const messageInput = $('message-input');
        const content = messageInput?.value.trim();
        if (!content) return;

        const providerId = getSelectedProvider();
        const modelId = getSelectedModel();

        if (!providerId || !modelId) {
            showError('Please select a provider and model first.');
            return;
        }

        try {
            // Update UI state
            state.stream.status = 'streaming';
            updateComposerState();
            clearMessageInput();

            // Add user message
            addMessageToTranscript('user', content);

            // Add placeholder for assistant message
            addMessageToTranscript('assistant', '', true);

            // Start streaming
            await startStreaming(content, providerId, modelId);

        } catch (error) {
            showError('Failed to send message: ' + error.message);
            state.stream.status = 'error';
            updateComposerState();
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
                const elapsed = streamingStartTime ? (Date.now() - streamingStartTime) / 1000 : null;
                updateStatusLine('Streaming...', elapsed, event.usage);
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
        state.stream.status = 'error';
        state.stream.lastError = error;
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

        state.stream.status = 'idle';
        updateComposerState();

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
        }

        state.stream.status = 'cancelled';
        finalizeStreaming();
        updateStatusLine('Cancelled');
    }

    // ============================================
    // SETTINGS HANDLERS
    // ============================================

    function handleDrawerTemperatureChange(e) {
        const value = parseFloat(e.target.value);
        setTemperature(value);

        // Sync both inputs
        const numInput = $('drawer-temperature');
        const rangeInput = $('drawer-temperature-range');
        if (numInput && e.target !== numInput) numInput.value = value;
        if (rangeInput && e.target !== rangeInput) rangeInput.value = value;
    }

    function handleDrawerTopPChange(e) {
        const value = parseFloat(e.target.value);
        setTopP(value);

        // Sync both inputs
        const numInput = $('drawer-top-p');
        const rangeInput = $('drawer-top-p-range');
        if (numInput && e.target !== numInput) numInput.value = value;
        if (rangeInput && e.target !== rangeInput) rangeInput.value = value;
    }

    function handleDrawerMaxTokensChange(e) {
        const value = e.target.value ? parseInt(e.target.value, 10) : null;
        setMaxTokens(value);
    }

    function handleQuickTemperatureChange(e) {
        const value = parseFloat(e.target.value);
        setTemperature(value);
        const display = $('temp-display');
        if (display) display.textContent = value.toFixed(1);
    }

    function handleQuickTopPChange(e) {
        const value = parseFloat(e.target.value);
        setTopP(value);
        const display = $('top-p-display');
        if (display) display.textContent = value.toFixed(2);
    }

    function handleQuickMaxTokensChange(e) {
        const value = e.target.value ? parseInt(e.target.value, 10) : null;
        setMaxTokens(value);
    }

    function handleSaveUrlClick() {
        const input = $('api-base-url');
        const url = input?.value.trim();
        if (url) {
            setApiBaseUrl(url);
            showSuccess('API Base URL saved. Refresh to apply.');
        }
    }

    // ============================================
    // KEYBOARD HANDLERS
    // ============================================

    function handleMessageInputKeydown(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        } else if (e.key === 'Escape') {
            if (state.stream.status === 'streaming') {
                cancelStreaming();
            }
        }
    }

    function handleGlobalKeydown(e) {
        // Cmd/Ctrl + K for command palette
        if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
            e.preventDefault();
            // Command palette is handled by command-palette.js
        }

        // Escape to close modals/drawers
        if (e.key === 'Escape') {
            if (settingsDrawerOpen) {
                closeSettingsDrawer();
            } else if (controlsPanelOpen) {
                closeControlsPanel();
            } else if (sidebarOpen && window.innerWidth <= 768) {
                closeSidebar();
            }
        }
    }

    // ============================================
    // EVENT BINDING
    // ============================================

    function bindEvents() {
        // Route changes
        window.addEventListener('hashchange', handleRouteChange);

        // Global keyboard
        document.addEventListener('keydown', handleGlobalKeydown);

        // Auth forms
        bindEvent('login-form', 'submit', handleLoginSubmit);
        bindEvent('register-form', 'submit', handleRegisterSubmit);
        bindClick('show-register', (e) => { e.preventDefault(); setRoute('register'); });
        bindClick('show-login', (e) => { e.preventDefault(); setRoute('login'); });
        bindClick('logout-btn', handleLogoutClick);
        bindClick('sidebar-logout-btn', handleLogoutClick);
        bindClick('admin-logout-btn', handleLogoutClick);

        // Sidebar
        bindClick('sidebar-toggle', () => toggleSidebar());
        bindClick('sidebar-backdrop', closeSidebar);
        bindClick('new-conversation-btn', createNewConversation);
        bindEvent('search-conversations', 'input', (e) => loadConversations(e.target.value));

        // Settings
        bindClick('settings-toggle-btn', () => toggleSettingsDrawer());
        bindClick('close-settings-btn', closeSettingsDrawer);
        bindClick('controls-btn', () => toggleControlsPanel());

        // Chat actions
        bindClick('rename-chat-btn', renameCurrentConversation);
        bindClick('delete-chat-btn', deleteCurrentConversation);

        // Composer
        bindClick('send-btn', sendMessage);
        bindClick('cancel-btn', cancelStreaming);
        bindEvent('message-input', 'keydown', handleMessageInputKeydown);
        bindEvent('message-input', 'input', (e) => {
            autoResizeTextarea(e.target);
            updateComposerState();
        });

        // Jump to latest
        bindClick('jump-to-latest', () => {
            const transcript = $('transcript');
            if (transcript) {
                scrollToBottom(transcript);
                userScrolledUp = false;
                hideJumpToLatest();
            }
        });

        // Transcript scroll
        bindEvent('transcript', 'scroll', handleTranscriptScroll);

        // Provider/Model
        bindEvent('provider-select', 'change', handleProviderChange);
        bindEvent('model-select', 'change', handleModelChange);

        // Drawer settings
        bindEvent('drawer-temperature', 'input', handleDrawerTemperatureChange);
        bindEvent('drawer-temperature-range', 'input', handleDrawerTemperatureChange);
        bindEvent('drawer-top-p', 'input', handleDrawerTopPChange);
        bindEvent('drawer-top-p-range', 'input', handleDrawerTopPChange);
        bindEvent('drawer-max-tokens', 'input', handleDrawerMaxTokensChange);

        // Quick controls
        bindEvent('quick-temperature', 'input', handleQuickTemperatureChange);
        bindEvent('quick-top-p', 'input', handleQuickTopPChange);
        bindEvent('quick-max-tokens', 'input', handleQuickMaxTokensChange);

        // Backend URL
        bindClick('save-url-btn', handleSaveUrlClick);

        // Banners
        bindClick('dismiss-error', hideErrorBanner);
        bindClick('retry-stream', () => {
            hideDisconnectBanner();
            // Could implement retry logic here
        });

        // Click outside to close panels
        document.addEventListener('click', (e) => {
            const controlsPanel = $('controls-panel');
            const controlsBtn = $('controls-btn');

            if (controlsPanelOpen && controlsPanel && controlsBtn) {
                if (!controlsPanel.contains(e.target) && !controlsBtn.contains(e.target)) {
                    closeControlsPanel();
                }
            }
        });

        // Suggestion buttons
        document.querySelectorAll('.suggestion-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const prompt = btn.dataset.prompt;
                const messageInput = $('message-input');
                if (messageInput && prompt) {
                    messageInput.value = prompt;
                    messageInput.focus();
                    autoResizeTextarea(messageInput);
                    updateComposerState();
                }
            });
        });

        // Diagnostics (if present)
        bindClick('test-me', async () => {
            try {
                const result = await getMe();
                const results = $('diag-results');
                if (results) results.textContent = JSON.stringify(result, null, 2);
            } catch (error) {
                const results = $('diag-results');
                if (results) results.textContent = 'Error: ' + error.message;
            }
        });

        bindClick('test-providers', async () => {
            try {
                const result = await getProviders();
                const results = $('diag-results');
                if (results) results.textContent = JSON.stringify(result, null, 2);
            } catch (error) {
                const results = $('diag-results');
                if (results) results.textContent = 'Error: ' + error.message;
            }
        });
    }

    // ============================================
    // INITIALIZATION
    // ============================================

    async function initApp() {
        bindEvents();
        startHealthCheck();
        await initializeAuth();
        handleRouteChange();
    }

    // Single init on DOMContentLoaded
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initApp);
    } else {
        initApp();
    }

    // Expose necessary functions globally for other modules
    window.selectConversation = selectConversation;
    window.renameConversation = async function(id, title) {
        const newTitle = prompt('Enter new title:', title || '');
        if (newTitle !== null && newTitle.trim() !== '') {
            try {
                await updateConversation(id, newTitle.trim());
                await loadConversations();
                if (id === currentConversationId) {
                    updateChatTitle(newTitle.trim());
                }
            } catch (error) {
                showError('Failed to rename conversation: ' + error.message);
            }
        }
    };
    window.deleteConversation = async function(id) {
        if (confirm('Are you sure you want to delete this conversation?')) {
            try {
                await deleteConversation(id);
                if (id === currentConversationId) {
                    await createNewConversation();
                }
                await loadConversations();
            } catch (error) {
                showError('Failed to delete conversation: ' + error.message);
            }
        }
    };
    window.showToast = showToast;
    window.showError = showError;
    window.showSuccess = showSuccess;

})();