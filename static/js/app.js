// ==================== KONFIGURATION ====================
const API_KEY = "sysop";
let activeModel = "__AUTO__";
let availableModels = [];
let currentChatController = null;
let currentThinkingContainer = null;
let thinkingInterval = null;
let thinkingStartTime = null;
let isChatRunning = false;
let lastScrollDirection = 'down';
let lastScrollTop = 0;
let userScrolledUp = false;
let scrollTimeout = null;

// Command History
let commandHistory = [];
let historyIndex = -1;

// Panel State
let activePanel = null;

// Waiting Animation spezifische Variablen
let waitingTimerInterval = null;
let waitingStartTime = null;

// DOM Elements (werden nach DOM-Ready gesetzt)
let chatContainer, chatInput, sendBtn, stopBtn, modelSelector, llmStatus;
let panelOverlay, panelTitle, panelBody, closePanelBtn, helpModal, closeHelpBtn, helpBtn;
let scrollBtn;

// ==================== HELPER FUNCTIONS ====================
function escapeHtml(str) { 
    return str?.replace(/[&<>]/g, function(m) { 
        if(m === '&') return '&amp;'; 
        if(m === '<') return '&lt;'; 
        if(m === '>') return '&gt;'; 
        return m; 
    }) || ''; 
}

function formatClock() { 
    return new Date().toLocaleTimeString('de-DE'); 
}

function formatTime(ms) { 
    return `${Math.floor(ms/1000)}s`; 
}

function smoothScrollToBottom() {
    const targetScroll = chatContainer.scrollHeight;
    const startScroll = chatContainer.scrollTop;
    const distance = targetScroll - startScroll;
    if (distance <= 0) return;
    const duration = Math.min(300, Math.max(100, distance / 3));
    const startTime = performance.now();
    
    function animateScroll(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(1, elapsed / duration);
        const easeOutCubic = 1 - Math.pow(1 - progress, 3);
        chatContainer.scrollTop = startScroll + (distance * easeOutCubic);
        if (progress < 1) requestAnimationFrame(animateScroll);
    }
    requestAnimationFrame(animateScroll);
}

function adjustContainerHeight() {
    if (!chatContainer || chatContainer.children.length === 0) return;
    const lastMessage = chatContainer.children[chatContainer.children.length - 1];
    if (lastMessage) {
        const messageRect = lastMessage.getBoundingClientRect();
        const containerRect = chatContainer.getBoundingClientRect();
        if (messageRect.bottom > containerRect.bottom) smoothScrollToBottom();
    }
}

function updateScrollButton() {
    const isAtBottom = chatContainer.scrollHeight - chatContainer.scrollTop - chatContainer.clientHeight < 50;
    if (isAtBottom) {
        scrollBtn.classList.remove('visible');
        return;
    }
    scrollBtn.classList.add('visible');
    const currentScroll = chatContainer.scrollTop;
    if (currentScroll > lastScrollTop) {
        scrollBtn.innerHTML = '<i class="fas fa-arrow-down"></i>';
        lastScrollDirection = 'down';
    } else if (currentScroll < lastScrollTop) {
        scrollBtn.innerHTML = '<i class="fas fa-arrow-up"></i>';
        lastScrollDirection = 'up';
    }
    lastScrollTop = currentScroll;
}

// ==================== MESSAGE FUNCTIONS ====================
function addMessage(sender, content, isUser = false, icon = 'fas fa-user') {
    const div = document.createElement('div');
    div.className = `fade-in ${isUser ? 'flex justify-end' : 'flex justify-start'}`;
    
    let processedContent = content;
    processedContent = processedContent.replace(/(https?:\/\/[^\s]+)/g, (url) => {
        if (url.length > 50) return `<a href="${url}" target="_blank" class="text-[var(--accent)] hover:underline">${url.substring(0, 40)}...</a>`;
        return `<a href="${url}" target="_blank" class="text-[var(--accent)] hover:underline">${url}</a>`;
    });
    
    processedContent = processedContent.replace(/```json\n([\s\S]*?)```/g, (match, jsonContent) => {
        try {
            const parsed = JSON.parse(jsonContent);
            const formatted = JSON.stringify(parsed, null, 2);
            return `<pre class="bg-black/50 p-3 rounded-lg overflow-x-auto text-xs"><code class="language-json">${escapeHtml(formatted)}</code></pre>`;
        } catch (e) { return match; }
    });
    
    div.innerHTML = `
        <div class="${isUser ? 'message-user' : 'message-assistant'}">
            <div class="flex items-center gap-2 text-xs opacity-80 mb-1">
                <i class="${icon}"></i> <span>${escapeHtml(sender)}</span> <span>·</span> <span class="message-time">${formatClock()}</span>
            </div>
            <div class="message-content break-words">${marked.parse(processedContent)}</div>
        </div>
    `;
    chatContainer.appendChild(div);
    
    const isNearBottom = chatContainer.scrollHeight - chatContainer.scrollTop - chatContainer.clientHeight < 150;
    if (isNearBottom || !userScrolledUp) smoothScrollToBottom();
    adjustContainerHeight();
}

