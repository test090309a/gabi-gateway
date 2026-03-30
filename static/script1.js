// ========== GLOBALS ==========
let currentRequestId = null;
let isProcessing = false;
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let lastTelegramCount = 0;
let telegramRefreshInterval = null;
let wakeDetector = null;
let wakeListening = false;
let isSidebarCollapsed = false;
let requestStartTime = null;

// DOM Elements
const chatMessages = document.getElementById('chatMessages');
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const stopBtn = document.getElementById('stopBtn');
const voiceBtn = document.getElementById('voiceBtn');
const voiceStatus = document.getElementById('voiceStatus');
const imageUpload = document.getElementById('imageUpload');
const modelButton = document.getElementById('modelButton');
const modelDropdown = document.getElementById('modelDropdown');
const modelList = document.getElementById('modelList');
const modelSearch = document.getElementById('modelSearch');
const currentModelSpan = document.getElementById('currentModel');
const ollamaStatus = document.getElementById('ollamaStatus');
const ollamaStatusText = document.getElementById('ollamaStatusText');
const wakeIndicator = document.getElementById('wakeIndicator');
const wakeWordStatus = document.getElementById('wakeWordStatus');
const wakeToggleBtn = document.getElementById('wakeToggleBtn');
const wakeToggleText = document.getElementById('wakeToggleText');
const themeToggle = document.getElementById('themeToggle');
const themeIcon = document.getElementById('themeIcon');

// API Config
let apiKey = localStorage.getItem('apiKey') || 'sysop';
let ollamaUrl = localStorage.getItem('ollamaUrl') || 'http://localhost:11434';
let defaultModel = localStorage.getItem('defaultModel') || 'llama2:latest';

// Theme
let isDarkMode = localStorage.getItem('darkMode') === 'true';

function initTheme() {
    if (isDarkMode) {
        document.body.classList.remove('light-mode');
        document.body.classList.add('dark-mode');
        themeIcon.className = 'fas fa-sun';
    } else {
        document.body.classList.remove('dark-mode');
        document.body.classList.add('light-mode');
        themeIcon.className = 'fas fa-moon';
    }
}

themeToggle.addEventListener('click', () => {
    isDarkMode = !isDarkMode;
    localStorage.setItem('darkMode', isDarkMode);
    initTheme();
});

// ========== HEADER SIDEBAR TOGGLE (fa-bars) ==========
const headerToggleBtn = document.getElementById('sidebarToggle'); // Der fa-bars Button im Header
const sidebarContent = document.getElementById('sidebarContent');
const sidebarCol = document.querySelector('.lg\\:col-span-1');
const chatCol = document.querySelector('.lg\\:col-span-3');

let sidebarVisible = true;

function toggleSidebar() {
    if (sidebarVisible) {
        // Sidebar ausblenden
        sidebarContent.classList.add('sidebar-collapsed');
        if (sidebarCol) {
            sidebarCol.classList.add('sidebar-collapsed');
        }
        if (chatCol) {
            chatCol.classList.remove('lg:col-span-3');
            chatCol.classList.add('lg:col-span-4');
        }
        sidebarVisible = false;
    } else {
        // Sidebar einblenden
        sidebarContent.classList.remove('sidebar-collapsed');
        if (sidebarCol) {
            sidebarCol.classList.remove('sidebar-collapsed');
        }
        if (chatCol) {
            chatCol.classList.remove('lg:col-span-4');
            chatCol.classList.add('lg:col-span-3');
        }
        sidebarVisible = true;
    }
}

if (headerToggleBtn) {
    headerToggleBtn.addEventListener('click', toggleSidebar);
}

// Sidebar Toggle Button in Header einfügen
const headerDiv = document.querySelector('.glass .flex.items-center.justify-between');
if (headerDiv && !document.getElementById('sidebarToggle')) {
    const toggleBtn = document.createElement('button');
    toggleBtn.id = 'sidebarToggle';
    toggleBtn.className = 'p-2 rounded-full hover:bg-gray-200 dark:hover:bg-gray-700 transition mr-2';
    toggleBtn.innerHTML = '<i class="fas fa-bars text-gray-600 dark:text-gray-300"></i>';
    toggleBtn.onclick = toggleSidebar;
    headerDiv.insertBefore(toggleBtn, headerDiv.firstChild);
}

// ========== SCROLL BUTTON ==========
// Globale Variablen für Scroll-Button
let scrollBtn = null;
let scrollBtnInner = null;
let scrollIcon = null;

