// OmniAI WebUI DOM Rendering Helpers

// ============================================
// VIEW MANAGEMENT
// ============================================

function showView(viewId) {
    document.querySelectorAll('.view').forEach(view => view.classList.add('hidden'));
    const view = document.getElementById(viewId);
    if (view) view.classList.remove('hidden');
}

// ============================================
// ERROR/BANNER DISPLAY
// ============================================

function showError(message) {
    if (window.showToast) {
        window.showToast(message, 'error', 6000);
    } else {
        const banner = document.getElementById('error-banner');
        const messageEl = document.getElementById('error-message');
        if (banner && messageEl) {
            messageEl.textContent = message;
            banner.classList.remove('hidden');
        }
    }
}

function hideError() {
    const banner = document.getElementById('error-banner');
    if (banner) banner.classList.add('hidden');
}

function showDisconnectBanner() {
    const banner = document.getElementById('disconnect-banner');
    if (banner) banner.classList.remove('hidden');
}

function hideDisconnectBanner() {
    const banner = document.getElementById('disconnect-banner');
    if (banner) banner.classList.add('hidden');
}

// ============================================
// CONVERSATIONS LIST
// ============================================

function renderConversations(conversations) {
    const list = document.getElementById('conversations-list');
    if (!list) return;

    list.innerHTML = '';

    if (!conversations || conversations.length === 0) {
        const emptyLi = document.createElement('li');
        emptyLi.className = 'empty-conversations';
        emptyLi.innerHTML = '<span class="conversation-title" style="color: var(--muted); font-style: italic;">No conversations yet</span>';
        list.appendChild(emptyLi);
        return;
    }

    conversations.forEach(conv => {
        const li = document.createElement('li');
        li.dataset.id = conv.id;

        const title = document.createElement('span');
        title.className = 'conversation-title';
        title.textContent = conv.title || 'Untitled Chat';
        title.addEventListener('click', () => {
            if (window.selectConversation) {
                window.selectConversation(conv.id);
            }
        });

        const actions = document.createElement('div');
        actions.className = 'conversation-actions';

        const renameBtn = document.createElement('button');
        renameBtn.textContent = 'Rename';
        renameBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (window.renameConversation) {
                window.renameConversation(conv.id, conv.title);
            }
        });

        const deleteBtn = document.createElement('button');
        deleteBtn.textContent = 'Delete';
        deleteBtn.className = 'btn-danger';
        deleteBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (window.deleteConversation) {
                window.deleteConversation(conv.id);
            }
        });

        actions.appendChild(renameBtn);
        actions.appendChild(deleteBtn);

        li.appendChild(title);
        li.appendChild(actions);
        list.appendChild(li);
    });
}

// ============================================
// TRANSCRIPT / MESSAGES
// ============================================

function renderTranscript(messages) {
    const transcript = document.getElementById('transcript');
    if (!transcript) return;

    // Keep empty state if it exists
    const emptyState = document.getElementById('empty-state');

    transcript.innerHTML = '';

    if (!messages || messages.length === 0) {
        if (emptyState) {
            transcript.appendChild(emptyState);
            emptyState.classList.remove('hidden');
        }
        return;
    }

    if (emptyState) {
        emptyState.classList.add('hidden');
    }

    messages.forEach((msg, index) => {
        const messageCard = createMessageCard(msg, index);
        transcript.appendChild(messageCard);
    });

    // Scroll to bottom
    transcript.scrollTop = transcript.scrollHeight;
}

