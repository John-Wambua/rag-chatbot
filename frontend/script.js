// API base URL - use relative path to work from any host
const API_URL = '/api';

// Global state
let currentSessionId = null;
let activeRequest = null;  // AbortController for the in-flight query, if any

// DOM elements
let chatMessages, chatInput, sendButton, newChatButton, totalCourses, courseTitles, themeToggle;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    // Get DOM elements after page loads
    chatMessages = document.getElementById('chatMessages');
    chatInput = document.getElementById('chatInput');
    sendButton = document.getElementById('sendButton');
    newChatButton = document.getElementById('newChatButton');
    totalCourses = document.getElementById('totalCourses');
    courseTitles = document.getElementById('courseTitles');
    themeToggle = document.getElementById('themeToggle');

    setupTheme();
    setupEventListeners();
    createNewSession();
    loadCourseStats();
});

// Event Listeners
function setupEventListeners() {
    // Chat functionality
    sendButton.addEventListener('click', sendMessage);
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });

    // New chat
    newChatButton.addEventListener('click', createNewSession);

    // Theme toggle - a native <button>, so Enter and Space already fire click
    themeToggle.addEventListener('click', toggleTheme);


    // Suggested questions
    document.querySelectorAll('.suggested-item').forEach(button => {
        button.addEventListener('click', (e) => {
            const question = e.target.getAttribute('data-question');
            chatInput.value = question;
            sendMessage();
        });
    });
}


// Theme Functions
// The active theme lives in the data-theme attribute on <html>; index.html sets it
// before first paint, so here we only sync the button and react to changes.
function setupTheme() {
    updateThemeButton(getCurrentTheme());

    // Follow the OS preference while the user has not made an explicit choice
    window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', (e) => {
        if (readStoredTheme()) return;
        applyTheme(e.matches ? 'light' : 'dark');
    });
}

function toggleTheme() {
    const next = getCurrentTheme() === 'light' ? 'dark' : 'light';
    applyTheme(next);
    storeTheme(next);
}

function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    updateThemeButton(theme);
}

// The button shows the theme it switches TO, so the label names that theme
function updateThemeButton(theme) {
    if (!themeToggle) return;

    const target = theme === 'light' ? 'dark' : 'light';
    const label = `Switch to ${target} theme`;
    themeToggle.setAttribute('aria-label', label);
    themeToggle.setAttribute('title', label);
}

function getCurrentTheme() {
    return document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
}

// localStorage throws in private-mode Safari and when site data is blocked
function readStoredTheme() {
    try {
        const stored = localStorage.getItem('theme');
        return stored === 'light' || stored === 'dark' ? stored : null;
    } catch (error) {
        return null;
    }
}

function storeTheme(theme) {
    try {
        localStorage.setItem('theme', theme);
    } catch (error) {
        // Preference just will not survive a reload - not worth surfacing
    }
}


// Chat Functions
async function sendMessage() {
    const query = chatInput.value.trim();
    if (!query) return;

    // Disable input
    chatInput.value = '';
    chatInput.disabled = true;
    sendButton.disabled = true;

    // Add user message
    addMessage(query, 'user');

    // Add loading message - create a unique container for it
    const loadingMessage = createLoadingMessage();
    chatMessages.appendChild(loadingMessage);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    // Track the request so starting a new chat can cancel it
    const controller = new AbortController();
    activeRequest = controller;

    try {
        const response = await fetch(`${API_URL}/query`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                query: query,
                session_id: currentSessionId
            }),
            signal: controller.signal
        });

        if (!response.ok) throw new Error('Query failed');

        const data = await response.json();
        
        // Update session ID if new
        if (!currentSessionId) {
            currentSessionId = data.session_id;
        }

        // Replace loading message with response
        loadingMessage.remove();
        addMessage(data.answer, 'assistant', data.sources);

    } catch (error) {
        // A new chat cancelled this request - it already reset the UI, so stay quiet
        if (error.name === 'AbortError') return;

        // Replace loading message with error
        loadingMessage.remove();
        addMessage(`Error: ${error.message}`, 'assistant');
    } finally {
        // Only release the slot if a newer request hasn't already claimed it
        if (activeRequest === controller) {
            activeRequest = null;
            chatInput.disabled = false;
            sendButton.disabled = false;
            chatInput.focus();
        }
    }
}

