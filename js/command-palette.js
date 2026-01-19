// OmniAI Command Palette

class CommandPalette {
    constructor() {
        this.isOpen = false;
        this.actions = [];
        this.filteredActions = [];
        this.selectedIndex = 0;
        this.query = '';

        this.init();
    }

    init() {
        this.createElements();
        this.registerActions();
        this.bindEvents();
    }

    createElements() {
        // Create modal overlay
        this.overlay = document.createElement('div');
        this.overlay.className = 'command-palette-overlay hidden';
        this.overlay.setAttribute('role', 'dialog');
        this.overlay.setAttribute('aria-modal', 'true');
        this.overlay.setAttribute('aria-labelledby', 'command-palette-title');

        // Create modal content
        this.modal = document.createElement('div');
        this.modal.className = 'command-palette-modal';

        // Title (hidden for screen readers)
        const title = document.createElement('h2');
        title.id = 'command-palette-title';
        title.className = 'sr-only';
        title.textContent = 'Command Palette';
        this.modal.appendChild(title);

        // Input field
        this.input = document.createElement('input');
        this.input.type = 'text';
        this.input.className = 'command-palette-input';
        this.input.placeholder = 'Type a command...';
        this.input.setAttribute('aria-label', 'Command search');
        this.modal.appendChild(this.input);

        // Results list
        this.resultsList = document.createElement('ul');
        this.resultsList.className = 'command-palette-results';
        this.resultsList.setAttribute('role', 'listbox');
        this.modal.appendChild(this.resultsList);

        // Hints
        const hints = document.createElement('div');
        hints.className = 'command-palette-hints';
        hints.innerHTML = `
            <span>↑↓ Navigate</span>
            <span>↵ Select</span>
            <span>⎋ Close</span>
        `;
        this.modal.appendChild(hints);

        this.overlay.appendChild(this.modal);
        document.body.appendChild(this.overlay);
    }

    registerActions() {
        // Load MRU actions from localStorage
        this.mruActions = this.loadMRUActions();

        this.actions = [
            {
                id: 'new-chat',
                title: 'New Chat',
                description: 'Start a new conversation',
                icon: '➕',
                action: () => this.executeAction('new-chat')
            },
            {
                id: 'toggle-focus-mode',
                title: 'Toggle Focus Mode',
                description: 'Hide sidebar for distraction-free writing',
                icon: '🎯',
                action: () => this.executeAction('toggle-focus-mode')
            },
            {
                id: 'open-settings',
                title: 'Open Settings',
                description: 'Open the settings drawer',
                icon: '⚙️',
                action: () => this.executeAction('open-settings')
            },
            {
                id: 'search-messages',
                title: 'Search messages in thread',
                description: 'Search within current conversation',
                icon: '🔍',
                action: () => this.executeAction('search-messages')
            },
            {
                id: 'copy-diagnostics',
                title: 'Copy Diagnostics',
                description: 'Copy last request ID for debugging',
                icon: '📋',
                action: () => this.executeAction('copy-diagnostics')
            },
            {
                id: 'cancel-generation',
                title: 'Cancel Generation',
                description: 'Stop current AI response',
                icon: '⏹️',
                action: () => this.executeAction('cancel-generation')
            }
        ];

        // Add conversation switching actions
        this.updateConversationActions();
        // Add model switching actions
        this.updateModelActions();
    }

    updateConversationActions() {
        // Remove existing conversation actions
        this.actions = this.actions.filter(action => !action.id.startsWith('switch-to-'));

        // Add current conversations
        if (window.getConversationsList) {
            const conversations = window.getConversationsList();
            conversations.slice(0, 10).forEach((conv, index) => {
                this.actions.push({
                    id: `switch-to-${conv.id}`,
                    title: `Switch to: ${conv.title || 'Untitled'}`,
                    description: 'Switch to this conversation',
                    icon: '💬',
                    action: () => this.executeAction('switch-to', conv.id)
                });
            });
        }
    }

    updateModelActions() {
        // Remove existing model actions
        this.actions = this.actions.filter(action => !action.id.startsWith('switch-model-to-'));

        // Add recent models from localStorage
        const recentModels = this.loadRecentModels();
        recentModels.forEach(model => {
            this.actions.push({
                id: `switch-model-to-${model.providerId}-${model.modelId}`,
                title: `Switch model to ${model.name}`,
                description: `Switch to ${model.providerName} - ${model.name}`,
                icon: '🤖',
                action: () => this.executeAction('switch-model-to', model.providerId, model.modelId)
            });
        });
    }

