// OmniAI WebUI DOM Rendering Helpers

function showView(viewId) {
    document.querySelectorAll('.view').forEach(view => view.classList.add('hidden'));
    document.getElementById(viewId).classList.remove('hidden');
}

function showError(message) {
    const banner = document.getElementById('error-banner');
    const messageEl = document.getElementById('error-message');
    messageEl.textContent = message;
    banner.classList.remove('hidden');
}

function hideError() {
    document.getElementById('error-banner').classList.add('hidden');
}

function showDisconnectBanner() {
    document.getElementById('disconnect-banner').classList.remove('hidden');
}

function hideDisconnectBanner() {
    document.getElementById('disconnect-banner').classList.add('hidden');
}

function renderConversations(conversations) {
    const list = document.getElementById('conversations-list');
    list.innerHTML = '';

    conversations.forEach(conv => {
        const li = document.createElement('li');
        li.dataset.id = conv.id;

        const title = document.createElement('span');
        title.className = 'conversation-title';
        title.textContent = conv.title || 'Untitled Chat';
        title.addEventListener('click', () => selectConversation(conv.id));

        const actions = document.createElement('div');
        actions.className = 'conversation-actions';

        const renameBtn = document.createElement('button');
        renameBtn.textContent = 'Rename';
        renameBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            renameConversation(conv.id, conv.title);
        });

        const deleteBtn = document.createElement('button');
        deleteBtn.textContent = 'Delete';
        deleteBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            deleteConversation(conv.id);
        });

        actions.appendChild(renameBtn);
        actions.appendChild(deleteBtn);

        li.appendChild(title);
        li.appendChild(actions);
        list.appendChild(li);
    });
}

function renderTranscript(messages) {
    const transcript = document.getElementById('transcript');
    transcript.innerHTML = '';

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
        // Add model and timing info if available
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
    }
    header.appendChild(meta);

    // Content section
    const content = document.createElement('div');
    content.className = 'message-content';

    if (msg.role === 'assistant' && msg.content === '') {
        card.classList.add('streaming');
        content.innerHTML = '<div class="skeleton-placeholder">...</div>';
    } else {
        content.innerHTML = renderMessageContent(msg.content);
    }

    // Actions section (hover)
    const actions = document.createElement('div');
    actions.className = 'message-actions';

    if (msg.role === 'assistant') {
        // Copy button
        const copyBtn = document.createElement('button');
        copyBtn.className = 'action-btn copy-btn';
        copyBtn.textContent = '=Ë';
        copyBtn.title = 'Copy message';
        copyBtn.addEventListener('click', () => copyMessageToClipboard(msg.content));

        // Retry button
        const retryBtn = document.createElement('button');
        retryBtn.className = 'action-btn retry-btn';
        retryBtn.textContent = '»';
        retryBtn.title = 'Retry this message';
        retryBtn.addEventListener('click', () => retryMessage(index));

        // Continue button
        const continueBtn = document.createElement('button');
        continueBtn.className = 'action-btn continue-btn';
        continueBtn.textContent = '¤';
        continueBtn.title = 'Continue this message';
        continueBtn.addEventListener('click', () => continueMessage(msg.content));

        // Quote button
        const quoteBtn = document.createElement('button');
        quoteBtn.className = 'action-btn quote-btn';
        quoteBtn.textContent = ']';
        quoteBtn.title = 'Quote to composer';
        quoteBtn.addEventListener('click', () => quoteToComposer(msg.content));

        actions.appendChild(copyBtn);
        actions.appendChild(retryBtn);
        actions.appendChild(continueBtn);
        actions.appendChild(quoteBtn);
    } else {
        // For user messages, just copy
        const copyBtn = document.createElement('button');
        copyBtn.className = 'action-btn copy-btn';
        copyBtn.textContent = '=Ë';
        copyBtn.title = 'Copy message';
        copyBtn.addEventListener('click', () => copyMessageToClipboard(msg.content));

        actions.appendChild(copyBtn);
    }

    card.appendChild(header);
    card.appendChild(content);
    card.appendChild(actions);

    return card;
}

function renderMessageContent(content) {
    if (!content) return '';

    // Process code blocks
    return content
        .replace(/```(\w+)?\n?([\s\S]*?)```/g, (match, lang, code) => {
            const codeBlock = document.createElement('div');
            codeBlock.className = 'code-block';

            const header = document.createElement('div');
            header.className = 'code-header';

            const langLabel = document.createElement('span');
            langLabel.className = 'code-lang';
            langLabel.textContent = lang || 'text';

            const actions = document.createElement('div');
            actions.className = 'code-actions';

            const copyBtn = document.createElement('button');
            copyBtn.className = 'code-copy-btn';
            copyBtn.textContent = 'Copy';
            copyBtn.addEventListener('click', () => {
                navigator.clipboard.writeText(code.trim());
                copyBtn.textContent = 'Copied!';
                setTimeout(() => copyBtn.textContent = 'Copy', 2000);
            });

            const saveBtn = document.createElement('button');
            saveBtn.className = 'code-save-btn';
            saveBtn.textContent = 'Save';
            saveBtn.addEventListener('click', () => saveCodeAsFile(code.trim(), lang || 'txt'));

            actions.appendChild(copyBtn);
            actions.appendChild(saveBtn);

            header.appendChild(langLabel);
            header.appendChild(actions);

            const pre = document.createElement('pre');
            const codeEl = document.createElement('code');
            if (lang) codeEl.className = `language-${lang}`;
            codeEl.textContent = code.trim();

            pre.appendChild(codeEl);
            codeBlock.appendChild(header);
            codeBlock.appendChild(pre);

            return codeBlock.outerHTML;
        })
        .replace(/\n/g, '<br>');
}

