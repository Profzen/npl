// ===================================
// CONFIGURATION
// ===================================
const API_BASE_URL = 'http://localhost:8000';

// État de l'application
let currentUser = null;
let currentConversation = [];
let conversations = [];

// ===================================
// LOGIN
// ===================================
document.getElementById('loginForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    
    // Validation simple (à remplacer par une vraie authentification)
    if ((username === 'admin' || username === 'user') && password === 'demo') {
        currentUser = {
            username: username,
            role: username === 'admin' ? 'admin' : 'user'
        };
        
        document.getElementById('loginScreen').classList.add('hidden');
        document.getElementById('appScreen').classList.remove('hidden');
        
        if (currentUser.role === 'admin') {
            document.getElementById('adminPanel').classList.remove('hidden');
            initAdminPanel();
        } else {
            document.getElementById('userPanel').classList.remove('hidden');
            initUserPanel();
        }
    } else {
        alert('Identifiants incorrects');
    }
});

// ===================================
// USER PANEL INITIALIZATION
// ===================================
function initUserPanel() {
    document.getElementById('userName').textContent = currentUser.username.toUpperCase();
    
    // Update header user label
    const userLabel = document.querySelector('.user-label');
    if (userLabel) {
        userLabel.textContent = currentUser.username;
    }
    
    // Load conversations from localStorage
    loadConversations();
    
    // Setup event listeners
    setupEventListeners();
    
    // Load table info
    loadTableInfo();
}

function initAdminPanel() {
    // Update header user label
    const adminUserLabel = document.getElementById('adminUserLabel');
    if (adminUserLabel) {
        adminUserLabel.textContent = currentUser.username;
    }
    
    // Setup admin event listeners
    setupAdminEventListeners();
}

// ===================================
// EVENT LISTENERS
// ===================================
function setupEventListeners() {
    // New chat button
    const newChatBtn = document.getElementById('newChatBtn');
    if (newChatBtn) {
        newChatBtn.addEventListener('click', startNewChat);
    }
    
    // Chat form
    document.getElementById('chatForm').addEventListener('submit', handleChatSubmit);
    
    // Chat input auto-resize
    const chatInput = document.getElementById('chatInput');
    chatInput.addEventListener('input', (e) => {
        e.target.style.height = 'auto';
        e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px';
    });
    
    // Example questions
    document.querySelectorAll('.example-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const question = e.target.getAttribute('data-question');
            document.getElementById('chatInput').value = question;
            setTimeout(() => handleChatSubmit(new Event('submit')), 100);
        });
    });
    
    // Logout - header button
    const logoutBtn = document.querySelector('.btn-logout');
    if (logoutBtn && !logoutBtn.id.includes('admin')) {
        logoutBtn.addEventListener('click', logout);
    }
}

// ===================================
// ADMIN EVENT LISTENERS
// ===================================
function setupAdminEventListeners() {
    // Tab navigation
    document.querySelectorAll('.admin-nav-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            handleAdminTabClick(e);
        });
    });
    
    // Config form
    const configForm = document.getElementById('configForm');
    if (configForm) {
        configForm.addEventListener('submit', handleConfigSave);
    }
    
    // Test connection button
    const testConnBtn = document.getElementById('testConnBtn');
    if (testConnBtn) {
        testConnBtn.addEventListener('click', handleTestConnection);
    }
    
    // Add user button
    const addUserBtn = document.getElementById('addUserBtn');
    if (addUserBtn) {
        addUserBtn.addEventListener('click', handleAddUser);
    }
    
    // Admin logout button
    const adminLogoutBtn = document.getElementById('adminLogoutBtn');
    if (adminLogoutBtn) {
        adminLogoutBtn.addEventListener('click', logout);
    }
}

function handleAdminTabClick(e) {
    const btn = e.currentTarget;
    const tabName = btn.getAttribute('data-tab');
    
    // Update active button
    document.querySelectorAll('.admin-nav-btn').forEach(b => {
        b.classList.remove('active');
    });
    btn.classList.add('active');
    
    // Update active tab content
    document.querySelectorAll('.admin-tab').forEach(tab => {
        tab.classList.remove('active');
    });
    
    const tabElement = document.getElementById(`tab-${tabName}`);
    if (tabElement) {
        tabElement.classList.add('active');
    }
}