// 1. Chat-Container finden
const chatContainer = document.querySelector('.lg\\:col-span-3 .glass');
if (!chatContainer) {
    console.warn('Chat-Container nicht gefunden');
} else {
    // 2. Button erstellen (initial versteckt)
    const scrollButton = document.createElement('div');
    scrollButton.id = 'scrollButton';
    scrollButton.className = 'absolute bottom-4 right-4 z-20';
    scrollButton.innerHTML = `
        <button class="w-10 h-10 rounded-full bg-white dark:bg-gray-800 shadow-lg flex items-center justify-center hover:scale-110 transition-transform cursor-pointer">
            <i id="scrollIcon" class="fas fa-arrow-down text-gray-600 dark:text-gray-300"></i>
        </button>
    `;
    chatContainer.appendChild(scrollButton);
    
    // 3. Button-Elemente referenzieren (global)
    scrollBtn = document.getElementById('scrollButton');
    scrollBtnInner = scrollBtn ? scrollBtn.querySelector('button') : null;
    scrollIcon = document.getElementById('scrollIcon');
    
    // 4. Fester Event-Listener
    if (scrollBtnInner) {
        scrollBtnInner.addEventListener('click', function() {
            if (!chatMessages) return;
            
            const isAtBottom = chatMessages.scrollHeight - chatMessages.scrollTop - chatMessages.clientHeight < 50;
            
            if (isAtBottom) {
                // Ganz unten -> nach oben scrollen
                chatMessages.scrollTo({ top: 0, behavior: 'smooth' });
            } else {
                // Nicht ganz unten -> nach unten scrollen
                chatMessages.scrollTo({ top: chatMessages.scrollHeight, behavior: 'smooth' });
            }
        });
    }
    
    // 5. Funktion zum Aktualisieren
    function updateScrollButton() {
        if (!chatMessages || !scrollBtn || !scrollBtnInner) return;
        
        const isAtBottom = chatMessages.scrollHeight - chatMessages.scrollTop - chatMessages.clientHeight < 50;
        
        // Button verstecken wenn ganz unten ODER keine Nachrichten (nur Willkommen)
        const hasMessages = chatMessages.children.length > 1;
        
        if (isAtBottom || !hasMessages) {
            scrollBtn.classList.add('hidden');
            return;
        }
        
        // Button anzeigen
        scrollBtn.classList.remove('hidden');
        
        // Icon setzen: oben -> Pfeil nach unten, sonst Pfeil nach oben
        if (chatMessages.scrollTop < 50) {
            scrollIcon.className = 'fas fa-arrow-down';
        } else {
            scrollIcon.className = 'fas fa-arrow-up';
        }
    }
    
    // 6. Event-Listener
    if (chatMessages) {
        chatMessages.addEventListener('scroll', updateScrollButton);
    }
    window.addEventListener('resize', updateScrollButton);
    
    // 7. Initial prüfen
    setTimeout(updateScrollButton, 500);
}