function createLoadingMessage() {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant';
    messageDiv.innerHTML = `
        <div class="message-content">
            <div class="loading">
                <span></span>
                <span></span>
                <span></span>
            </div>
        </div>
    `;
    return messageDiv;
}

function addMessage(content, type, sources = null, isWelcome = false) {
    const messageId = Date.now();
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}${isWelcome ? ' welcome-message' : ''}`;
    messageDiv.id = `message-${messageId}`;
    
    // Convert markdown to HTML for assistant messages
    const displayContent = type === 'assistant' ? marked.parse(content) : escapeHtml(content);
    
    let html = `<div class="message-content">${displayContent}</div>`;
    
    if (sources && sources.length > 0) {
        html += `
            <details class="sources-collapsible">
                <summary class="sources-header">Sources</summary>
                <div class="sources-content">${sources.map(formatSource).join(', ')}</div>
            </details>
        `;
    }
    
    messageDiv.innerHTML = html;
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    
    return messageId;
}

// Render one citation as a link - the URL lives in the href only, never as visible text
function formatSource(source) {
    const text = escapeHtml(source.text);
    const href = safeUrl(source.link);

    if (!href) return `<span class="source-link-none">${text}</span>`;

    return `<a href="${escapeAttr(href)}" target="_blank" rel="noopener noreferrer">${text}</a>`;
}

// Only http(s) URLs belong in an href - escaping alone would still allow javascript:
// Returns the normalized form, which percent-encodes quotes and other delimiters.
function safeUrl(url) {
    if (!url) return null;

    try {
        const parsed = new URL(url, window.location.origin);
        return (parsed.protocol === 'http:' || parsed.protocol === 'https:') ? parsed.href : null;
    } catch {
        return null;
    }
}

// Helper function to escape HTML for user messages
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// escapeHtml leaves quotes intact, which would break out of a double-quoted attribute
function escapeAttr(value) {
    return escapeHtml(value).replace(/"/g, '&quot;');
}

// Removed removeMessage function - no longer needed since we handle loading differently

async function createNewSession() {
    // Cancel any in-flight query so its answer can't land in the new conversation
    if (activeRequest) {
        activeRequest.abort();
        activeRequest = null;
    }

    // Drop the old id before any await, so a late response cannot re-adopt it.
    // The next query mints a fresh session server-side (see app.py).
    const previousSessionId = currentSessionId;
    currentSessionId = null;

    // Reset the transcript and the input straight away - never wait on the network
    chatMessages.innerHTML = '';
    addMessage('Welcome to the Course Materials Assistant! I can help you with questions about courses, lessons and specific content. What would you like to know?', 'assistant', null, true);

    chatInput.value = '';
    chatInput.disabled = false;
    sendButton.disabled = false;
    chatInput.focus();

    // Release the old session's history server-side - best effort
    if (previousSessionId) {
        try {
            await fetch(`${API_URL}/session/${encodeURIComponent(previousSessionId)}`, {
                method: 'DELETE'
            });
        } catch (error) {
            console.error('Failed to release previous session:', error);
        }
    }
}

// Load course statistics
async function loadCourseStats() {
    try {
        console.log('Loading course stats...');
        const response = await fetch(`${API_URL}/courses`);
        if (!response.ok) throw new Error('Failed to load course stats');
        
        const data = await response.json();
        console.log('Course data received:', data);
        
        // Update stats in UI
        if (totalCourses) {
            totalCourses.textContent = data.total_courses;
        }
        
        // Update course titles
        if (courseTitles) {
            if (data.course_titles && data.course_titles.length > 0) {
                courseTitles.innerHTML = data.course_titles
                    .map(title => `<div class="course-title-item">${escapeHtml(title)}</div>`)
                    .join('');
            } else {
                courseTitles.innerHTML = '<span class="no-courses">No courses available</span>';
            }
        }
        
    } catch (error) {
        console.error('Error loading course stats:', error);
        // Set default values on error
        if (totalCourses) {
            totalCourses.textContent = '0';
        }
        if (courseTitles) {
            courseTitles.innerHTML = '<span class="error">Failed to load courses</span>';
        }
    }
}