async function handleTestConnection() {
    const host = document.getElementById('dbHost').value;
    const port = document.getElementById('dbPort').value;
    const dbName = document.getElementById('dbName').value;
    const user = document.getElementById('dbUser').value;
    const password = document.getElementById('dbPassword').value;
    
    const statusDiv = document.getElementById('configStatus');
    statusDiv.classList.add('visible');
    statusDiv.classList.remove('success', 'error');
    statusDiv.textContent = 'Test en cours...';
    
    try {
        const response = await fetch(`${API_BASE_URL}/admin/test-connection`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ host, port, dbName, user, password })
        });
        
        if (response.ok) {
            statusDiv.classList.add('success');
            statusDiv.textContent = '✓ Connexion établie avec succès';
        } else {
            statusDiv.classList.add('error');
            statusDiv.textContent = '✗ Erreur de connexion';
        }
    } catch (error) {
        statusDiv.classList.add('error');
        statusDiv.textContent = '✗ Erreur: ' + error.message;
    }
}

async function handleConfigSave(e) {
    e.preventDefault();
    
    const host = document.getElementById('dbHost').value;
    const port = document.getElementById('dbPort').value;
    const dbName = document.getElementById('dbName').value;
    const user = document.getElementById('dbUser').value;
    const password = document.getElementById('dbPassword').value;
    
    const statusDiv = document.getElementById('configStatus');
    statusDiv.classList.add('visible');
    statusDiv.classList.remove('success', 'error');
    statusDiv.textContent = 'Enregistrement...';
    
    try {
        const response = await fetch(`${API_BASE_URL}/admin/save-config`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ host, port, dbName, user, password })
        });
        
        if (response.ok) {
            statusDiv.classList.add('success');
            statusDiv.textContent = '✓ Configuration enregistrée';
        } else {
            statusDiv.classList.add('error');
            statusDiv.textContent = '✗ Erreur lors de l\'enregistrement';
        }
    } catch (error) {
        statusDiv.classList.add('error');
        statusDiv.textContent = '✗ Erreur: ' + error.message;
    }
}

function handleAddUser() {
    // Simple implementation - could be enhanced with a modal
    const userName = prompt('Nom d\'utilisateur:');
    if (!userName) return;
    
    const userRole = prompt('Rôle (Utilisateur/Administrateur):', 'Utilisateur');
    if (!userRole) return;
    
    const usersList = document.getElementById('usersList');
    
    const userItem = document.createElement('div');
    userItem.className = 'user-item';
    userItem.innerHTML = `
        <div class="user-info">
            <div class="user-name">${userName}</div>
            <div class="user-role">${userRole}</div>
        </div>
        <div class="user-actions">
            <button class="btn-icon">✎</button>
            <button class="btn-icon danger">⏹</button>
        </div>
    `;
    
    usersList.appendChild(userItem);
    
    // Setup delete button
    const deleteBtn = userItem.querySelector('.btn-icon.danger');
    deleteBtn.addEventListener('click', () => {
        userItem.remove();
    });
}

// ===================================
// CHAT FUNCTIONS
// ===================================
function startNewChat() {
    currentConversation = [];
    document.getElementById('messagesContainer').innerHTML = '';
    document.getElementById('chatEmpty').style.display = 'flex';
    document.getElementById('chatInput').value = '';
}

async function handleChatSubmit(e) {
    e.preventDefault();
    
    const input = document.getElementById('chatInput');
    const question = input.value.trim();
    
    if (!question) return;
    
    // Hide empty state
    document.getElementById('chatEmpty').style.display = 'none';
    
    // Add user message
    addMessage('user', question);
    
    // Clear input
    input.value = '';
    input.style.height = 'auto';
    
    // Show loading
    const loadingId = addLoadingMessage();
    
    try {
        // Call API
        const response = await fetch(`${API_BASE_URL}/query`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ question })
        });
        
        if (!response.ok) {
            throw new Error('Erreur lors de la requête');
        }
        
        const data = await response.json();
        
        // Remove loading
        removeLoadingMessage(loadingId);
        
        // Add assistant response
        addAssistantMessage(data);
        
        // Save conversation
        saveConversation(question);
        
    } catch (error) {
        console.error('Error:', error);
        removeLoadingMessage(loadingId);
        addMessage('assistant', 'Désolé, une erreur est survenue. Veuillez réessayer.');
    }
}

