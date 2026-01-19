// OmniAI Admin Panel

let currentAdminSection = 'users';

// Admin data loading
async function loadAdminData() {
    const user = getCurrentUser();
    document.getElementById('admin-user-display').textContent = user.username;

    // Load initial data based on current section
    switch (currentAdminSection) {
        case 'users':
            await loadUsers();
            break;
        case 'invites':
            await loadInvites();
            break;
        case 'audit':
            await loadAuditLog();
            break;
        case 'quotas':
            await loadQuotas();
            break;
    }
}

async function loadUsers() {
    try {
        const response = await fetch(`${getApiBaseUrl()}/admin/users`, {
            method: 'GET',
            headers: getAuthHeaders()
        });
        const data = await handleApiResponse(response);
        renderUsers(data.users);
    } catch (error) {
        showError('Failed to load users: ' + error.message);
    }
}

async function loadInvites() {
    try {
        const response = await fetch(`${getApiBaseUrl()}/admin/invites`, {
            method: 'GET',
            headers: getAuthHeaders()
        });
        const data = await handleApiResponse(response);
        renderInvites(data.invites);
    } catch (error) {
        showError('Failed to load invites: ' + error.message);
    }
}

async function loadAuditLog(q = '', action = '', since = '') {
    try {
        const params = new URLSearchParams();
        if (q) params.append('q', q);
        if (action) params.append('action', action);
        if (since) params.append('since', since);

        const response = await fetch(`${getApiBaseUrl()}/admin/audit?${params}`, {
            method: 'GET',
            headers: getAuthHeaders()
        });
        const data = await handleApiResponse(response);
        renderAuditLog(data.entries);
    } catch (error) {
        showError('Failed to load audit log: ' + error.message);
    }
}

async function loadQuotas() {
    try {
        // First load users to get user info
        const usersResponse = await fetch(`${getApiBaseUrl()}/admin/users`, {
            method: 'GET',
            headers: getAuthHeaders()
        });
        const usersData = await handleApiResponse(usersResponse);

        // Load quotas for each user
        const quotas = [];
        for (const user of usersData.users) {
            try {
                const quotaResponse = await fetch(`${getApiBaseUrl()}/admin/quotas/${user.id}`, {
                    method: 'GET',
                    headers: getAuthHeaders()
                });
                const quotaData = await handleApiResponse(quotaResponse);
                quotas.push({ ...quotaData, username: user.username });
            } catch (e) {
                // If no quota set, use defaults
                quotas.push({
                    user_id: user.id,
                    username: user.username,
                    messages_per_day: 100, // default
                    tokens_per_day: 10000, // default
                    updated_at: null
                });
            }
        }
        renderQuotas(quotas);
    } catch (error) {
        showError('Failed to load quotas: ' + error.message);
    }
}

// Rendering functions
function renderUsers(users) {
    const tbody = document.getElementById('users-tbody');
    tbody.innerHTML = '';

    users.forEach(user => {
        const row = document.createElement('tr');

        row.innerHTML = `
            <td>${user.id}</td>
            <td>${escapeHtml(user.username)}</td>
            <td>${escapeHtml(user.display_name || '')}</td>
            <td>${user.role}</td>
            <td>${user.status}</td>
            <td>${new Date(user.created_at).toLocaleDateString()}</td>
            <td>${user.last_login ? new Date(user.last_login).toLocaleDateString() : 'Never'}</td>
            <td>
                <select onchange="changeUserStatus(${user.id}, this.value)">
                    <option value="active" ${user.status === 'active' ? 'selected' : ''}>Active</option>
                    <option value="disabled" ${user.status === 'disabled' ? 'selected' : ''}>Disabled</option>
                </select>
                <select onchange="changeUserRole(${user.id}, this.value)">
                    <option value="user" ${user.role === 'user' ? 'selected' : ''}>User</option>
                    <option value="admin" ${user.role === 'admin' ? 'selected' : ''}>Admin</option>
                </select>
            </td>
        `;

        tbody.appendChild(row);
    });
}

function renderInvites(invites) {
    const tbody = document.getElementById('invites-tbody');
    tbody.innerHTML = '';

    invites.forEach(invite => {
        const row = document.createElement('tr');

        row.innerHTML = `
            <td>${escapeHtml(invite.code)}</td>
            <td>${invite.created_by}</td>
            <td>${invite.used_by || 'Not used'}</td>
            <td>${new Date(invite.expires_at).toLocaleString()}</td>
            <td>${invite.revoked_at ? new Date(invite.revoked_at).toLocaleString() : 'No'}</td>
            <td>${new Date(invite.created_at).toLocaleDateString()}</td>
            <td>
                ${!invite.revoked_at && !invite.used_by ? `<button onclick="revokeInvite('${invite.code}')">Revoke</button>` : ''}
            </td>
        `;

        tbody.appendChild(row);
    });
}

function renderAuditLog(entries) {
    const tbody = document.getElementById('audit-tbody');
    tbody.innerHTML = '';

    entries.forEach(entry => {
        const row = document.createElement('tr');

        row.innerHTML = `
            <td>${entry.id}</td>
            <td>${entry.action}</td>
            <td>${escapeHtml(entry.target)}</td>
            <td>${entry.actor_user_id}</td>
            <td>${entry.ip}</td>
            <td>${new Date(entry.created_at).toLocaleString()}</td>
        `;

        tbody.appendChild(row);
    });
}

