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
    
    // 3. Button-Elemente referenzieren
    const scrollBtn = document.getElementById('scrollButton');
    const scrollBtnInner = scrollBtn ? scrollBtn.querySelector('button') : null;
    const scrollIcon = document.getElementById('scrollIcon');
    
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
        if (!chatMessages || !scrollBtnInner) return;
        
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

function addSystemMessage(content) {
    const div = document.createElement('div');
    div.className = 'message-enter flex justify-center mb-2';
    div.innerHTML = `<div class="bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-400 text-xs px-4 py-1.5 rounded-full">${escapeHtml(content)}</div>`;
    chatMessages.appendChild(div);
    div.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

function clearChat() {
    chatMessages.innerHTML = `<div class="text-center opacity-50 py-12"><i class="fas fa-comment-dots text-4xl mb-2"></i><p class="text-sm">Chat gelöscht</p></div>`;
    addSystemMessage('🧹 Chat gelöscht');
}

function exportChat() {
    const messages = [];
    for (let msg of chatMessages.children) {
        const text = msg.textContent;
        if (text && !text.includes('Chat gelöscht')) messages.push(text);
    }
    const blob = new Blob([messages.join('\n\n---\n\n')], { type: 'text/plain' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `gabi_chat_${new Date().toISOString().slice(0,19)}.txt`;
    a.click();
    URL.revokeObjectURL(a.href);
    addSystemMessage('📁 Chat exportiert');
}

async function showStatus() {
    try {
        const response = await fetch('/api/status', { headers: { 'X-API-Key': apiKey } });
        const data = await response.json();
        addMessage(`**📊 System Status**\n\n**System:** ${data.system?.os || '?'}\n**Ollama:** ${data.ollama?.available ? '✅ Online' : '❌ Offline'}\n**Modelle:** ${data.ollama?.total_models || 0}\n**Speicher:** ${data.storage?.free_gb || '?'} GB frei`, 'assistant');
    } catch (error) {
        addSystemMessage(`❌ Status fehlgeschlagen: ${error.message}`);
    }
}

function showHelp() {
    addMessage(`**🔧 GABI Befehle**\n\n**Chat:** /new, /reset, /archives, /load\n**Shell:** /shell <befehl>\n**GUI:** /gui open, /gui goto, /gui screenshot\n**Memory:** /merken, /gemerkt, /memory\n**Model:** /model, /model liste, /model <name>\n**System:** /status, /help`, 'assistant');
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

async function toggleRecording() {
    if (isRecording) {
        if (mediaRecorder) mediaRecorder.stop();
        isRecording = false;
        voiceBtn.innerHTML = '<i class="fas fa-microphone mr-1"></i><span>Mikrofon</span>';
        voiceBtn.classList.remove('bg-red-500', 'hover:bg-red-600');
        voiceBtn.classList.add('bg-green-500', 'hover:bg-green-600');
        voiceStatus.textContent = '🔄 Verarbeite...';
    } else {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaRecorder = new MediaRecorder(stream);
            audioChunks = [];
            mediaRecorder.ondataavailable = (e) => audioChunks.push(e.data);
            mediaRecorder.onstop = async () => {
                const blob = new Blob(audioChunks, { type: 'audio/webm' });
                await transcribeAudio(blob);
                stream.getTracks().forEach(t => t.stop());
            };
            mediaRecorder.start();
            isRecording = true;
            voiceBtn.innerHTML = '<i class="fas fa-stop mr-1"></i><span>Stopp</span>';
            voiceBtn.classList.remove('bg-green-500', 'hover:bg-green-600');
            voiceBtn.classList.add('bg-red-500', 'hover:bg-red-600');
            voiceStatus.textContent = '🎙️ Aufnahme läuft...';
        } catch (err) {
            voiceStatus.textContent = '❌ Mikrofon nicht verfügbar';
        }
    }
}

async function transcribeAudio(blob) {
    const formData = new FormData();
    formData.append('file', blob, 'audio.webm');
    try {
        const response = await fetch('/api/whisper/transcribe/sync', {
            method: 'POST',
            headers: { 'X-API-Key': apiKey },
            body: formData
        });
        const data = await response.json();
        voiceStatus.textContent = '';
        
        if (data.status === 'success' && data.text) {
            const userText = data.text.trim();
            console.log("🎤 Transkribiert:", userText);
            
            const lowerText = userText.toLowerCase();
            
            const telegramPatterns = [
                "sende an telegram", "send an telegram", "telegram nachricht",
                "schreib an telegram", "telegram senden", "tg send"
            ];
            
            const isTelegramCommand = telegramPatterns.some(pattern => lowerText.includes(pattern));
            
            const explicitSearchPatterns = [
                "suche im internet", "such im internet", "google nach", 
                "web suche", "im internet suchen", "finde im internet",
                "recherchiere", "such nach", "suche nach"
            ];
            
            const isExplicitSearch = explicitSearchPatterns.some(pattern => lowerText.includes(pattern));
            
            const alwaysWebTopics = [
                "wetter", "temperatur", "regen", "sonne", "vorhersage",
                "kino", "film", "kinoprogramm", "kino wien",
                "nachrichten", "news", "aktuell",
                "verkehr", "stau", "u-bahn", "bim",
                "aktien", "kurs", "boerse", "euro", "dollar",
                "fußball", "ergebnis", "spielstand"
            ];
            
            const isAlwaysWeb = alwaysWebTopics.some(topic => lowerText.includes(topic));
            
            const questionWords = ["was ist", "wer ist", "wer war", "was bedeutet", "erkläre", "definiere"];
            const isQuestion = questionWords.some(qw => lowerText.includes(qw));
            
            const greetings = ["hallo", "hi", "hey", "servus", "moin", "guten morgen", "guten tag"];
            const isGreeting = greetings.some(g => lowerText === g || lowerText.startsWith(g + " "));
            
            if (isTelegramCommand) {
                let telegramMessage = userText;
                for (const pattern of telegramPatterns) {
                    telegramMessage = telegramMessage.replace(new RegExp(pattern, 'gi'), '').trim();
                }
                
                if (telegramMessage) {
                    console.log("📱 Sende Telegram-Nachricht:", telegramMessage);
                    updateVoiceStatus(`📱 Sende an Telegram...`, 'telegram');
                    
                    try {
                        const tgResponse = await fetch('/api/telegram/send', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'X-API-Key': apiKey
                            },
                            body: JSON.stringify({ message: telegramMessage })
                        });
                        const tgData = await tgResponse.json();
                        
                        if (tgData.status === 'success') {
                            addSystemMessage(`✅ Telegram: "${telegramMessage.substring(0, 50)}..." gesendet`);
                            updateVoiceStatus(`✅ Telegram gesendet!`, 'success');
                        } else {
                            addSystemMessage(`❌ Telegram Fehler: ${tgData.message || 'Unbekannt'}`);
                            updateVoiceStatus(`❌ Telegram Fehler`, 'error');
                        }
                    } catch (err) {
                        console.error('Telegram send error:', err);
                        addSystemMessage(`❌ Telegram Fehler: ${err.message}`);
                        updateVoiceStatus(`❌ Telegram Fehler`, 'error');
                    }
                    return;
                } else {
                    addSystemMessage(`❌ Keine Nachricht für Telegram erkannt`);
                    updateVoiceStatus(`❌ Keine Nachricht`, 'error');
                    return;
                }
            }
            
            let shouldSearch = false;
            let cleanText = userText;
            
            for (const pattern of explicitSearchPatterns) {
                if (lowerText.includes(pattern)) {
                    cleanText = userText.replace(new RegExp(pattern, 'gi'), '').trim();
                    shouldSearch = true;
                    break;
                }
            }
            
            if (!shouldSearch) {
                if (isAlwaysWeb) {
                    shouldSearch = true;
                    cleanText = userText;
                    console.log("🌐 Thema erfordert Web-Suche:", cleanText);
                } else if (isGreeting) {
                    shouldSearch = false;
                    console.log("💬 Begrüßung erkannt");
                } else if (isQuestion) {
                    shouldSearch = false;
                    console.log("📚 Wissensfrage -> Lokale KI");
                } else {
                    shouldSearch = false;
                    console.log("🤖 Normale Frage -> Lokale KI");
                }
            }
            
            if (shouldSearch) {
                messageInput.value = cleanText;
                console.log("🔍 Starte Web-Suche:", cleanText);
                updateVoiceStatus(`🔍 Web-Suche: "${cleanText.substring(0, 30)}..."`, 'search');
                addSystemMessage(`🔍 Web-Suche: "${cleanText}"`);
                sendMessage();
            } else {
                messageInput.value = userText;
                console.log("💬 Sende an lokale KI:", userText);
                updateVoiceStatus(`💬 Frage an GABI...`, 'local');
                sendMessage();
            }
            
        } else {
            addSystemMessage(`❌ Transkription fehlgeschlagen`);
            updateVoiceStatus(`❌ Transkription fehlgeschlagen`, 'error');
        }
    } catch (error) {
        console.error('Transcription error:', error);
        addSystemMessage(`❌ Fehler: ${error.message}`);
        updateVoiceStatus(`❌ Fehler: ${error.message}`, 'error');
    }
}

function updateVoiceStatus(message, type = 'info') {
    const voiceStatus = document.getElementById('voiceStatus');
    if (!voiceStatus) return;
    
    voiceStatus.textContent = message;
    voiceStatus.classList.remove('search', 'local', 'telegram', 'error', 'success');
    voiceStatus.classList.add(type);
    
    setTimeout(() => {
        if (voiceStatus.textContent === message) {
            voiceStatus.style.opacity = '0.5';
        }
    }, 3000);
}

async function handleImageUpload(e) {
    const file = e.target.files[0];
    if (!file) return;
    if (!file.type.startsWith('image/')) {
        addSystemMessage(`❌ Kein Bild: ${file.type}`);
        imageUpload.value = '';
        return;
    }
    const formData = new FormData();
    formData.append('file', file);
    formData.append('prompt', 'Beschreibe dieses Bild.');
    addSystemMessage(`📷 Analysiere Bild...`);
    showTypingIndicator();
    try {
        const response = await fetch('/api/api/chat/image/analyze', {
            method: 'POST',
            headers: { 'token': apiKey },
            body: formData
        });
        const data = await response.json();
        hideTypingIndicator();
        if (data.status === 'success') {
            addMessage(data.reply, 'assistant', data.thinking_steps);
        } else {
            addSystemMessage(`❌ Analyse fehlgeschlagen`);
        }
    } catch (error) {
        hideTypingIndicator();
        addSystemMessage(`❌ Fehler: ${error.message}`);
    } finally {
        imageUpload.value = '';
    }
}

// ========== MODEL MANAGEMENT ==========
async function loadModels() {
    try {
        const response = await fetch('/api/models', { headers: { 'X-API-Key': apiKey } });
        const data = await response.json();
        if (data.status === 'success') {
            currentModelSpan.textContent = data.current_model || defaultModel;
            renderModelList(data.models || []);
        }
    } catch (error) {
        currentModelSpan.textContent = defaultModel;
    }
}

function renderModelList(models) {
    modelList.innerHTML = '';
    models.forEach(m => {
        const item = document.createElement('div');
        item.className = 'model-selector px-3 py-2 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center justify-between text-sm';
        item.innerHTML = `<span>${escapeHtml(m.name)}</span>`;
        item.onclick = () => switchModel(m.name);
        modelList.appendChild(item);
    });
}

async function switchModel(name) {
    try {
        const response = await fetch('/api/models/switch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-API-Key': apiKey },
            body: JSON.stringify({ model: name })
        });
        const data = await response.json();
        if (data.status === 'success') {
            currentModelSpan.textContent = name;
            defaultModel = name;
            localStorage.setItem('defaultModel', name);
            addSystemMessage(`✅ Modell: ${name}`);
        }
        modelDropdown.classList.add('hidden');
    } catch (error) {
        addSystemMessage(`❌ Fehler: ${error.message}`);
    }
}