    bindEvents() {
        // Global keyboard shortcut - Ctrl+K (avoid Ctrl+P print conflict)
        document.addEventListener('keydown', (e) => {
            // Ignore shortcuts when focus is in input/textarea/contenteditable
            const activeElement = document.activeElement;
            const isInInput = activeElement && (
                activeElement.tagName === 'INPUT' ||
                activeElement.tagName === 'TEXTAREA' ||
                activeElement.contentEditable === 'true'
            );

            // Allow Esc to close palette even in inputs
            if (e.key === 'Escape') {
                if (this.isOpen) {
                    e.preventDefault();
                    this.close();
                }
                return;
            }

            // Allow Ctrl+. to cancel streaming even in inputs
            if ((e.ctrlKey || e.metaKey) && e.key === '.') {
                if (window.cancelStreaming) {
                    e.preventDefault();
                    window.cancelStreaming();
                }
                return;
            }

            // Skip other shortcuts if in input field
            if (isInInput) return;

            // Ctrl+K to open palette (primary)
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                e.preventDefault();
                this.toggle();
                return;
            }

            // Ctrl+Shift+P as secondary shortcut
            if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'P') {
                e.preventDefault();
                this.toggle();
                return;
            }
        });

        // Input events
        this.input.addEventListener('input', (e) => {
            this.query = e.target.value.toLowerCase();
            this.filterActions();
            this.selectedIndex = 0;
            this.renderResults();
        });

        this.input.addEventListener('keydown', (e) => {
            switch (e.key) {
                case 'ArrowDown':
                    e.preventDefault();
                    this.selectedIndex = Math.min(this.selectedIndex + 1, this.filteredActions.length - 1);
                    this.renderResults();
                    break;
                case 'ArrowUp':
                    e.preventDefault();
                    this.selectedIndex = Math.max(this.selectedIndex - 1, 0);
                    this.renderResults();
                    break;
                case 'Enter':
                    e.preventDefault();
                    this.executeSelectedAction();
                    break;
                case 'Escape':
                    e.preventDefault();
                    this.close();
                    break;
            }
        });

        // Click outside to close
        this.overlay.addEventListener('click', (e) => {
            if (e.target === this.overlay) {
                this.close();
            }
        });
    }

    toggle() {
        if (this.isOpen) {
            this.close();
        } else {
            this.open();
        }
    }

    open() {
        if (this.isOpen) return;

        this.isOpen = true;
        this.query = '';
        this.selectedIndex = 0;
        this.updateConversationActions();
        this.updateModelActions();
        this.filteredActions = [...this.actions];
        this.overlay.classList.remove('hidden');
        this.input.value = '';
        this.input.focus();
        this.renderResults();

        // Trap focus
        this.focusTrap();
    }

    close() {
        if (!this.isOpen) return;

        this.isOpen = false;
        this.overlay.classList.add('hidden');

        // Restore focus
        if (this.previousFocus) {
            this.previousFocus.focus();
        }
    }

    focusTrap() {
        this.previousFocus = document.activeElement;

        const focusableElements = this.overlay.querySelectorAll(
            'input, button, [tabindex]:not([tabindex="-1"])'
        );

        const firstElement = focusableElements[0];
        const lastElement = focusableElements[focusableElements.length - 1];

        this.overlay.addEventListener('keydown', (e) => {
            if (e.key === 'Tab') {
                if (e.shiftKey) {
                    if (document.activeElement === firstElement) {
                        e.preventDefault();
                        lastElement.focus();
                    }
                } else {
                    if (document.activeElement === lastElement) {
                        e.preventDefault();
                        firstElement.focus();
                    }
                }
            }
        });
    }

    filterActions() {
        if (!this.query) {
            // Show MRU actions first, then regular actions
            const mruActions = this.mruActions.map(mru =>
                this.actions.find(a => a.id === mru.id) || mru
            ).filter(Boolean);

            const otherActions = this.actions.filter(a => !this.mruActions.some(mru => mru.id === a.id));

            this.filteredActions = [...mruActions, ...otherActions];
            return;
        }

        this.filteredActions = this.actions.filter(action =>
            action.title.toLowerCase().includes(this.query) ||
            (action.description && action.description.toLowerCase().includes(this.query))
        );
    }

    renderResults() {
        this.resultsList.innerHTML = '';

        this.filteredActions.forEach((action, index) => {
            const li = document.createElement('li');
            li.className = `command-palette-result ${index === this.selectedIndex ? 'selected' : ''}`;
            li.setAttribute('role', 'option');
            li.setAttribute('aria-selected', index === this.selectedIndex);

            li.innerHTML = `
                <div class="command-palette-result-icon">${action.icon}</div>
                <div class="command-palette-result-content">
                    <div class="command-palette-result-title">${this.highlightMatch(action.title)}</div>
                    <div class="command-palette-result-description">${action.description || ''}</div>
                </div>
            `;

            li.addEventListener('click', () => {
                this.selectedIndex = index;
                this.executeSelectedAction();
            });

            li.addEventListener('mouseenter', () => {
                this.selectedIndex = index;
                this.renderResults();
            });

            this.resultsList.appendChild(li);
        });
    }

    highlightMatch(text) {
        if (!this.query) return text;
        const regex = new RegExp(`(${this.query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
        return text.replace(regex, '<mark>$1</mark>');
    }

    executeSelectedAction() {
        const action = this.filteredActions[this.selectedIndex];
        if (action) {
            // Add to MRU list
            this.addToMRU(action);

            action.action();
            this.close();
        }
    }

    addToMRU(action) {
        // Remove if already exists
        this.mruActions = this.mruActions.filter(a => a.id !== action.id);

        // Add to beginning
        this.mruActions.unshift({
            id: action.id,
            title: action.title,
            description: action.description,
            icon: action.icon
        });

        // Keep only last 10
        this.mruActions = this.mruActions.slice(0, 10);

        // Save to localStorage
        localStorage.setItem('commandPaletteMRU', JSON.stringify(this.mruActions));
    }

    loadMRUActions() {
        try {
            const stored = localStorage.getItem('commandPaletteMRU');
            return stored ? JSON.parse(stored) : [];
        } catch {
            return [];
        }
    }

    loadRecentModels() {
        try {
            const stored = localStorage.getItem('recentModels');
            return stored ? JSON.parse(stored) : [];
        } catch {
            return [];
        }
    }

    addRecentModel(providerId, modelId, modelName, providerName) {
        const recentModels = this.loadRecentModels();
        // Remove if already exists
        const filtered = recentModels.filter(m => !(m.providerId === providerId && m.modelId === modelId));
        // Add to beginning
        filtered.unshift({ providerId, modelId, name: modelName, providerName });
        // Keep only last 5
        const updated = filtered.slice(0, 5);
        localStorage.setItem('recentModels', JSON.stringify(updated));
    }

    executeAction(actionId, ...args) {
        switch (actionId) {
            case 'new-chat':
                if (window.createNewConversation) {
                    window.createNewConversation();
                }
                break;
            case 'toggle-focus-mode':
                this.toggleFocusMode();
                break;
            case 'open-settings':
                if (window.openSettingsDrawer) {
                    window.openSettingsDrawer();
                }
                break;
            case 'search-messages':
                this.searchMessagesInThread();
                break;
            case 'copy-diagnostics':
                this.copyDiagnostics();
                break;
            case 'cancel-generation':
                if (window.cancelStreaming) {
                    window.cancelStreaming();
                }
                break;
            case 'switch-to':
                if (window.selectConversation && args[0]) {
                    window.selectConversation(args[0]);
                }
                break;
            case 'switch-model-to':
                if (args[0] && args[1]) {
                    this.switchToModel(args[0], args[1]);
                }
                break;
        }
    }

    switchToModel(providerId, modelId) {
        // Set provider
        const providerSelect = document.getElementById('provider-select');
        providerSelect.value = providerId;
        providerSelect.dispatchEvent(new Event('change'));

        // Set model after models are loaded
        setTimeout(() => {
            const modelSelect = document.getElementById('model-select');
            modelSelect.value = modelId;
            modelSelect.dispatchEvent(new Event('change'));
        }, 100);
    }

    toggleFocusMode() {
        const sidebar = document.getElementById('sidebar');
        const main = document.getElementById('main');

        if (sidebar.classList.contains('hidden')) {
            // Exit focus mode
            sidebar.classList.remove('hidden');
            main.style.marginLeft = '';
            localStorage.setItem('focusMode', 'false');
        } else {
            // Enter focus mode
            sidebar.classList.add('hidden');
            main.style.marginLeft = '0';
            localStorage.setItem('focusMode', 'true');
        }
    }

    searchMessagesInThread() {
        const query = prompt('Search messages in thread:');
        if (!query || !query.trim()) return;

        const transcript = document.getElementById('transcript');
        const messages = transcript.querySelectorAll('.message');
        let found = false;

        messages.forEach(message => {
            const text = message.textContent.toLowerCase();
            if (text.includes(query.toLowerCase())) {
                message.classList.add('search-highlight');
                if (!found) {
                    message.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    found = true;
                }
            } else {
                message.classList.remove('search-highlight');
            }
        });

        if (!found) {
            alert('No messages found matching: ' + query);
        }
    }

    copyDiagnostics() {
        const diagnostics = {
            lastRequestId: window.lastRequestId || 'N/A',
            lastError: window.lastError || 'N/A',
            timestamp: new Date().toISOString()
        };

        navigator.clipboard.writeText(JSON.stringify(diagnostics, null, 2))
            .then(() => {
                // Show success toast
                if (window.showToast) {
                    window.showToast('Diagnostics copied to clipboard', 'success');
                }
            })
            .catch(err => {
                console.error('Failed to copy diagnostics:', err);
            });
    }
}

function initCommandPalette() {
  if (document.body?.dataset?.page !== "chat") return;
  if (window.commandPalette) return;
  window.commandPalette = new CommandPalette();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initCommandPalette, { once: true });
} else {
  initCommandPalette();
}