function renderQuotas(quotas) {
    const tbody = document.getElementById('quotas-tbody');
    tbody.innerHTML = '';

    quotas.forEach(quota => {
        const row = document.createElement('tr');

        row.innerHTML = `
            <td>${quota.user_id}</td>
            <td>${escapeHtml(quota.username)}</td>
            <td><input type="number" value="${quota.messages_per_day}" onchange="updateQuota(${quota.user_id}, 'messages_per_day', this.value)"></td>
            <td><input type="number" value="${quota.tokens_per_day}" onchange="updateQuota(${quota.user_id}, 'tokens_per_day', this.value)"></td>
            <td>${quota.updated_at ? new Date(quota.updated_at).toLocaleString() : 'Default'}</td>
            <td><button onclick="saveQuota(${quota.user_id})">Save</button></td>
        `;

        tbody.appendChild(row);
    });
}

// Action handlers
async function changeUserStatus(userId, status) {
    try {
        const response = await fetch(`${getApiBaseUrl()}/admin/users/${userId}`, {
            method: 'PATCH',
            headers: getAuthHeaders(),
            body: JSON.stringify({ status })
        });
        await handleApiResponse(response);
        showSuccess('User status updated');
        await loadUsers();
    } catch (error) {
        showError('Failed to update user status: ' + error.message);
    }
}

async function changeUserRole(userId, role) {
    try {
        const response = await fetch(`${getApiBaseUrl()}/admin/users/${userId}`, {
            method: 'PATCH',
            headers: getAuthHeaders(),
            body: JSON.stringify({ role })
        });
        await handleApiResponse(response);
        showSuccess('User role updated');
        await loadUsers();
    } catch (error) {
        showError('Failed to update user role: ' + error.message);
    }
}

async function createInvite() {
    const hours = prompt('Enter expiration time in hours:', '24');
    if (!hours) return;

    try {
        const response = await fetch(`${getApiBaseUrl()}/admin/invites`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ expires_in_hours: parseInt(hours) })
        });
        const data = await handleApiResponse(response);
        showSuccess(`Invite created: ${data.invite_code}`);
        await loadInvites();
    } catch (error) {
        showError('Failed to create invite: ' + error.message);
    }
}

async function revokeInvite(code) {
    if (!confirm(`Revoke invite ${code}?`)) return;

    try {
        const response = await fetch(`${getApiBaseUrl()}/admin/invites/${code}/revoke`, {
            method: 'POST',
            headers: getAuthHeaders()
        });
        await handleApiResponse(response);
        showSuccess('Invite revoked');
        await loadInvites();
    } catch (error) {
        showError('Failed to revoke invite: ' + error.message);
    }
}

async function updateQuota(userId, field, value) {
    // Store the value for later saving
    // This is a simple approach - in a real app you'd want better state management
    const row = document.querySelector(`tr:has(td:first-child:contains('${userId}'))`);
    if (row) {
        row.dataset[field] = value;
    }
}

async function saveQuota(userId) {
    const row = document.querySelector(`tr:has(td:first-child:contains('${userId}'))`);
    if (!row) return;

    const messages = parseInt(row.dataset.messages_per_day) || 100;
    const tokens = parseInt(row.dataset.tokens_per_day) || 10000;

    try {
        const response = await fetch(`${getApiBaseUrl()}/admin/quotas/${userId}`, {
            method: 'PUT',
            headers: getAuthHeaders(),
            body: JSON.stringify({
                messages_per_day: messages,
                tokens_per_day: tokens
            })
        });
        await handleApiResponse(response);
        showSuccess('Quota updated');
        await loadQuotas();
    } catch (error) {
        showError('Failed to update quota: ' + error.message);
    }
}

// Tab switching
function switchAdminSection(section) {
    currentAdminSection = section;

    // Update tab buttons
    document.querySelectorAll('#admin-nav button').forEach(btn => {
        btn.classList.remove('active');
    });
    document.getElementById(`admin-${section}-tab`).classList.add('active');

    // Show/hide sections
    document.querySelectorAll('.admin-section').forEach(sec => {
        sec.classList.add('hidden');
    });
    document.getElementById(`admin-${section}-section`).classList.remove('hidden');

    // Load data for the section
    switch (section) {
        case 'users':
            loadUsers();
            break;
        case 'invites':
            loadInvites();
            break;
        case 'audit':
            loadAuditLog();
            break;
        case 'quotas':
            loadQuotas();
            break;
    }
}

// Event listeners
document.getElementById('admin-logout-btn').addEventListener('click', async () => {
    await handleLogout();
    setRoute('login');
});

document.getElementById('admin-users-tab').addEventListener('click', () => switchAdminSection('users'));
document.getElementById('admin-invites-tab').addEventListener('click', () => switchAdminSection('invites'));
document.getElementById('admin-audit-tab').addEventListener('click', () => switchAdminSection('audit'));
document.getElementById('admin-quotas-tab').addEventListener('click', () => switchAdminSection('quotas'));

document.getElementById('create-invite-btn').addEventListener('click', createInvite);

document.getElementById('audit-search-btn').addEventListener('click', () => {
    const q = document.getElementById('audit-q').value;
    const action = document.getElementById('audit-action').value;
    const since = document.getElementById('audit-since').value;
    loadAuditLog(q, action, since);
});

// Utility functions
function showSuccess(message) {
    // Simple success notification
    alert(message);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}