async function checkOllamaStatus() {
    try {
        const response = await fetch(`${ollamaUrl}/api/tags`);
        if (response.ok) {
            ollamaStatus.className = 'w-2.5 h-2.5 rounded-full bg-green-500';
            ollamaStatusText.textContent = 'Online';
        } else throw new Error();
    } catch {
        ollamaStatus.className = 'w-2.5 h-2.5 rounded-full bg-red-500';
        ollamaStatusText.textContent = 'Offline';
    }
}

// ========== TELEGRAM MODAL ==========
async function loadTelegramMessages() {
    const container = document.getElementById('telegramModalMessages');
    try {
        const response = await fetch('/api/telegram/messages?limit=100', { headers: { 'X-API-Key': apiKey } });
        const data = await response.json();
        if (data.status === 'success' && data.messages?.length) {
            container.innerHTML = '';
            for (const msg of data.messages.slice(-50)) {
                const isUser = msg.role === 'user';
                const time = new Date(msg.date).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
                const div = document.createElement('div');
                div.className = `flex ${isUser ? 'justify-start' : 'justify-end'} mb-2`;
                div.innerHTML = `<div class="max-w-[85%] ${isUser ? 'bg-blue-100 dark:bg-blue-900' : 'bg-green-100 dark:bg-green-900'} rounded-xl p-2 text-sm"><div class="flex justify-between text-xs opacity-70 mb-1"><span><i class="fab fa-telegram"></i> ${isUser ? `User ${msg.user_id}` : 'GABI'}</span><span>${time}</span></div>${escapeHtml(msg.text)}</div>`;
                container.appendChild(div);
            }
            container.scrollTop = container.scrollHeight;
        } else {
            container.innerHTML = '<div class="text-center opacity-50 py-8"><i class="fab fa-telegram text-4xl mb-2"></i><p>Keine Nachrichten</p></div>';
        }
    } catch (e) {
        container.innerHTML = '<div class="text-center text-red-500 py-8">Fehler beim Laden</div>';
    }
}