// ========== APPLE TYPING INDICATOR ==========
function showTypingIndicator() {
    const indicatorDiv = document.createElement('div');
    indicatorDiv.id = 'typingIndicator';
    indicatorDiv.className = 'flex justify-start mb-3';
    indicatorDiv.innerHTML = `
        <div class="chat-bubble-assistant py-3 px-4">
            <div class="typing-indicator flex space-x-1.5">
                <span style="animation-delay: 0s"></span>
                <span style="animation-delay: 0.2s"></span>
                <span style="animation-delay: 0.4s"></span>
            </div>
        </div>
    `;
    chatMessages.appendChild(indicatorDiv);
    indicatorDiv.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

function hideTypingIndicator() {
    const indicator = document.getElementById('typingIndicator');
    if (indicator) indicator.remove();
}

// ========== WAKE WORD DETECTOR ==========
class WakeWordDetector {
    constructor() {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) {
            this.available = false;
            wakeWordStatus.textContent = "❌ Nicht unterstützt";
            return;
        }
        this.available = true;
        this.recognition = new SpeechRecognition();
        this.recognition.continuous = true;
        this.recognition.interimResults = true;
        this.recognition.lang = "de-DE";
        this.wakeWords = ["hey gabi", "ok gabi", "gabi"];
        this.isActive = false;
        this.silenceTimer = null;
        this.silenceTimeout = 1200;
        this.collectedText = "";
        this.setupEvents();
    }
    
    setupEvents() {
        this.recognition.onstart = () => {
            if (this.isActive) {
                wakeIndicator.className = "w-2.5 h-2.5 rounded-full bg-green-500";
                wakeWordStatus.textContent = "🎤 Hört auf 'Hey GABI'...";
            }
        };
        
        this.recognition.onresult = (event) => {
            if (!this.isActive) return;
            
            let fullText = "";
            for (let i = event.resultIndex; i < event.results.length; i++) {
                fullText += event.results[i][0].transcript.toLowerCase().trim();
            }
            
            for (const wake of this.wakeWords) {
                if (fullText.includes(wake)) {
                    this.triggerWake();
                    this.collectedText = "";
                    return;
                }
            }
            
            if (this.collectedText !== null && fullText.length > 0) {
                if (this.silenceTimer) clearTimeout(this.silenceTimer);
                this.collectedText = fullText;
                wakeWordStatus.textContent = `🎤 "${fullText.substring(0, 40)}..."`;
                
                this.silenceTimer = setTimeout(() => {
                    if (this.collectedText && this.collectedText.length > 2) {
                        this.sendToChat(this.collectedText);
                        this.collectedText = "";
                    }
                }, this.silenceTimeout);
            }
        };
        
        this.recognition.onerror = (e) => {
            if (e.error !== "no-speech" && this.isActive) {
                wakeWordStatus.textContent = "⚠️ Fehler, Neustart...";
                setTimeout(() => this.start(), 1000);
            }
        };
        
        this.recognition.onend = () => {
            if (this.isActive) setTimeout(() => this.start(), 100);
        };
    }
    
    triggerWake() {
        wakeIndicator.classList.add('wake-pulse');
        setTimeout(() => wakeIndicator.classList.remove('wake-pulse'), 500);
        wakeWordStatus.textContent = "🎤 Sprich jetzt...";
    }
    
    sendToChat(text) {
        const input = document.getElementById('messageInput');
        const btn = document.getElementById('sendBtn');
        if (input && btn) {
            input.value = text;
            btn.click();
            wakeWordStatus.textContent = "✅ Gesendet!";
            setTimeout(() => {
                if (this.isActive) wakeWordStatus.textContent = "🎤 Hört auf 'Hey GABI'...";
            }, 2000);
        }
    }
    
    start() {
        if (!this.available) return;
        try { this.recognition.start(); } catch(e) {}
    }
    
    activate() {
        this.isActive = true;
        this.collectedText = "";
        this.start();
    }
    
    deactivate() {
        this.isActive = false;
        if (this.silenceTimer) clearTimeout(this.silenceTimer);
        try { this.recognition.stop(); } catch(e) {}
        wakeIndicator.className = "w-2.5 h-2.5 rounded-full bg-gray-400";
        wakeWordStatus.textContent = "🎤 Zuhören aus";
    }
}

function initWakeWord() {
    wakeDetector = new WakeWordDetector();
    wakeDetector.activate();
    wakeListening = true;
    wakeToggleText.textContent = "Zuhören an";
    wakeIndicator.className = "w-2.5 h-2.5 rounded-full bg-green-500";
    wakeWordStatus.textContent = "🎤 Hört auf 'Hey GABI'...";
}

function toggleWakeWord() {
    if (!wakeDetector) return;
    if (wakeListening) {
        wakeDetector.deactivate();
        wakeListening = false;
        wakeToggleText.textContent = "Zuhören aus";
        wakeIndicator.className = "w-2.5 h-2.5 rounded-full bg-gray-400";
        wakeWordStatus.textContent = "🎤 Zuhören aus";
    } else {
        wakeDetector.activate();
        wakeListening = true;
        wakeToggleText.textContent = "Zuhören an";
        wakeIndicator.className = "w-2.5 h-2.5 rounded-full bg-green-500";
        wakeWordStatus.textContent = "🎤 Hört auf 'Hey GABI'...";
    }
}

wakeToggleBtn.addEventListener('click', toggleWakeWord);