function addThinkingStep(text, icon = 'fa-pencil-alt') {
    if (!currentThinkingContainer || !currentThinkingContainer.isConnected) {
        currentThinkingContainer = document.createElement('div');
        currentThinkingContainer.className = 'thinking-steps-container';
        currentThinkingContainer.innerHTML = `
            <details open>
                <summary class="text-[var(--accent)] font-semibold text-sm cursor-pointer hover:text-[var(--accent-hover)] transition-colors">
                    📡 GATEWAY LOGS & GEDANKENGANG
                </summary>
                <div class="steps-list mt-2 space-y-1"></div>
            </details>
        `;
        chatContainer.appendChild(currentThinkingContainer);
    }
    
    const stepsList = currentThinkingContainer.querySelector('.steps-list');
    const stepDiv = document.createElement('div');
    stepDiv.className = 'thinking-step text-xs';
    stepDiv.style.opacity = '0';
    stepDiv.style.transform = 'translateX(-10px)';
    stepDiv.style.transition = 'all 0.2s ease';
    
    stepDiv.innerHTML = `
        <i class="fas ${icon} text-[var(--accent)]"></i>
        <div class="flex-1"><span class="text-[var(--text-secondary)]">${escapeHtml(text)}</span></div>
        <div class="step-time text-[var(--text-muted)] font-mono text-[10px]">${formatClock()}</div>
    `;
    stepsList.appendChild(stepDiv);
    
    setTimeout(() => { stepDiv.style.opacity = '1'; stepDiv.style.transform = 'translateX(0)'; }, 10);
    if (!userScrolledUp) smoothScrollToBottom();
    if (stepsList.children.length > 100) stepsList.removeChild(stepsList.children[0]);
}

function clearThinkingContainer() { 
    currentThinkingContainer = null; 
}

// ==================== WAITING ANIMATION ====================
function showWaiting(modelName = 'Auto') {
    let animation = document.getElementById('waiting-animation');
    
    if (!animation) {
        const inputArea = document.querySelector('.p-4.border-t.border-\\[var\\(--border\\)\\]');
        if (!inputArea) return;
        
        animation = document.createElement('div');
        animation.id = 'waiting-animation';
        animation.className = 'flex flex-col gap-2 p-3 mb-2 bg-[var(--bg-tertiary)] border border-[var(--border)] rounded-lg shadow-lg';
        animation.style.opacity = '0';
        animation.style.transform = 'translateY(-10px)';
        animation.style.transition = 'all 0.2s ease';
        
        animation.innerHTML = `
            <div class="flex items-center justify-between">
                <div class="flex items-center gap-3">
                    <div class="loader w-5 h-5"></div>
                    <span class="text-sm font-medium text-[var(--accent)]">🧠 GABI denkt...</span>
                    <span id="thinking-timer" class="text-xs text-[var(--text-muted)] font-mono bg-black/30 px-2 py-0.5 rounded">0.0s</span>
                </div>
                <div class="flex items-center gap-2">
                    <span class="text-xs text-[var(--text-muted)]">🤖 <span id="waiting-model">${modelName}</span></span>
                    <div class="w-1.5 h-1.5 bg-[var(--accent)] rounded-full animate-pulse"></div>
                </div>
            </div>
            <div class="flex items-center gap-4 text-xs">
                <div class="flex items-center gap-1"><i class="fas fa-chart-line text-[var(--text-muted)] w-4"></i><span class="text-[var(--text-muted)]">Token:</span><span id="waiting-tokens" class="font-mono text-[var(--text-secondary)]">--</span></div>
                <div class="flex items-center gap-1"><i class="fas fa-bullseye text-[var(--text-muted)] w-4"></i><span class="text-[var(--text-muted)]">Intent:</span><span id="waiting-intent" class="font-mono text-[var(--text-secondary)]">--</span></div>
                <div class="flex items-center gap-1"><i class="fas fa-brain text-[var(--text-muted)] w-4"></i><span class="text-[var(--text-muted)]">Hemisphäre:</span><span id="waiting-hemisphere" class="font-mono text-[var(--text-secondary)]">--</span></div>
            </div>
            <div class="text-[10px] text-[var(--text-muted)] flex items-center gap-2 border-t border-[var(--border)] pt-1 mt-1">
                <i class="fas fa-spinner fa-pulse"></i>
                <span id="waiting-status">Verbinde mit Gateway...</span>
            </div>
        `;
        
        inputArea.parentNode.insertBefore(animation, inputArea);
    }
    
    const modelSpan = document.getElementById('waiting-model');
    const timerSpan = document.getElementById('thinking-timer');
    
    if (modelSpan) modelSpan.textContent = modelName;
    if (timerSpan) timerSpan.textContent = '0.0s';
    
    animation.style.display = 'flex';
    animation.style.opacity = '1';
    animation.style.transform = 'translateY(0)';
    
    waitingStartTime = performance.now();
    
    if (waitingTimerInterval) clearInterval(waitingTimerInterval);
    
    waitingTimerInterval = setInterval(() => {
        const timerSpan = document.getElementById('thinking-timer');
        if (timerSpan && waitingStartTime) {
            const elapsed = (performance.now() - waitingStartTime) / 1000;
            timerSpan.textContent = elapsed.toFixed(1) + 's';
        }
    }, 100);
}

function updateWaitingStats(tokens, intent, hemisphere, status) {
    if (tokens) {
        const tokensEl = document.getElementById('waiting-tokens');
        if (tokensEl) tokensEl.textContent = tokens;
    }
    if (intent) {
        const intentEl = document.getElementById('waiting-intent');
        if (intentEl) intentEl.textContent = intent;
    }
    if (hemisphere) {
        const hemisphereEl = document.getElementById('waiting-hemisphere');
        if (hemisphereEl) hemisphereEl.textContent = hemisphere;
    }
    if (status) {
        const statusEl = document.getElementById('waiting-status');
        if (statusEl) statusEl.innerHTML = `<i class="fas fa-spinner fa-pulse mr-1"></i> ${status}`;
    }
}

function hideWaiting() {
    const animation = document.getElementById('waiting-animation');
    if (animation) {
        animation.style.opacity = '0';
        animation.style.transform = 'translateY(-10px)';
        setTimeout(() => {
            if (animation.parentNode) animation.remove();
        }, 200);
    }
    if (waitingTimerInterval) {
        clearInterval(waitingTimerInterval);
        waitingTimerInterval = null;
    }
}

// ==================== FILE SUGGESTIONS ====================
async function fetchFileSuggestions(query = "") {
    try {
        const response = await fetch(`/api/files/list?limit=50&query=${encodeURIComponent(query)}`, {
            headers: { 'Authorization': `Bearer ${API_KEY}` }
        });
        if (!response.ok) return [];
        const data = await response.json();
        return data.files || [];
    } catch { return []; }
}