async function sendTelegramMsg() {
    const input = document.getElementById('telegramMessageInput');
    const msg = input.value.trim();
    if (!msg) return;
    const btn = document.getElementById('sendTelegramMessageBtn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
    try {
        await fetch('/api/telegram/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-API-Key': apiKey },
            body: JSON.stringify({ message: msg })
        });
        input.value = '';
        addSystemMessage(`✅ Telegram: ${msg.substring(0, 50)}...`);
        setTimeout(loadTelegramMessages, 500);
    } catch (e) {
        addSystemMessage(`❌ Telegram Fehler`);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-paper-plane"></i>';
    }
}

// ========== SETTINGS ==========
function closeSettings() { document.getElementById('settingsModal').classList.add('hidden'); }
function saveSettings() {
    const newKey = document.getElementById('apiKey').value.trim();
    const newUrl = document.getElementById('ollamaUrl').value.trim();
    const newModel = document.getElementById('defaultModel').value.trim();
    if (newKey) apiKey = newKey;
    if (newUrl) ollamaUrl = newUrl;
    if (newModel) defaultModel = newModel;
    localStorage.setItem('apiKey', apiKey);
    localStorage.setItem('ollamaUrl', ollamaUrl);
    localStorage.setItem('defaultModel', defaultModel);
    closeSettings();
    addSystemMessage('✅ Einstellungen gespeichert');
    loadModels();
    checkOllamaStatus();
}

