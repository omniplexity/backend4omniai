// OmniAI Prompt Dock

class PromptDock {
    constructor() {
        this.templates = [
            {
                name: 'Code Review',
                content: 'Please review this code and provide feedback on:\n- Code quality and best practices\n- Potential bugs or issues\n- Performance considerations\n- Security concerns\n- Suggestions for improvement\n\nCode to review:\n```'
            },
            {
                name: 'Bug Report',
                content: 'I\'m experiencing a bug with the following details:\n\n**Steps to reproduce:**\n1. \n2. \n3. \n\n**Expected behavior:**\n\n**Actual behavior:**\n\n**Environment:**\n- Browser: \n- OS: \n- Device: \n\n**Additional context:**'
            },
            {
                name: 'Feature Request',
                content: 'I would like to request a new feature:\n\n**Feature description:**\n\n**Use case:**\n\n**Benefits:**\n\n**Additional details:**'
            },
            {
                name: 'Explain Code',
                content: 'Please explain what this code does:\n\n```'
            },
            {
                name: 'Refactor',
                content: 'Please refactor this code to improve:\n- Readability\n- Maintainability\n- Performance\n\nOriginal code:\n```'
            },
            {
                name: 'Unit Tests',
                content: 'Please write comprehensive unit tests for this code:\n\n```'
            },
            {
                name: 'Documentation',
                content: 'Please generate documentation for this code/module:\n\n```'
            },
            {
                name: 'API Design',
                content: 'I need help designing an API for:\n\n**Requirements:**\n\n**Endpoints needed:**\n\n**Data models:**\n\n**Authentication:**'
            }
        ];

        this.savedPrompts = [];
        this.init();
    }

    init() {
        this.loadSavedPrompts();
        this.renderTemplates();
        this.renderSavedPrompts();
        this.bindEvents();
    }

    loadSavedPrompts() {
        const saved = localStorage.getItem('savedPrompts');
        if (saved) {
            try {
                this.savedPrompts = JSON.parse(saved);
            } catch (e) {
                console.error('Failed to load saved prompts:', e);
                this.savedPrompts = [];
            }
        }
    }

    saveSavedPrompts() {
        localStorage.setItem('savedPrompts', JSON.stringify(this.savedPrompts));
    }

    renderTemplates() {
        const container = document.getElementById('prompt-templates');
        if (!container) {
            console.error('Prompt templates container not found');
            return;
        }
        container.innerHTML = '';

        this.templates.forEach((template, index) => {
            const chip = document.createElement('button');
            chip.className = 'prompt-chip';
            chip.textContent = template.name;
            chip.title = template.content.substring(0, 100) + '...';
            chip.addEventListener('click', (e) => this.insertTemplate(template, e.shiftKey));
            container.appendChild(chip);
        });
    }

    renderSavedPrompts() {
        const container = document.getElementById('saved-prompts-list');
        if (!container) {
            console.error('Saved prompts container not found');
            return;
        }
        container.innerHTML = '';

        if (this.savedPrompts.length === 0) {
            container.innerHTML = '<p class="no-prompts">No saved prompts yet. Save your current message as a prompt above.</p>';
            return;
        }

        this.savedPrompts.forEach((prompt, index) => {
            const item = document.createElement('div');
            item.className = 'saved-prompt-item';

            const header = document.createElement('div');
            header.className = 'saved-prompt-header';

            const name = document.createElement('span');
            name.className = 'saved-prompt-name';
            name.textContent = prompt.name;

            const actions = document.createElement('div');
            actions.className = 'saved-prompt-actions';

            const insertBtn = document.createElement('button');
            insertBtn.className = 'saved-prompt-btn insert-btn';
            insertBtn.textContent = 'Insert';
            insertBtn.title = 'Insert into composer';
            insertBtn.addEventListener('click', (e) => this.insertSavedPrompt(prompt, e.shiftKey));

            const editBtn = document.createElement('button');
            editBtn.className = 'saved-prompt-btn edit-btn';
            editBtn.textContent = 'Edit';
            editBtn.title = 'Edit prompt';
            editBtn.addEventListener('click', () => this.editSavedPrompt(index));

            const deleteBtn = document.createElement('button');
            deleteBtn.className = 'saved-prompt-btn delete-btn';
            deleteBtn.textContent = 'Delete';
            deleteBtn.title = 'Delete prompt';
            deleteBtn.addEventListener('click', () => this.deleteSavedPrompt(index));

            actions.appendChild(insertBtn);
            actions.appendChild(editBtn);
            actions.appendChild(deleteBtn);

            header.appendChild(name);
            header.appendChild(actions);

            const preview = document.createElement('div');
            preview.className = 'saved-prompt-preview';
            preview.textContent = prompt.content.length > 100
                ? prompt.content.substring(0, 100) + '...'
                : prompt.content;

            item.appendChild(header);
            item.appendChild(preview);
            container.appendChild(item);
        });
    }