// ========== CHAT FUNCTIONS ==========
async function sendMessage() {
    const message = messageInput.value.trim();
    if (!message || isProcessing) return;
    
    const lowerMessage = message.toLowerCase();
    
    // Telegram-Befehl Patterns
    const telegramPatterns = [
        "sende an telegram", "send an telegram", "telegram nachricht",
        "schreib an telegram", "telegram senden", "tg send",
        "an telegram", "per telegram"
    ];
    
    const isTelegramCommand = telegramPatterns.some(pattern => lowerMessage.includes(pattern));
    
    if (isTelegramCommand) {
        let telegramMessage = message;
        for (const pattern of telegramPatterns) {
            telegramMessage = telegramMessage.replace(new RegExp(pattern, 'gi'), '').trim();
        }
        
        if (telegramMessage) {
            console.log("📱 Sende Telegram-Nachricht:", telegramMessage);
            addSystemMessage(`📱 Sende an Telegram: "${telegramMessage.substring(0, 50)}..."`);
            
            try {
                const response = await fetch('/api/telegram/send', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-API-Key': apiKey
                    },
                    body: JSON.stringify({ message: telegramMessage })
                });
                const data = await response.json();
                
                if (data.status === 'success') {
                    addSystemMessage(`✅ Telegram gesendet: "${telegramMessage.substring(0, 50)}..."`);
                    messageInput.value = '';
                } else {
                    addSystemMessage(`❌ Telegram Fehler: ${data.message || data.error || 'Unbekannt'}`);
                }
            } catch (error) {
                console.error('Telegram send error:', error);
                addSystemMessage(`❌ Telegram Fehler: ${error.message}`);
            }
            return;
        }
    }
    
    // Web-Suche Erkennung
    const searchPatterns = [
        "suche im internet", "such im internet", "google nach",
        "web suche", "im internet suchen", "finde im internet",
        "recherchiere", "such nach", "suche nach"
    ];
    
    const isExplicitSearch = searchPatterns.some(pattern => lowerMessage.includes(pattern));
    
    const alwaysWebTopics = [
        "wetter", "temperatur", "vorhersage",
        "kino", "film", "kinoprogramm",
        "nachrichten", "news", "aktuell",
        "verkehr", "stau"
    ];
    
    const isAlwaysWeb = alwaysWebTopics.some(topic => lowerMessage.includes(topic));
    
    if (isExplicitSearch || isAlwaysWeb) {
        let cleanQuery = message;
        for (const pattern of searchPatterns) {
            cleanQuery = cleanQuery.replace(new RegExp(pattern, 'gi'), '').trim();
        }
        messageInput.value = `__SEARCH__ ${cleanQuery}`;
    } else {
        messageInput.value = message;
    }
    
    const msgToSend = messageInput.value;
    messageInput.value = '';
    addMessage(message, 'user');
    
    isProcessing = true;
    sendBtn.disabled = true;
    stopBtn.classList.remove('hidden');
    
    showTypingIndicator();
    
    const requestId = 'req_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    currentRequestId = requestId;
    requestStartTime = Date.now();
    
    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'token': apiKey
            },
            body: JSON.stringify({
                message: msgToSend,
                model: '__AUTO__',
                request_id: requestId
            })
        });
        
        const data = await response.json();
        const elapsedTime = ((Date.now() - requestStartTime) / 1000).toFixed(1);
        
        hideTypingIndicator();
        
        if (data.status === 'success') {
            addMessage(data.reply, 'assistant', data.thinking_steps, elapsedTime, data.model_used);
        } else {
            addMessage(`❌ Fehler: ${data.reply || data.message || 'Unbekannter Fehler'}`, 'assistant', null, elapsedTime);
        }
    } catch (error) {
        hideTypingIndicator();
        console.error('Send message error:', error);
        addMessage(`❌ Netzwerkfehler: ${error.message}`, 'assistant', null);
    } finally {
        isProcessing = false;
        sendBtn.disabled = false;
        stopBtn.classList.add('hidden');
        currentRequestId = null;
        messageInput.focus();
    }
}

function addMessage(content, role, thinkingSteps = null, elapsedTime = null, modelUsed = null) {
    const div = document.createElement('div');
    div.className = `message-enter flex ${role === 'user' ? 'justify-end' : 'justify-start'} mb-3`;
    const bubbleClass = role === 'user' ? 'chat-bubble-user' : 'chat-bubble-assistant';
    let html = `<div class="${bubbleClass}">`;
    
    if (role === 'assistant') {
        html += `<div class="markdown-content prose prose-sm max-w-none">${marked.parse(content)}</div>`;
        
        if (elapsedTime) {
            html += `<div class="text-xs opacity-50 mt-2 pt-1 border-t border-gray-200 dark:border-gray-700 flex justify-between">
                        <span><i class="fas fa-clock mr-1"></i>${elapsedTime}s</span>`;
            if (modelUsed) {
                html += `<span><i class="fas fa-microchip mr-1"></i>${escapeHtml(modelUsed)}</span>`;
            }
            html += `</div>`;
        }
        
        if (thinkingSteps && thinkingSteps.length > 0) {
            html += `<details class="mt-2 text-xs opacity-70"><summary><i class="fas fa-brain"></i> Gedankengang</summary><div class="mt-2 space-y-1">`;
            for (const step of thinkingSteps) {
                html += `<div class="thinking-step"><i class="${step.icon || 'fa-brain'} mr-1"></i> ${escapeHtml(step.text)}</div>`;
            }
            html += `</div></details>`;
        }
    } else {
        html += `<div class="whitespace-pre-wrap">${escapeHtml(content)}</div>`;
    }
    html += `</div>`;
    div.innerHTML = html;
    
    if (chatMessages.children.length === 1 && chatMessages.children[0].querySelector('.text-center')) {
        chatMessages.innerHTML = '';
    }
    chatMessages.appendChild(div);
    div.scrollIntoView({ behavior: 'smooth', block: 'end' });
    setTimeout(updateScrollButton, 100);
}