// ========== STOP FUNCTION ==========
function stopCurrentRequest() {
    if (currentRequestId) {
        fetch('/api/api/chat/stop', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'token': apiKey },
            body: JSON.stringify({ request_id: currentRequestId })
        });
    }
    isProcessing = false;
    sendBtn.disabled = false;
    stopBtn.classList.add('hidden');
    hideTypingIndicator();
    addSystemMessage('⏹️ Anfrage gestoppt');
}

// ========== EVENT LISTENERS ==========
sendBtn.addEventListener('click', sendMessage);
stopBtn.addEventListener('click', stopCurrentRequest);
messageInput.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } });
voiceBtn.addEventListener('click', toggleRecording);
imageUpload.addEventListener('change', handleImageUpload);
modelButton.addEventListener('click', () => modelDropdown.classList.toggle('hidden'));
modelSearch.addEventListener('input', (e) => {
    const term = e.target.value.toLowerCase();
    for (let item of modelList.children) {
        item.style.display = item.textContent.toLowerCase().includes(term) ? 'flex' : 'none';
    }
});
document.addEventListener('click', (e) => { if (!modelButton.contains(e.target) && !modelDropdown.contains(e.target)) modelDropdown.classList.add('hidden'); });
document.getElementById('settingsBtn').addEventListener('click', () => {
    document.getElementById('apiKey').value = apiKey;
    document.getElementById('ollamaUrl').value = ollamaUrl;
    document.getElementById('defaultModel').value = defaultModel;
    document.getElementById('settingsModal').classList.remove('hidden');
});
document.getElementById('telegramModalBtn').addEventListener('click', () => { document.getElementById('telegramModal').classList.remove('hidden'); loadTelegramMessages(); });
document.getElementById('closeTelegramModalBtn').addEventListener('click', () => document.getElementById('telegramModal').classList.add('hidden'));
document.getElementById('refreshTelegramModalBtn').addEventListener('click', loadTelegramMessages);
document.getElementById('sendTelegramMessageBtn').addEventListener('click', sendTelegramMsg);
document.getElementById('telegramMessageInput').addEventListener('keypress', (e) => { if (e.key === 'Enter') sendTelegramMsg(); });
document.getElementById('telegramModal').addEventListener('click', (e) => { if (e.target === document.getElementById('telegramModal')) document.getElementById('telegramModal').classList.add('hidden'); });

// ========== INIT ==========
initTheme();
loadModels();
checkOllamaStatus();
setInterval(checkOllamaStatus, 30000);
initWakeWord();
setInterval(() => {
    if (document.getElementById('telegramModal').classList.contains('hidden')) return;
    loadTelegramMessages();
}, 10000);