function createMessageCard(msg, index) {
    const card = document.createElement('div');
    card.className = `message-card ${msg.role}`;
    card.dataset.messageIndex = index;

    // Header/meta section
    const header = document.createElement('div');
    header.className = 'message-header';

    const meta = document.createElement('div');
    meta.className = 'message-meta';

    if (msg.role === 'assistant') {
        // Add model info if available
        const modelInfo = document.createElement('span');
        modelInfo.className = 'message-model';
        modelInfo.textContent = msg.model || 'Assistant';
        meta.appendChild(modelInfo);

        if (msg.elapsed_time) {
            const timing = document.createElement('span');
            timing.className = 'message-timing';
            timing.textContent = `${msg.elapsed_time}s`;
            meta.appendChild(timing);
        }

        if (msg.usage) {
            const tokens = document.createElement('span');
            tokens.className = 'message-tokens';
            tokens.textContent = `${msg.usage.total_tokens || 'N/A'} tokens`;
            meta.appendChild(tokens);
        }
    } else {
        // User message
        const roleInfo = document.createElement('span');
        roleInfo.className = 'message-model';
        roleInfo.textContent = 'You';
        meta.appendChild(roleInfo);
    }

    header.appendChild(meta);

    // Content section
    const content = document.createElement('div');
    content.className = 'message-content';

    if (msg.role === 'assistant' && msg.content === '') {
        card.classList.add('streaming');
        content.innerHTML = '<div class="skeleton-placeholder"></div>';
    } else {
        content.innerHTML = renderMessageContent(msg.content);
    }

    // Actions section (hover)
    const actions = document.createElement('div');
    actions.className = 'message-actions';

    // Copy button for all messages
    const copyBtn = document.createElement('button');
    copyBtn.className = 'action-btn copy-btn';
    copyBtn.innerHTML = '<span title="Copy">Copy</span>';
    copyBtn.addEventListener('click', () => copyMessageToClipboard(msg.content));
    actions.appendChild(copyBtn);

    if (msg.role === 'assistant') {
        // Regenerate button
        const regenBtn = document.createElement('button');
        regenBtn.className = 'action-btn regen-btn';
        regenBtn.innerHTML = '<span title="Regenerate">Retry</span>';
        regenBtn.addEventListener('click', () => {
            if (window.retryMessageAtIndex) {
                window.retryMessageAtIndex(index);
            }
        });
        actions.appendChild(regenBtn);
    }

    card.appendChild(header);
    card.appendChild(content);
    card.appendChild(actions);

    return card;
}