function renderFileSuggestions(items) {
    const box = document.getElementById('file-suggest');
    if (!box) return;
    if (!items.length) { box.classList.add('hidden'); box.innerHTML = ""; return; }
    box.innerHTML = items.map(path => `<button onclick="window.pickSuggestedFile('${escapeHtml(path).replace(/'/g, "\\'")}')">📄 @${escapeHtml(path)}</button>`).join("");
    box.classList.remove('hidden');
}

window.pickSuggestedFile = function(path) {
    const value = chatInput.value;
    const cursorPos = chatInput.selectionStart;
    const textBeforeCursor = value.slice(0, cursorPos);
    const atIndex = textBeforeCursor.lastIndexOf('@');
    if (atIndex >= 0) {
        chatInput.value = `${value.slice(0, atIndex)}@${path} ${value.slice(cursorPos)}`;
        chatInput.focus();
        chatInput.setSelectionRange(atIndex + path.length + 2, atIndex + path.length + 2);
    }
    renderFileSuggestions([]);
};

// ==================== PANEL LOGIC ====================
function closeAllPanels() { 
    panelOverlay.classList.remove('active'); 
    activePanel = null; 
    document.querySelectorAll('.btn[data-panel]').forEach(btn => btn.classList.remove('btn-active')); 
}

async function openPanel(panelType) {
    if (activePanel === panelType) { closeAllPanels(); return; }
    closeAllPanels();
    activePanel = panelType;
    panelOverlay.classList.add('active');
    document.querySelector(`.btn[data-panel="${panelType}"]`).classList.add('btn-active');
    if (panelType === 'tools') await loadToolsPanel();
    else if (panelType === 'mails') await loadMailsPanel();
    else if (panelType === 'gui') await loadGuiPanel();
    else if (panelType === 'comfy') await loadComfyPanel();
}

// ==================== PANEL CONTENT ====================
async function loadToolsPanel() {
    panelTitle.innerHTML = '<i class="fas fa-tools"></i> GABI Tools';
    panelBody.innerHTML = `<div class="grid grid-cols-2 md:grid-cols-3 gap-2">
        <button class="btn btn-sm" onclick="window.openModalAPI('/api/memory', 'Memory')"><i class="fas fa-brain"></i> Memory</button>
        <button class="btn btn-sm" onclick="window.openModalAPI('/api/soul', 'Soul')"><i class="fas fa-dna"></i> Soul</button>
        <button class="btn btn-sm" onclick="window.openModalAPI('/api/identity', 'Identity')"><i class="fas fa-id-card"></i> Identity</button>
        <button class="btn btn-sm" onclick="window.showMemoryStats()"><i class="fas fa-chart-bar"></i> Statistiken</button>
        <button class="btn btn-sm" onclick="window.archiveMemory()"><i class="fas fa-archive"></i> Archivieren</button>
        <button class="btn btn-sm" onclick="window.resetMemory()"><i class="fas fa-trash-alt"></i> Memory reset</button>
        <button class="btn btn-sm" onclick="window.generateSoul()"><i class="fas fa-magic"></i> Soul generieren</button>
        <button class="btn btn-sm" onclick="window.openWhisperModal()"><i class="fas fa-microphone"></i> Whisper</button>
        <button class="btn btn-sm" onclick="window.openShellModal()"><i class="fas fa-terminal"></i> Shell</button>
        <button class="btn btn-sm" onclick="document.getElementById('file-input-tools').click()"><i class="fas fa-paperclip"></i> Datei anhängen</button>
        <input type="file" id="file-input-tools" class="hidden" multiple onchange="window.handleFileUpload(this.files)">
    </div>`;
}

async function loadMailsPanel() {
    panelTitle.innerHTML = '<i class="fas fa-envelope"></i> Gmail Posteingang';
    panelBody.innerHTML = '<div class="text-center p-8"><div class="loader mx-auto"></div> Lade Mails...</div>';
    try {
        const res = await fetch('/api/gmail/list', { headers: { 'Authorization': `Bearer ${API_KEY}` } });
        const data = await res.json();
        const messages = data.messages || [];
        if(!messages.length) { panelBody.innerHTML = '<div class="text-center p-8 text-[var(--text-muted)]">📭 Keine Mails</div>'; return; }
        panelBody.innerHTML = `<div class="space-y-2">${messages.map(m => `
            <div class="border border-[var(--border)] rounded p-3 hover:bg-[var(--bg-tertiary)] cursor-pointer" onclick="window.loadMailDetail('${m.id}')">
                <div class="font-semibold">${escapeHtml(m.from || 'Unbekannt')}</div>
                <div class="text-sm">${escapeHtml(m.subject || 'Kein Betreff')}</div>
                <div class="text-xs text-[var(--text-muted)] truncate">${escapeHtml(m.snippet || '')}</div>
            </div>
        `).join('')}</div><div id="mail-detail" class="mt-4 hidden"></div>`;
    } catch(e) { panelBody.innerHTML = `<div class="text-[var(--error)]">Fehler: ${e.message}</div>`; }
}

window.loadMailDetail = async function(id) {
    try {
        const res = await fetch(`/api/gmail/message/${id}`, { headers: { 'Authorization': `Bearer ${API_KEY}` } });
        const mail = await res.json();
        const detailDiv = document.getElementById('mail-detail');
        detailDiv.classList.remove('hidden');
        detailDiv.innerHTML = `<div class="border-t border-[var(--border)] mt-4 pt-4">
            <div class="font-bold">${escapeHtml(mail.subject)}</div>
            <div class="text-sm mt-2 whitespace-pre-wrap">${escapeHtml(mail.body || mail.snippet)}</div>
            <textarea id="reply-text" class="chat-input w-full mt-3" rows="3" placeholder="Antwort..."></textarea>
            <button class="btn btn-sm mt-2" onclick="window.sendMailReply('${id}')"><i class="fas fa-reply"></i> Antworten</button>
        </div>`;
    } catch(e) { alert('Fehler beim Laden'); }
};