function copyMessageToClipboard(content) {
    navigator.clipboard.writeText(content).catch(err => {
        console.error('Failed to copy:', err);
        // Fallback for older browsers
        const textArea = document.createElement('textarea');
        textArea.value = content;
        document.body.appendChild(textArea);
        textArea.select();
        document.execCommand('copy');
        document.body.removeChild(textArea);
    });
}

function retryMessage(messageIndex) {
    // This will be connected to the app logic
    if (window.retryMessageAtIndex) {
        window.retryMessageAtIndex(messageIndex);
    }
}

function continueMessage(content) {
    // Insert content into composer for continuation
    const input = document.getElementById('message-input');
    input.value = content + '\n\n';
    input.focus();
    input.setSelectionRange(input.value.length, input.value.length);
}

function quoteToComposer(content) {
    // Insert quoted content into composer
    const input = document.getElementById('message-input');
    const quote = '> ' + content.replace(/\n/g, '\n> ') + '\n\n';
    input.value += quote;
    input.focus();
    input.setSelectionRange(input.value.length, input.value.length);
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

function getFileExtension(lang) {
    const extensions = {
        javascript: 'js',
        python: 'py',
        java: 'java',
        cpp: 'cpp',
        c: 'c',
        html: 'html',
        css: 'css',
        json: 'json',
        xml: 'xml',
        yaml: 'yaml',
        yml: 'yml',
        markdown: 'md',
        sql: 'sql',
        bash: 'sh',
        shell: 'sh',
        typescript: 'ts',
        go: 'go',
        rust: 'rs',
        php: 'php',
        ruby: 'rb',
        swift: 'swift',
        kotlin: 'kt',
        dart: 'dart',
        scala: 'scala',
        perl: 'pl',
        lua: 'lua',
        r: 'r',
        matlab: 'm',
        julia: 'jl'
    };
    return extensions[lang] || 'txt';
}

function appendToLastMessage(content) {
    const transcript = document.getElementById('transcript');
    const lastMessage = transcript.lastElementChild;
    if (lastMessage && lastMessage.classList.contains('assistant')) {
        lastMessage.innerHTML += content.replace(/\n/g, '<br>');
        transcript.scrollTop = transcript.scrollHeight;
    }
}

function finalizeLastMessage() {
    const transcript = document.getElementById('transcript');
    const lastMessage = transcript.lastElementChild;
    if (lastMessage && lastMessage.classList.contains('streaming')) {
        lastMessage.classList.remove('streaming');
    }
}

function renderProviders(providers) {
    const select = document.getElementById('provider-select');
    select.innerHTML = '<option value="">Select Provider</option>';

    providers.forEach(provider => {
        const option = document.createElement('option');
        option.value = provider.provider_id;
        option.textContent = provider.name;
        select.appendChild(option);
    });

    // Restore selected provider and trigger change to load models
    const selected = getSelectedProvider();
    if (selected) {
        const optionExists = select.querySelector(`option[value="${selected}"]`);
        if (optionExists) {
            select.value = selected;
            // Dispatch change event to trigger model loading
            select.dispatchEvent(new Event('change'));
        } else {
            // Clear stale provider from storage
            setSelectedProvider('');
        }
    }
}

function renderModels(models) {
    const select = document.getElementById('model-select');
    select.innerHTML = '<option value="">Select Model</option>';

    models.forEach(model => {
        const option = document.createElement('option');
        option.value = model.id;
        option.textContent = model.name;
        select.appendChild(option);
    });

    // Restore selected model
    const selected = getSelectedModel();
    if (selected) {
        select.value = selected;
    }

    select.disabled = models.length === 0;
}

function updateStatusLine(status, elapsed = null, usage = null) {
    const statusEl = document.getElementById('status-text');
    const elapsedEl = document.getElementById('elapsed-time');
    const usageEl = document.getElementById('token-usage');

    statusEl.textContent = status;

    if (elapsed !== null) {
        elapsedEl.textContent = `${elapsed}s`;
    } else {
        elapsedEl.textContent = '';
    }

    if (usage) {
        const parts = [];
        if (usage.prompt_tokens !== undefined) parts.push(`Prompt: ${usage.prompt_tokens}`);
        if (usage.completion_tokens !== undefined) parts.push(`Completion: ${usage.completion_tokens}`);
        if (usage.total_tokens !== undefined) parts.push(`Total: ${usage.total_tokens}`);
        usageEl.textContent = parts.join(' | ');
    } else {
        usageEl.textContent = '';
    }
}

function updateUserDisplay(user) {
    const display = document.getElementById('user-display');
    display.textContent = user ? user.username || user.email || 'User' : '';
}

function updateSettingsInputs() {
    document.getElementById('temperature').value = getTemperature();
    document.getElementById('top-p').value = getTopP();
    const maxTokens = getMaxTokens();
    document.getElementById('max-tokens').value = maxTokens || '';
}

function enableSendButton() {
    document.getElementById('send-btn').disabled = false;
}

function disableSendButton() {
    document.getElementById('send-btn').disabled = true;
}

function showCancelButton() {
    document.getElementById('cancel-btn').classList.remove('hidden');
    document.getElementById('retry-btn').classList.add('hidden');
}

function showRetryButton() {
    document.getElementById('cancel-btn').classList.add('hidden');
    document.getElementById('retry-btn').classList.remove('hidden');
}

function hideActionButtons() {
    document.getElementById('cancel-btn').classList.add('hidden');
    document.getElementById('retry-btn').classList.add('hidden');
}

function clearMessageInput() {
    document.getElementById('message-input').value = '';
}