function addMessage(role, text) {
    const container = document.getElementById('messagesContainer');
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `message message-${role}`;
    
    const avatarDiv = document.createElement('div');
    avatarDiv.className = 'message-avatar';
    
    if (role === 'user') {
        avatarDiv.innerHTML = `
            <svg viewBox="0 0 24 24" fill="currentColor" stroke="none">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
                <circle cx="12" cy="7" r="4"></circle>
            </svg>
        `;
    } else {
        avatarDiv.innerHTML = `
            <svg viewBox="0 0 24 24" fill="currentColor" stroke="none">
                <rect x="3" y="3" width="18" height="18" rx="2"></rect>
                <path d="M9 9h6M9 15h6" stroke="currentColor" stroke-width="1" fill="none"></path>
            </svg>
        `;
    }
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    
    const textDiv = document.createElement('div');
    textDiv.className = 'message-text';
    textDiv.textContent = text;
    
    contentDiv.appendChild(textDiv);
    messageDiv.appendChild(avatarDiv);
    messageDiv.appendChild(contentDiv);
    
    container.appendChild(messageDiv);
    
    // Scroll to bottom
    setTimeout(() => {
        container.scrollTop = container.scrollHeight;
    }, 0);
    
    return messageDiv;
}

function addAssistantMessage(data) {
    const container = document.getElementById('messagesContainer');
    
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message message-assistant';
    
    const avatarDiv = document.createElement('div');
    avatarDiv.className = 'message-avatar';
    avatarDiv.innerHTML = `
        <svg viewBox="0 0 24 24" fill="currentColor" stroke="none">
            <rect x="3" y="3" width="18" height="18" rx="2"></rect>
            <path d="M9 9h6M9 15h6" stroke="currentColor" stroke-width="1" fill="none"></path>
        </svg>
    `;
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    
    // Answer text
    const textDiv = document.createElement('div');
    textDiv.className = 'message-text';
    textDiv.textContent = data.answer || data.response || 'Réponse générée';
    contentDiv.appendChild(textDiv);
    
    // SQL query
    if (data.sql) {
        const sqlDiv = document.createElement('div');
        sqlDiv.className = 'message-sql';
        sqlDiv.textContent = data.sql;
        contentDiv.appendChild(sqlDiv);
    }
    
    // Results table
    if (data.data && data.data.length > 0) {
        const tableDiv = createResultTable(data.data);
        contentDiv.appendChild(tableDiv);
    }
    
    messageDiv.appendChild(avatarDiv);
    messageDiv.appendChild(contentDiv);
    
    container.appendChild(messageDiv);
    
    // Scroll to bottom
    setTimeout(() => {
        container.scrollTop = container.scrollHeight;
    }, 0);
}

function createResultTable(data) {
    const tableContainer = document.createElement('div');
    tableContainer.className = 'message-table';
    
    const table = document.createElement('table');
    
    // Header
    const thead = document.createElement('thead');
    const headerRow = document.createElement('tr');
    
    const columns = Object.keys(data[0]);
    columns.forEach(col => {
        const th = document.createElement('th');
        th.textContent = col;
        headerRow.appendChild(th);
    });
    
    thead.appendChild(headerRow);
    table.appendChild(thead);
    
    // Body
    const tbody = document.createElement('tbody');
    
    data.slice(0, 10).forEach(row => { // Limit to 10 rows
        const tr = document.createElement('tr');
        
        columns.forEach(col => {
            const td = document.createElement('td');
            td.textContent = row[col] !== null ? row[col] : '-';
            tr.appendChild(td);
        });
        
        tbody.appendChild(tr);
    });
    
    table.appendChild(tbody);
    tableContainer.appendChild(table);
    
    if (data.length > 10) {
        const moreDiv = document.createElement('div');
        moreDiv.style.padding = '0.75rem 1rem';
        moreDiv.style.textAlign = 'center';
        moreDiv.style.fontSize = '0.85rem';
        moreDiv.style.color = 'var(--text-secondary)';
        moreDiv.textContent = `... et ${data.length - 10} ligne(s) supplémentaire(s)`;
        tableContainer.appendChild(moreDiv);
    }
    
    return tableContainer;
}