    bindEvents() {
        document.getElementById('save-prompt-btn').addEventListener('click', () => {
            this.saveCurrentPrompt();
        });

        document.getElementById('new-prompt-name').addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                this.saveCurrentPrompt();
            }
        });
    }

    insertTemplate(template, sendImmediately = false) {
        const input = document.getElementById('message-input');
        const cursorPos = input.selectionStart;
        const textBefore = input.value.substring(0, cursorPos);
        const textAfter = input.value.substring(cursorPos);

        input.value = textBefore + template.content + textAfter;
        input.focus();

        // Position cursor after inserted text
        const newCursorPos = cursorPos + template.content.length;
        input.setSelectionRange(newCursorPos, newCursorPos);

        if (sendImmediately) {
            // Trigger send after a brief delay to allow UI update
            setTimeout(() => {
                if (window.sendMessage) {
                    window.sendMessage();
                }
            }, 100);
        }
    }

    insertSavedPrompt(prompt, sendImmediately = false) {
        const input = document.getElementById('message-input');
        const cursorPos = input.selectionStart;
        const textBefore = input.value.substring(0, cursorPos);
        const textAfter = input.value.substring(cursorPos);

        input.value = textBefore + prompt.content + textAfter;
        input.focus();

        // Position cursor after inserted text
        const newCursorPos = cursorPos + prompt.content.length;
        input.setSelectionRange(newCursorPos, newCursorPos);

        if (sendImmediately) {
            // Trigger send after a brief delay to allow UI update
            setTimeout(() => {
                if (window.sendMessage) {
                    window.sendMessage();
                }
            }, 100);
        }
    }

    saveCurrentPrompt() {
        const nameInput = document.getElementById('new-prompt-name');
        const name = nameInput.value.trim();

        if (!name) {
            alert('Please enter a name for the prompt.');
            nameInput.focus();
            return;
        }

        const input = document.getElementById('message-input');
        const content = input.value.trim();

        if (!content) {
            alert('Please enter some content in the message input to save as a prompt.');
            input.focus();
            return;
        }

        // Check if name already exists
        const existingIndex = this.savedPrompts.findIndex(p => p.name.toLowerCase() === name.toLowerCase());
        if (existingIndex !== -1) {
            if (!confirm(`A prompt named "${name}" already exists. Replace it?`)) {
                return;
            }
            this.savedPrompts[existingIndex] = { name, content };
        } else {
            this.savedPrompts.push({ name, content });
        }

        this.saveSavedPrompts();
        this.renderSavedPrompts();
        nameInput.value = '';

        // Show success message
        if (window.showToast) {
            window.showToast('Prompt saved successfully!', 'success');
        }
    }

    editSavedPrompt(index) {
        const prompt = this.savedPrompts[index];
        const newName = prompt('Edit prompt name:', prompt.name);

        if (newName === null) return; // Cancelled

        const trimmedName = newName.trim();
        if (!trimmedName) {
            alert('Prompt name cannot be empty.');
            return;
        }

        // Check for name conflicts
        const existingIndex = this.savedPrompts.findIndex((p, i) => i !== index && p.name.toLowerCase() === trimmedName.toLowerCase());
        if (existingIndex !== -1) {
            alert(`A prompt named "${trimmedName}" already exists.`);
            return;
        }

        prompt.name = trimmedName;
        this.saveSavedPrompts();
        this.renderSavedPrompts();
    }

    deleteSavedPrompt(index) {
        if (confirm(`Delete prompt "${this.savedPrompts[index].name}"?`)) {
            this.savedPrompts.splice(index, 1);
            this.saveSavedPrompts();
            this.renderSavedPrompts();
        }
    }
}

// Initialize prompt dock after DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.promptDock = new PromptDock();
});