window.sendMailReply = async function(id) {
    const body = document.getElementById('reply-text')?.value;
    if(!body) return;
    await fetch(`/api/gmail/reply/${id}`, { method: 'POST', headers: { 'Authorization': `Bearer ${API_KEY}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ body }) });
    alert('Antwort gesendet');
};

async function loadGuiPanel() {
    panelTitle.innerHTML = '<i class="fas fa-desktop"></i> GUI Controller';
    panelBody.innerHTML = `<div class="space-y-4"><div class="bg-[var(--bg-tertiary)] p-3 rounded"><div class="flex gap-2"><input id="gui-x" type="number" placeholder="X" class="bg-black border p-1 rounded w-24"><input id="gui-y" type="number" placeholder="Y" class="bg-black border p-1 rounded w-24"><button class="btn btn-sm" onclick="window.guiClick()">Click</button><button class="btn btn-sm" onclick="window.guiRightClick()">Rechts</button></div></div>
    <div><input id="gui-text" placeholder="Text..." class="chat-input w-full"><button class="btn btn-sm mt-1" onclick="window.guiType()">Type</button></div>
    <div class="grid grid-cols-3 gap-1"><button class="btn btn-sm" onclick="window.guiHotkey(['ctrl','c'])">Copy</button><button class="btn btn-sm" onclick="window.guiHotkey(['ctrl','v'])">Paste</button><button class="btn btn-sm" onclick="window.guiOpen('notepad')">Notepad</button></div>
    <button class="btn btn-sm w-full" onclick="window.takeGuiScreenshot()">Screenshot</button>
    <div id="gui-screenshot" class="border rounded h-48 bg-black flex items-center justify-center text-[var(--text-muted)]">Kein Screenshot</div></div>`;
}

window.guiClick = async() => { 
    const x = document.getElementById('gui-x')?.value; 
    const y = document.getElementById('gui-y')?.value; 
    if (x && y) {
        try {
            await fetch('/api/gui/click', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-API-Key': 'dev-key' },
                body: JSON.stringify({ x: parseInt(x), y: parseInt(y) })
            });
            addThinkingStep(`Mausklick bei (${x}, ${y})`, 'fa-mouse-pointer');
        } catch(e) {
            addThinkingStep(`GUI-Fehler: ${e.message}`, 'fa-exclamation-triangle');
        }
    }
};

window.guiRightClick = async() => { 
    const x = document.getElementById('gui-x')?.value; 
    const y = document.getElementById('gui-y')?.value; 
    if (x && y) {
        try {
            await fetch('/api/gui/click', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-API-Key': 'dev-key' },
                body: JSON.stringify({ x: parseInt(x), y: parseInt(y), button: 'right' })
            });
            addThinkingStep(`Rechtsklick bei (${x}, ${y})`, 'fa-mouse-pointer');
        } catch(e) {
            addThinkingStep(`GUI-Fehler: ${e.message}`, 'fa-exclamation-triangle');
        }
    }
};

window.guiType = async() => { 
    const text = document.getElementById('gui-text')?.value; 
    if (text) {
        try {
            await fetch('/api/gui/type', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-API-Key': 'dev-key' },
                body: JSON.stringify({ text })
            });
            addThinkingStep(`Texteingabe: "${text.substring(0, 50)}${text.length > 50 ? '...' : ''}"`, 'fa-keyboard');
        } catch(e) {
            addThinkingStep(`GUI-Fehler: ${e.message}`, 'fa-exclamation-triangle');
        }
    }
};

window.guiHotkey = async(keys) => { 
    try {
        await fetch('/api/gui/hotkey', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-API-Key': 'dev-key' },
            body: JSON.stringify({ keys })
        });
        addThinkingStep(`Hotkey: ${keys.join('+')}`, 'fa-keyboard');
    } catch(e) {
        addThinkingStep(`GUI-Fehler: ${e.message}`, 'fa-exclamation-triangle');
    }
};

window.guiOpen = async(prog) => { 
    try {
        await fetch('/api/gui/open', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-API-Key': 'dev-key' },
            body: JSON.stringify({ program: prog })
        });
        addThinkingStep(`Programm gestartet: ${prog}`, 'fa-rocket');
    } catch(e) {
        addThinkingStep(`GUI-Fehler: ${e.message}`, 'fa-exclamation-triangle');
    }
};

window.takeGuiScreenshot = async() => { 
    try {
        const res = await fetch('/api/gui/screenshot', {
            method: 'POST',
            headers: { 'X-API-Key': 'dev-key' }
        });
        const data = await res.json();
        if (data.success) {
            const screenshotDiv = document.getElementById('gui-screenshot');
            if (screenshotDiv) {
                screenshotDiv.innerHTML = `<img src="/api/view_screenshot?path=${data.path}" class="max-h-full object-contain">`;
            }
            addThinkingStep('Screenshot erstellt', 'fa-camera');
        }
    } catch(e) {
        addThinkingStep(`Screenshot-Fehler: ${e.message}`, 'fa-exclamation-triangle');
    }
};

async function loadComfyPanel() {
    panelTitle.innerHTML = '<i class="fas fa-palette"></i> ComfyUI Generator';
    panelBody.innerHTML = `<div class="space-y-3"><textarea id="comfy-prompt" rows="3" class="chat-input w-full" placeholder="Prompt..."></textarea>
    <div class="grid grid-cols-3 gap-2"><select id="comfy-width" class="model-select"><option value="512">512</option><option value="768">768</option><option value="1024" selected>1024</option></select>
    <select id="comfy-height" class="model-select"><option value="512">512</option><option value="768">768</option><option value="1024" selected>1024</option></select>
    <select id="comfy-steps" class="model-select"><option value="20">20 steps</option><option value="30">30 steps</option></select></div>
    <button class="btn w-full" onclick="window.generateComfyImage()"><i class="fas fa-magic"></i> Generieren</button>
    <div id="comfy-gallery" class="grid grid-cols-2 gap-2 mt-3"></div></div>`;
}

window.generateComfyImage = async function() {
    const prompt = document.getElementById('comfy-prompt')?.value;
    if(!prompt) return;
    const width=parseInt(document.getElementById('comfy-width')?.value||1024), height=parseInt(document.getElementById('comfy-height')?.value||1024), steps=parseInt(document.getElementById('comfy-steps')?.value||20);
    const res = await fetch('/api/comfy/generate',{method:'POST',headers:{'token':API_KEY,'Content-Type':'application/json'},body:JSON.stringify({prompt,width,height,steps})});
    const data=await res.json();
    if(data.status==='success') {
        const gallery=document.getElementById('comfy-gallery');
        const cleanPath = data.image_path?.replace(/\\/g,'/').replace(/^screenshots\//, '');
        const url = `/api/image/${cleanPath}`;
        gallery.innerHTML = `<img src="${url}" class="rounded border border-[var(--accent)] cursor-pointer max-h-48 object-contain" onclick="window.open('${url}')">` + gallery.innerHTML;
    }
};

// ==================== HELP MODAL ====================
function showHelp() {
    const helpContent = `
        <div class="space-y-4">
            <div><h4 class="text-[var(--accent)] font-bold">📌 Allgemeine Befehle</h4><p><code>/help</code> - Diese Hilfe<br><code>/model [name]</code> - Modell wechseln<br><code>/clear</code> - Chat löschen</p></div>
            <div><h4 class="text-[var(--accent)] font-bold">⌨️ Tastatur</h4><p><code>↑</code> <code>↓</code> - Vorherige Befehle durchblättern<br><code>@</code> - Datei-Vorschläge (z.B. @test.txt)</p></div>
            <div><h4 class="text-[var(--accent)] font-bold">📎 Dateien</h4><p><code>@datei.txt</code> - Datei in Kontext laden<br><code>Drag & Drop</code> - Bild/Audio/Text hochladen</p></div>
            <div><h4 class="text-[var(--accent)] font-bold">🎤 Whisper</h4><p>Audio-Datei hochladen oder Tools → Whisper → Aufnahme</p></div>
            <div><h4 class="text-[var(--accent)] font-bold">💻 Shell</h4><p>Tools → Shell: <code>dir, ls, echo, ipconfig</code> uvm.</p></div>
            <div><h4 class="text-[var(--accent)] font-bold">📧 Gmail / Telegram</h4><p>Mails-Panel: Mails lesen & antworten. Telegram-Nachrichten erscheinen automatisch im Chat.</p></div>
            <div><h4 class="text-[var(--accent)] font-bold">🎨 ComfyUI</h4><p>Bilder generieren mit Prompt, negative Prompt optional.</p></div>
            <div><h4 class="text-[var(--accent)] font-bold">🖱️ GUI Control</h4><p>Mausklicks, Tastatureingaben, Programme starten via GUI-Panel.</p></div>
        </div>
    `;
    document.getElementById('help-body').innerHTML = helpContent;
    helpModal.classList.add('active');
}

// ==================== CHAT SEND (MIT LOG-STREAM) ====================
async function sendChat() {
    const message = chatInput.value.trim();
    if(!message || isChatRunning) return;
    
    if (message.trim()) {
        if (commandHistory.length === 0 || commandHistory[commandHistory.length - 1] !== message) commandHistory.push(message);
        if (commandHistory.length > 50) commandHistory.shift();
        historyIndex = -1;
    }
    
    addMessage('Du', message, true, 'fas fa-user');
    chatInput.value = '';
    isChatRunning = true;
    sendBtn.disabled = true;
    stopBtn.disabled = false;
    clearThinkingContainer();
    
    showWaiting(activeModel === '__AUTO__' ? 'Auto' : activeModel);
    
    // Setze initialen Status
    const statusSpan = document.getElementById('waiting-status');
    if (statusSpan) {
        statusSpan.innerHTML = '<i class="fas fa-spinner fa-pulse mr-1"></i> Verbinde mit Gateway...';
    }

    const intentEl = document.getElementById('waiting-intent');
    if (intentEl) intentEl.textContent = '--';

    const hemisphereEl = document.getElementById('waiting-hemisphere');
    if (hemisphereEl) hemisphereEl.textContent = '--';

    const tokensEl = document.getElementById('waiting-tokens');
    if (tokensEl) tokensEl.textContent = '--';

    const modelEl = document.getElementById('waiting-model');
    if (modelEl) modelEl.textContent = activeModel === '__AUTO__' ? 'Auto' : activeModel;

    thinkingStartTime = Date.now();
    if (thinkingInterval) clearInterval(thinkingInterval);
    thinkingInterval = setInterval(() => {
        const timer = document.getElementById('thinking-timer');
        if(timer && thinkingStartTime) timer.textContent = `${((Date.now() - thinkingStartTime) / 1000).toFixed(1)}s`;
    }, 100);
    
    const statusMessages = ["Verbinde mit Gateway...", "Intent wird analysiert...", "Modell wird ausgewählt...", "LLM generiert Antwort...", "Antwort wird verarbeitet..."];
    let statusIndex = 0;
    const statusInterval = setInterval(() => {
        const statusSpan = document.getElementById('waiting-status');
        if(statusSpan) {
            statusIndex = (statusIndex + 1) % statusMessages.length;
            statusSpan.innerHTML = `<i class="fas fa-spinner fa-pulse mr-1"></i> ${statusMessages[statusIndex]}`;
        }
    }, 2000);
    
    // ===== EventSource für Live-Logs =====
    const requestId = Date.now().toString();
    let logStream = null;
    let receivedLogs = new Set();
    
    try {
        // EventSource für Log-Stream öffnen
        console.log(`🔌 Öffne Log-Stream für ${requestId}`);
        logStream = new EventSource(`/api/chat/logs/${requestId}?token=${API_KEY}`);
        
        logStream.onopen = () => {
            console.log('✅ Log-Stream verbunden');
        };
        
        logStream.onmessage = (event) => {
            try {
                const logData = JSON.parse(event.data);
                console.log('📡 Log empfangen:', logData);
                
                if (logData.done) {
                    console.log('🏁 Log-Stream beendet');
                    logStream?.close();
                    return;
                }
                
                // ===== LIVE-UPDATE DER WARTEANIMATION =====
                const logText = logData.text;
                
                // 1. Status-Text aktualisieren
                const statusSpan = document.getElementById('waiting-status');
                if (statusSpan && logText) {
                    let icon = 'fa-spinner';
                    if (logText.includes('Intent')) icon = 'fa-bullseye';
                    else if (logText.includes('Modell') || logText.includes('Model')) icon = 'fa-microchip';
                    else if (logText.includes('Hemisphäre') || logText.includes('Routing')) icon = 'fa-code-branch';
                    else if (logText.includes('OLLAMA')) icon = 'fa-robot';
                    else if (logText.includes('Token')) icon = 'fa-chart-line';
                    
                    statusSpan.innerHTML = `<i class="fas ${icon} fa-pulse mr-1"></i> ${logText}`;
                }
                
                // 2. Intent extrahieren und anzeigen
                if (logText && (logText.includes('INTENT:') || logText.includes('Intent:'))) {
                    const intentMatch = logText.match(/INTENT:\s*(\w+)/i) || logText.match(/Intent:\s*(\w+)/i);
                    if (intentMatch) {
                        const intentEl = document.getElementById('waiting-intent');
                        if (intentEl) intentEl.textContent = intentMatch[1];
                    }
                }
                
                // 3. Hemisphäre extrahieren und anzeigen
                if (logText && (logText.includes('Routing zu') || logText.includes('Hemisphäre:'))) {
                    let hemisphere = '--';
                    if (logText.includes('left') || logText.includes('links')) hemisphere = '🔵 links';
                    else if (logText.includes('right') || logText.includes('rechts')) hemisphere = '🟣 rechts';
                    else if (logText.includes('bridge')) hemisphere = '🌉 bridge';
                    
                    const hemisphereEl = document.getElementById('waiting-hemisphere');
                    if (hemisphereEl && hemisphere !== '--') hemisphereEl.textContent = hemisphere;
                }
                
                // 4. Modell extrahieren und anzeigen
                if (logText && (logText.includes('Modell:') || logText.includes('model='))) {
                    const modelMatch = logText.match(/Modell:\s*(\S+)/i) || logText.match(/model[=:]\s*(\S+)/i);
                    if (modelMatch) {
                        const modelEl = document.getElementById('waiting-model');
                        if (modelEl) modelEl.textContent = modelMatch[1];
                    }
                }
                
                // 5. Token-Statistiken extrahieren und anzeigen
                if (logText && (logText.includes('in_tok') || logText.includes('Token'))) {
                    const inMatch = logText.match(/in_tok[=~](\d+)/i);
                    const outMatch = logText.match(/out_tok=(\d+)/i);
                    
                    const tokensEl = document.getElementById('waiting-tokens');
                    if (tokensEl) {
                        let tokenText = '';
                        if (inMatch) tokenText = `in:${inMatch[1]}`;
                        if (outMatch) tokenText += ` / out:${outMatch[1]}`;
                        if (tokenText) tokensEl.textContent = tokenText;
                    }
                }
                
                // 6. Wenn explizite Werte im Log stehen
                if (logText && logText.includes('Token-Statistik')) {
                    const tokenMatch = logText.match(/in:(\d+)\s*\/\s*out:(\d+)/i);
                    if (tokenMatch) {
                        const tokensEl = document.getElementById('waiting-tokens');
                        if (tokensEl) tokensEl.textContent = `in:${tokenMatch[1]} / out:${tokenMatch[2]}`;
                    }
                }
                
                // 7. Füge Log als Thinking-Step hinzu
                const logKey = `${logData.text}|${logData.time}`;
                if (!receivedLogs.has(logKey)) {
                    receivedLogs.add(logKey);
                    addThinkingStep(logData.text, logData.icon || 'fa-terminal');
                }
                
            } catch (e) {
                console.error('Log-Parse Fehler:', e);
            }
        };
        
        logStream.onerror = (error) => {
            console.error('Log-Stream Fehler:', error);
            if (logStream) {
                logStream.close();
                logStream = null;
            }
        };
        
        // ===== FETCH-REQUEST MIT REQUEST_ID =====
        currentChatController = new AbortController();
        const res = await fetch('/chat', {
            method: 'POST',
            headers: { 'token': API_KEY, 'Content-Type': 'application/json' },
            signal: currentChatController.signal,
            body: JSON.stringify({ 
                message, 
                model: activeModel === '__AUTO__' ? null : activeModel, 
                request_id: requestId 
            })
        });
        
        const data = await res.json();
        clearInterval(statusInterval);
        
        let tokenInfo = '--';
        if(data.token_stats) tokenInfo = `in:${data.token_stats.input || '?'} / out:${data.token_stats.output || '?'}`;
        else if(data.input_tokens || data.output_tokens) tokenInfo = `in:${data.input_tokens || '?'} / out:${data.output_tokens || '?'}`;
        
        let intentText = data.intent || 'chat';
        let hemisphereText = '--';
        if(data.hemisphere) hemisphereText = data.hemisphere === 'left' ? '🔵 links (analytisch)' : '🟣 rechts (kreativ)';
        
        updateWaitingStats(tokenInfo, intentText, hemisphereText, `✅ Antwort erhalten in ${((Date.now() - thinkingStartTime) / 1000).toFixed(1)}s`);
        
        // Warte kurz auf letzte Logs
        await new Promise(resolve => setTimeout(resolve, 500));
        
        setTimeout(() => {
            hideWaiting();
        }, 1500);
        
        clearInterval(thinkingInterval);
        thinkingInterval = null;
        
        if(data.status === 'success') {
            addMessage('GABI', data.reply, false, 'fas fa-robot');
            if(data.model_used) addThinkingStep(`Modell: ${data.model_used}`, 'fa-brain');
            if(data.token_stats) addThinkingStep(`📊 Token: Eingabe ${data.token_stats.input || '?'} / Ausgabe ${data.token_stats.output || '?'}`, 'fa-chart-line');
            if(data.thinking_steps && Array.isArray(data.thinking_steps)) {
                data.thinking_steps.forEach(step => {
                    const stepKey = `${step.text}|${step.time}`;
                    if (!receivedLogs.has(stepKey)) {
                        addThinkingStep(step.text, step.icon || 'fa-terminal');
                    }
                });
            }
        } else throw new Error(data.reply || 'Fehler');
        
    } catch(e) {
        clearInterval(statusInterval);
        clearInterval(thinkingInterval);
        thinkingInterval = null;
        
        updateWaitingStats(null, null, null, `❌ Fehler: ${e.message}`);
        setTimeout(() => {
            hideWaiting();
        }, 2000);
        
        addMessage('System', `Fehler: ${e.message}`, false, 'fas fa-exclamation-triangle');
        addThinkingStep(`❌ Fehler: ${e.message}`, 'fa-exclamation-triangle');
    } finally {
        isChatRunning = false;
        sendBtn.disabled = false;
        stopBtn.disabled = true;
        currentChatController = null;
        if (logStream) {
            logStream.close();
            logStream = null;
        }
    }
}

function stopCurrentTask() {
    if(currentChatController) {
        currentChatController.abort();
        currentChatController = null;
    }
    addThinkingStep('Anfrage abgebrochen', 'fa-stop');
    isChatRunning = false;
    sendBtn.disabled = false;
    stopBtn.disabled = true;
    if(thinkingInterval) {
        clearInterval(thinkingInterval);
        thinkingInterval = null;
    }
    hideWaiting();
}

// ==================== STATUS & MODELS ====================
async function checkStatus() {
    try {
        const res = await fetch('/status');
        const data = await res.json();
        if(data.services?.ollama) {
            availableModels = data.services.ollama.available_models || [];
            modelSelector.innerHTML = '<option value="__AUTO__">Auto (Gateway)</option>' + availableModels.map(m => `<option value="${m}">${m}</option>`).join('');
            const saved = localStorage.getItem('lastUsedLLM');
            if(saved && availableModels.includes(saved)) modelSelector.value = saved;
            llmStatus.innerHTML = '<span class="status-badge status-online">🟢 Ollama verbunden</span>';
        } else llmStatus.innerHTML = '<span class="status-badge status-offline">🔴 Offline</span>';
    } catch(e) { llmStatus.innerHTML = '<span class="status-badge status-offline">⚠️ Fehler</span>'; }
}

// ==================== HELPER FUNCTIONS ====================
window.openModalAPI = async (url, title) => {
    const res = await fetch(url, { headers: { 'Authorization': `Bearer ${API_KEY}` } });
    const data = await res.json();
    const modal = document.createElement('div');
    modal.className = 'fixed inset-0 bg-black/80 flex items-center justify-center z-[2000]';
    modal.innerHTML = `<div class="bg-[var(--bg-secondary)] border border-[var(--border)] rounded-xl max-w-2xl w-full max-h-[80vh] overflow-auto p-4"><div class="flex-between"><h3 class="text-[var(--accent)]">${title}</h3><button onclick="this.closest('.fixed').remove()">✖</button></div><pre class="text-sm mt-2 whitespace-pre-wrap">${escapeHtml(JSON.stringify(data, null, 2))}</pre></div>`;
    document.body.appendChild(modal);
};

window.showMemoryStats = async () => { 
    const res=await fetch('/api/memory/stats',{headers:{'Authorization':`Bearer ${API_KEY}`}}); 
    const d=await res.json(); 
    alert(JSON.stringify(d.stats,null,2)); 
};

window.archiveMemory = async () => { 
    await fetch('/api/memory/archive',{method:'POST',headers:{'Authorization':`Bearer ${API_KEY}`}}); 
    addThinkingStep('Memory archiviert','fa-archive'); 
};

window.resetMemory = async () => { 
    if(confirm('Reset?')){ 
        await fetch('/api/memory/reset',{method:'POST',headers:{'Authorization':`Bearer ${API_KEY}`}}); 
        addThinkingStep('Memory zurückgesetzt','fa-trash'); 
    } 
};

window.generateSoul = async () => { 
    const res=await fetch('/api/memory/generate-soul',{method:'POST',headers:{'Authorization':`Bearer ${API_KEY}`}}); 
    const d=await res.json(); 
    alert(d.message); 
};

window.openWhisperModal = () => { 
    alert('Whisper: Audio-Datei per Drag&Drop in Chat oder über Datei-Upload hochladen.'); 
};

window.openShellModal = () => { 
    const cmd = prompt('Shell Befehl eingeben:'); 
    if(cmd) fetch('/shell',{method:'POST',headers:{'token':API_KEY,'Content-Type':'application/json'},body:JSON.stringify({command:cmd})}).then(r=>r.json()).then(d=>alert(d.stdout||d.stderr||'OK')); 
};

window.handleFileUpload = async (files) => { 
    if(files.length) addThinkingStep(`Datei ${files[0].name} hochgeladen`, 'fa-upload'); 
};

// ==================== INITIALIZATION ====================
function init() {
    // DOM Elements initialisieren
    chatContainer = document.getElementById('chat-container');
    chatInput = document.getElementById('chat-input');
    sendBtn = document.getElementById('send-btn');
    stopBtn = document.getElementById('stop-btn');
    modelSelector = document.getElementById('model-selector');
    llmStatus = document.getElementById('llm-status');
    panelOverlay = document.getElementById('panel-overlay');
    panelTitle = document.getElementById('panel-title');
    panelBody = document.getElementById('panel-body');
    closePanelBtn = document.getElementById('close-panel');
    helpModal = document.getElementById('help-modal');
    closeHelpBtn = document.getElementById('close-help');
    helpBtn = document.getElementById('help-btn');
    
    // Scroll Button erstellen
    scrollBtn = document.createElement('button');
    scrollBtn.className = 'scroll-btn';
    scrollBtn.innerHTML = '<i class="fas fa-arrow-down"></i>';
    document.body.appendChild(scrollBtn);
    
    // Event Listener
    setupEventListeners();
    
    // Observers
    setupObservers();
    
    // Timer
    updateTime();
    setInterval(updateTime, 1000);
    
    // Status
    checkStatus();
    setInterval(checkStatus, 10000);
    
    // Willkommensnachricht
    addMessage('System', 'Willkommen beim modernen GABI Gateway Dashboard. Klicke auf <strong class="text-[var(--accent)]">Hilfe</strong> für alle Befehle.<br><span class="text-xs">⌨️ Pfeiltasten ↑↓ für Befehlshistorie | @ für Datei-Vorschläge</span>', false, 'fas fa-info-circle');
}

function setupEventListeners() {
    // Scroll Button
    scrollBtn.addEventListener('click', () => {
        if (lastScrollDirection === 'down' || chatContainer.scrollTop + chatContainer.clientHeight < chatContainer.scrollHeight - 100) {
            chatContainer.scrollTo({ top: chatContainer.scrollHeight, behavior: 'smooth' });
        } else {
            chatContainer.scrollTo({ top: 0, behavior: 'smooth' });
        }
    });
    
    // Chat Container Scroll
    chatContainer.addEventListener('scroll', () => {
        const isNearBottom = chatContainer.scrollHeight - chatContainer.scrollTop - chatContainer.clientHeight < 50;
        if (!isNearBottom) {
            userScrolledUp = true;
            scrollBtn.classList.add('visible');
            if (scrollTimeout) clearTimeout(scrollTimeout);
            scrollTimeout = setTimeout(() => { userScrolledUp = false; }, 5000);
        } else {
            userScrolledUp = false;
            scrollBtn.classList.remove('visible');
        }
        updateScrollButton();
    });
    
    // Buttons
    sendBtn.addEventListener('click', sendChat);
    stopBtn.addEventListener('click', stopCurrentTask);
    
    // Panel Buttons
    document.querySelectorAll('.btn[data-panel]').forEach(btn => {
        btn.addEventListener('click', () => openPanel(btn.dataset.panel));
    });
    closePanelBtn.addEventListener('click', closeAllPanels);
    panelOverlay.addEventListener('click', (e) => { if(e.target === panelOverlay) closeAllPanels(); });
    
    // Help
    helpBtn.addEventListener('click', showHelp);
    closeHelpBtn.addEventListener('click', () => helpModal.classList.remove('active'));
    helpModal.addEventListener('click', (e) => { if(e.target === helpModal) helpModal.classList.remove('active'); });
    
    // Model Selector
    modelSelector.addEventListener('change', (e) => { 
        activeModel = e.target.value; 
        localStorage.setItem('lastUsedLLM', activeModel); 
        addThinkingStep(`Modell gewechselt: ${activeModel}`, 'fa-exchange-alt'); 
    });
    
    // Command History
    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowUp') {
            e.preventDefault();
            if (historyIndex < commandHistory.length - 1) {
                historyIndex++;
                chatInput.value = commandHistory[commandHistory.length - 1 - historyIndex] || '';
                chatInput.setSelectionRange(chatInput.value.length, chatInput.value.length);
            }
        } else if (e.key === 'ArrowDown') {
            e.preventDefault();
            if (historyIndex > 0) {
                historyIndex--;
                chatInput.value = commandHistory[commandHistory.length - 1 - historyIndex] || '';
                chatInput.setSelectionRange(chatInput.value.length, chatInput.value.length);
            } else if (historyIndex === 0) {
                historyIndex = -1;
                chatInput.value = '';
            }
        } else if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendChat();
        }
    });
    
    // File Suggestions
    chatInput.addEventListener('input', async function() {
        const value = this.value;
        const cursorPos = this.selectionStart;
        const textBeforeCursor = value.slice(0, cursorPos);
        const atIndex = textBeforeCursor.lastIndexOf('@');
        const charBeforeAt = atIndex > 0 ? textBeforeCursor[atIndex - 1] : null;
        const isWordStart = charBeforeAt === null || /\s/.test(charBeforeAt);
        
        if (atIndex >= 0 && isWordStart) {
            const queryPart = textBeforeCursor.slice(atIndex + 1);
            const queryHasSpace = /\s/.test(queryPart);
            if (!queryHasSpace) {
                const suggestions = await fetchFileSuggestions(queryPart);
                renderFileSuggestions(suggestions.slice(0, 30));
            } else renderFileSuggestions([]);
        } else renderFileSuggestions([]);
    });
    
    document.addEventListener('click', (e) => {
        const box = document.getElementById('file-suggest');
        if (box && !box.contains(e.target) && e.target !== chatInput) renderFileSuggestions([]);
    });
}

function setupObservers() {
    // Resize-Observer
    const resizeObserver = new ResizeObserver(() => {
        adjustContainerHeight();
        if (!userScrolledUp) smoothScrollToBottom();
    });
    resizeObserver.observe(chatContainer);
    
    // MutationObserver
    const mutationObserver = new MutationObserver(() => {
        adjustContainerHeight();
        if (!userScrolledUp) smoothScrollToBottom();
    });
    mutationObserver.observe(chatContainer, { childList: true, subtree: true, characterData: true });
}

function updateTime() { 
    const timeEl = document.getElementById('current-time');
    if (timeEl) timeEl.textContent = new Date().toLocaleTimeString('de-DE'); 
}

// Start when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}