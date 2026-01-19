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

        const actions = document.createElement('div');
        actions.className = 'conversation-actions';

        const renameBtn = document.createElement('button');
        renameBtn.textContent = 'Rename';
        renameBtn.className = 'rename-conversation-btn';

        const deleteBtn = document.createElement('button');
        deleteBtn.textContent = 'Delete';
        deleteBtn.className = 'delete-conversation-btn';

        actions.appendChild(renameBtn);
        actions.appendChild(deleteBtn);

        li.appendChild(title);
        li.appendChild(actions);
        list.appendChild(li);
    });
}

// Event delegation for conversation actions
document.getElementById('conversations-list').addEventListener('click', (e) => {
    const li = e.target.closest('li');
    if (!li) return;

    const convId = li.dataset.id;

    if (e.target.classList.contains('conversation-title')) {
        selectConversation(convId);
    } else if (e.target.classList.contains('rename-conversation-btn')) {
        e.stopPropagation();
        renameConversation(convId, li.querySelector('.conversation-title').textContent);
    } else if (e.target.classList.contains('delete-conversation-btn')) {
        e.stopPropagation();
        deleteConversation(convId);
    }
});

function renderTranscript(messages) {
    const transcript = document.getElementById('transcript');
    transcript.innerHTML = '';

    messages.forEach(msg => {
        const messageEl = document.createElement('div');
        messageEl.className = `message ${msg.role}`;
        messageEl.dataset.messageId = msg.id;

        if (msg.role === 'assistant' && msg.content === '') {
            messageEl.classList.add('streaming');
            messageEl.textContent = '...';
        } else {
            messageEl.innerHTML = msg.content.replace(/\n/g, '<br>');
        }

        // Add receipt for assistant messages
        if (msg.role === 'assistant' && msg.metadata) {
            const receipt = document.createElement('div');
            receipt.className = 'message-receipt collapsed';
            receipt.innerHTML = `
                <div class="receipt-line">
                    <span class="receipt-text">Run details</span>
                    <button class="receipt-toggle" aria-label="Toggle run details">¼</button>
                </div>
                <div class="receipt-expanded hidden">
                    <button class="receipt-re-run">Re-run with same settings</button>
                    <button class="receipt-copy-json">Copy Run JSON</button>
                    ${msg.metadata.request_id ? `<button class="receipt-copy-id">Copy Request ID</button>` : ''}
                </div>
            `;
            messageEl.appendChild(receipt);
        }

        transcript.appendChild(messageEl);
    });

    // Scroll to bottom
    transcript.scrollTop = transcript.scrollHeight;
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