let loadingCounter = 0;

function addLoadingMessage() {
    const container = document.getElementById('messagesContainer');
    
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message message-assistant';
    messageDiv.id = `loading-${loadingCounter}`;
    
    const avatarDiv = document.createElement('div');
    avatarDiv.className = 'message-avatar';
    avatarDiv.innerHTML = `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="3" width="18" height="18" rx="2"></rect>
            <path d="M9 9h6M9 15h6M3 9h18"></path>
        </svg>
    `;
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    
    const loadingDiv = document.createElement('div');
    loadingDiv.className = 'message-loading';
    loadingDiv.innerHTML = `
        <div class="loading-dot"></div>
        <div class="loading-dot"></div>
        <div class="loading-dot"></div>
    `;
    
    contentDiv.appendChild(loadingDiv);
    messageDiv.appendChild(avatarDiv);
    messageDiv.appendChild(contentDiv);
    
    container.appendChild(messageDiv);
    container.scrollTop = container.scrollHeight;
    
    return loadingCounter++;
}

function removeLoadingMessage(id) {
    const loadingMsg = document.getElementById(`loading-${id}`);
    if (loadingMsg) {
        loadingMsg.remove();
    }
}

// ===================================
// CONVERSATIONS MANAGEMENT
// ===================================
function loadConversations() {
    const stored = localStorage.getItem('conversations');
    if (stored) {
        conversations = JSON.parse(stored);
        renderConversations();
    }
}

function saveConversation(question) {
    const conv = {
        id: Date.now(),
        title: question.substring(0, 50) + (question.length > 50 ? '...' : ''),
        date: new Date().toISOString(),
        messages: currentConversation
    };
    
    conversations.unshift(conv);
    
    // Keep only last 50 conversations
    if (conversations.length > 50) {
        conversations = conversations.slice(0, 50);
    }
    
    localStorage.setItem('conversations', JSON.stringify(conversations));
    renderConversations();
}

function renderConversations() {
    const container = document.querySelector('.conversation-group');
    
    // Clear existing
    const existing = container.querySelectorAll('.conversation-item');
    existing.forEach(el => el.remove());
    
    // Add conversations
    const today = conversations.filter(c => isToday(new Date(c.date)));
    
    today.forEach(conv => {
        const item = document.createElement('div');
        item.className = 'conversation-item';
        item.innerHTML = `
            <div class="conversation-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
                </svg>
            </div>
            <div class="conversation-text">${conv.title}</div>
        `;
        
        item.addEventListener('click', () => loadConversation(conv.id));
        
        container.appendChild(item);
    });
}

function isToday(date) {
    const today = new Date();
    return date.getDate() === today.getDate() &&
           date.getMonth() === today.getMonth() &&
           date.getFullYear() === today.getFullYear();
}

function loadConversation(id) {
    const conv = conversations.find(c => c.id === id);
    if (conv) {
        currentConversation = conv.messages;
        // Render messages
        // TODO: Implement conversation loading
    }
}

// ===================================
// TABLE INFO
// ===================================
async function loadTableInfo() {
    try {
        // Call API to get table info (mock for now)
        // In real implementation, call your API endpoint
        
        // Mock data
        document.getElementById('auditColumns').textContent = '12';
        document.getElementById('auditRows').textContent = '15,234';
        
    } catch (error) {
        console.error('Error loading table info:', error);
    }
}

// ===================================
// LOGOUT
// ===================================
function logout() {
    currentUser = null;
    currentConversation = [];
    
    document.getElementById('appScreen').classList.add('hidden');
    document.getElementById('userPanel').classList.add('hidden');
    document.getElementById('adminPanel').classList.add('hidden');
    document.getElementById('loginScreen').classList.remove('hidden');
    
    // Clear form
    document.getElementById('username').value = '';
    document.getElementById('password').value = '';
}