function renderMessageContent(content) {
    if (!content) return '';

    // Escape HTML first
    let escaped = content
        .replace(/&/g, '&')
        .replace(/</g, '<')
        .replace(/>/g, '>');

    // Process code blocks
    escaped = escaped.replace(/```(\w+)?\n?([\s\S]*?)```/g, (match, lang, code) => {
        const language = lang || 'text';
        const codeId = 'code-' + Math.random().toString(36).substr(2, 9);

        return `<div class="code-block" data-code-id="${codeId}">
            <div class="code-header">
                <span class="code-lang">${language}</span>
                <div class="code-actions">
                    <button class="code-copy-btn" onclick="copyCodeBlock('${codeId}')">Copy</button>
                </div>
            </div>
            <pre><code class="language-${language}" id="${codeId}">${code.trim()}</code></pre>
        </div>`;
    });

    // Process inline code
    escaped = escaped.replace(/`([^`]+)`/g, '<code>$1</code>');

    // Process line breaks
    escaped = escaped.replace(/\n/g, '<br>');

    return escaped;
}

// Global function for code block copy
window.copyCodeBlock = function(codeId) {
    const codeEl = document.getElementById(codeId);
    if (codeEl) {
        copyMessageToClipboard(codeEl.textContent);
        // Find the button and update text
        const block = codeEl.closest('.code-block');
        const btn = block?.querySelector('.code-copy-btn');
        if (btn) {
            btn.textContent = 'Copied!';
            setTimeout(() => btn.textContent = 'Copy', 2000);
        }
    }
};

function copyMessageToClipboard(content) {
    if (!content) return;

    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(content).then(() => {
            if (window.showToast) {
                window.showToast('Copied to clipboard', 'success', 2000);
            }
        }).catch(err => {
            console.error('Failed to copy:', err);
            fallbackCopy(content);
        });
    } else {
        fallbackCopy(content);
    }
}

function fallbackCopy(content) {
    const textArea = document.createElement('textarea');
    textArea.value = content;
    textArea.style.position = 'fixed';
    textArea.style.left = '-9999px';
    document.body.appendChild(textArea);
    textArea.select();
    try {
        document.execCommand('copy');
        if (window.showToast) {
            window.showToast('Copied to clipboard', 'success', 2000);
        }
    } catch (err) {
        console.error('Fallback copy failed:', err);
    }
    document.body.removeChild(textArea);
}

// ============================================
// INCREMENTAL MESSAGE UPDATES
// ============================================

function appendToLastMessage(content) {
    const transcript = document.getElementById('transcript');
    if (!transcript) return;

    const lastCard = transcript.querySelector('.message-card.streaming');
    if (lastCard) {
        const contentEl = lastCard.querySelector('.message-content');
        if (contentEl) {
            // Get current text content and append
            const currentText = contentEl.textContent || '';
            contentEl.innerHTML = renderMessageContent(currentText + content);
        }
    }

    // Smart scroll
    const isNearBottom = transcript.scrollHeight - transcript.scrollTop - transcript.clientHeight < 100;
    if (isNearBottom) {
        transcript.scrollTop = transcript.scrollHeight;
    }
}

function finalizeLastMessage() {
    const transcript = document.getElementById('transcript');
    if (!transcript) return;

    const streamingCards = transcript.querySelectorAll('.message-card.streaming');
    streamingCards.forEach(card => card.classList.remove('streaming'));
}

// ============================================
// PROVIDER/MODEL DROPDOWNS
// ============================================

function renderProviders(providers) {
    const select = document.getElementById('provider-select');
    if (!select) return;

    select.innerHTML = '<option value="">Provider</option>';

    if (providers && providers.length > 0) {
        providers.forEach(provider => {
            const option = document.createElement('option');
            option.value = provider.provider_id;
            option.textContent = provider.name;
            select.appendChild(option);
        });
    }

    // Restore selected provider
    const selected = getSelectedProvider();
    if (selected) {
        const optionExists = select.querySelector(`option[value="${selected}"]`);
        if (optionExists) {
            select.value = selected;
            // Trigger change to load models
            select.dispatchEvent(new Event('change'));
        } else {
            // Clear stale provider
            setSelectedProvider('');
        }
    }
}

function renderModels(models) {
    const select = document.getElementById('model-select');
    if (!select) return;

    select.innerHTML = '<option value="">Model</option>';

    if (models && models.length > 0) {
        models.forEach(model => {
            const option = document.createElement('option');
            option.value = model.id;
            option.textContent = model.name;
            select.appendChild(option);
        });
        select.disabled = false;
    } else {
        select.disabled = true;
    }

    // Restore selected model
    const selected = getSelectedModel();
    if (selected) {
        const optionExists = select.querySelector(`option[value="${selected}"]`);
        if (optionExists) {
            select.value = selected;
        }
    }
}

// ============================================
// STATUS LINE
// ============================================

function updateStatusLine(status, elapsed = null, usage = null) {
    const statusEl = document.getElementById('status-text');
    const elapsedEl = document.getElementById('elapsed-time');
    const usageEl = document.getElementById('token-usage');

    if (statusEl) statusEl.textContent = status;

    if (elapsedEl) {
        elapsedEl.textContent = elapsed !== null ? `${elapsed}s` : '';
    }

    if (usageEl) {
        if (usage) {
            const parts = [];
            if (usage.prompt_tokens !== undefined) parts.push(`P:${usage.prompt_tokens}`);
            if (usage.completion_tokens !== undefined) parts.push(`C:${usage.completion_tokens}`);
            if (usage.total_tokens !== undefined) parts.push(`T:${usage.total_tokens}`);
            usageEl.textContent = parts.join(' ');
        } else {
            usageEl.textContent = '';
        }
    }
}

// ============================================
// USER DISPLAY
// ============================================

function updateUserDisplay(user) {
    const displays = ['user-display', 'sidebar-user-display', 'admin-user-display'];

    displays.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.textContent = user ? user.username || user.email || 'User' : '';
        }
    });
}

// ============================================
// SETTINGS INPUTS
// ============================================

function updateSettingsInputs() {
    const temp = getTemperature();
    const topP = getTopP();
    const maxTokens = getMaxTokens();

    // Drawer inputs
    const drawerTemp = document.getElementById('drawer-temperature');
    const drawerTempRange = document.getElementById('drawer-temperature-range');
    const drawerTopP = document.getElementById('drawer-top-p');
    const drawerTopPRange = document.getElementById('drawer-top-p-range');
    const drawerMaxTokens = document.getElementById('drawer-max-tokens');

    if (drawerTemp) drawerTemp.value = temp;
    if (drawerTempRange) drawerTempRange.value = temp;
    if (drawerTopP) drawerTopP.value = topP;
    if (drawerTopPRange) drawerTopPRange.value = topP;
    if (drawerMaxTokens) drawerMaxTokens.value = maxTokens || '';

    // Quick controls
    const quickTemp = document.getElementById('quick-temperature');
    const quickTopP = document.getElementById('quick-top-p');
    const quickMaxTokens = document.getElementById('quick-max-tokens');
    const tempDisplay = document.getElementById('temp-display');
    const topPDisplay = document.getElementById('top-p-display');

    if (quickTemp) quickTemp.value = temp;
    if (quickTopP) quickTopP.value = topP;
    if (quickMaxTokens) quickMaxTokens.value = maxTokens || '';
    if (tempDisplay) tempDisplay.textContent = temp.toFixed(1);
    if (topPDisplay) topPDisplay.textContent = topP.toFixed(2);
}

// ============================================
// BUTTON STATES
// ============================================

function enableSendButton() {
    const btn = document.getElementById('send-btn');
    if (btn) btn.disabled = false;
}

function disableSendButton() {
    const btn = document.getElementById('send-btn');
    if (btn) btn.disabled = true;
}

function showCancelButton() {
    const cancelBtn = document.getElementById('cancel-btn');
    const sendBtn = document.getElementById('send-btn');
    if (cancelBtn) cancelBtn.classList.remove('hidden');
    if (sendBtn) sendBtn.classList.add('hidden');
}

function showSendButton() {
    const cancelBtn = document.getElementById('cancel-btn');
    const sendBtn = document.getElementById('send-btn');
    if (cancelBtn) cancelBtn.classList.add('hidden');
    if (sendBtn) sendBtn.classList.remove('hidden');
}

function hideActionButtons() {
    const cancelBtn = document.getElementById('cancel-btn');
    if (cancelBtn) cancelBtn.classList.add('hidden');
}

function clearMessageInput() {
    const input = document.getElementById('message-input');
    if (input) {
        input.value = '';
        input.style.height = 'auto';
    }
}

// ============================================
// FILE EXTENSIONS (for code save)
// ============================================

function getFileExtension(lang) {
    const extensions = {
        javascript: 'js',
        js: 'js',
        typescript: 'ts',
        ts: 'ts',
        python: 'py',
        py: 'py',
        java: 'java',
        cpp: 'cpp',
        c: 'c',
        csharp: 'cs',
        cs: 'cs',
        html: 'html',
        css: 'css',
        json: 'json',
        xml: 'xml',
        yaml: 'yaml',
        yml: 'yml',
        markdown: 'md',
        md: 'md',
        sql: 'sql',
        bash: 'sh',
        shell: 'sh',
        sh: 'sh',
        go: 'go',
        rust: 'rs',
        rs: 'rs',
        php: 'php',
        ruby: 'rb',
        rb: 'rb',
        swift: 'swift',
        kotlin: 'kt',
        kt: 'kt',
        dart: 'dart',
        scala: 'scala',
        perl: 'pl',
        pl: 'pl',
        lua: 'lua',
        r: 'r',
        matlab: 'm',
        julia: 'jl',
        jl: 'jl'
    };
    return extensions[lang?.toLowerCase()] || 'txt';
}

function saveCodeAsFile(code, lang) {
    const extension = getFileExtension(lang);
    const filename = `code.${extension}`;
    const blob = new Blob([code], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);

    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}