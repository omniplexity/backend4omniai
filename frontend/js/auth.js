// OmniAI WebUI Auth Module

let currentUser = null;

function getCurrentUser() {
    return currentUser;
}

function setCurrentUser(user) {
    currentUser = user;
    if (user) {
        localStorage.setItem('currentUser', JSON.stringify(user));
    } else {
        localStorage.removeItem('currentUser');
    }
}

async function checkAuth() {
    try {
        const user = await getMe();
        setCurrentUser(user);
        return user;
    } catch (error) {
        setCurrentUser(null);
        return null;
    }
}

async function handleLogin(username, password) {
    try {
        const response = await login(username, password);
        setCurrentUser(response.user || { username });
        return response;
    } catch (error) {
        throw error;
    }
}

async function handleRegister(inviteCode, username, password) {
    try {
        const response = await register(inviteCode, username, password);
        setCurrentUser(response.user || { username });
        return response;
    } catch (error) {
        throw error;
    }
}

async function handleLogout() {
    try {
        await logout();
    } catch (error) {
        console.warn('Logout API call failed, clearing local state anyway:', error);
    }
    setCurrentUser(null);
    // Clear all local state
    localStorage.clear();
    location.reload(); // Force full reload to clear any cached state
}

// Initialize auth state on load
document.addEventListener('DOMContentLoaded', async () => {
    // Restore user from localStorage
    const storedUser = localStorage.getItem('currentUser');
    if (storedUser) {
        try {
            setCurrentUser(JSON.parse(storedUser));
        } catch (error) {
            console.warn('Failed to parse stored user:', error);
            localStorage.removeItem('currentUser');
        }
    }

    // Check auth with server
    await checkAuth();
});