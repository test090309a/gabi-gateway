const API_KEY_BEARER = 'sysop';  // Für Bearer Token Auth

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
        // Auch hier konsistent mit Bearer Token
        const response = await fetch('/api/status', { 
            headers: { 
                'Authorization': 'Bearer sysop'  // Geändert!
            } 
        });
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
            
            // Automatischer Stop nach 5 Sekunden
            setTimeout(() => {
                if (isRecording && mediaRecorder && mediaRecorder.state === "recording") {
                    mediaRecorder.stop();
                }
            }, 5000);
        } catch (err) {
            voiceStatus.textContent = '❌ Mikrofon nicht verfügbar';
            console.error("Mikrofon Fehler:", err);
        }
    }
}

async function transcribeAudio(blob) {
    const formData = new FormData();
    formData.append('file', blob, 'audio.webm');
    try {
        voiceStatus.textContent = '🎤 Transkribiere...';
        
        const response = await fetch('/api/whisper/transcribe/sync', {
            method: 'POST',
            headers: {
                'Authorization': 'Bearer sysop'  // Wichtig: Bearer Token!
            },
            body: formData
        });
        
        const data = await response.json();
        voiceStatus.textContent = '';
        
        if (response.status === 403) {
            console.error("API-Key ungültig!");
            addSystemMessage(`❌ API-Key ungültig`);
            voiceStatus.textContent = '❌ API-Key ungültig';
            return;
        }
        
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
                                'Authorization': 'Bearer sysop'  // Auch hier Bearer Token!
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
            addSystemMessage(`❌ Transkription fehlgeschlagen: ${data.error || 'Unbekannt'}`);
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
            headers: { 
                'Authorization': 'Bearer sysop'
            },
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
        const response = await fetch('/api/models', { 
            headers: { 
                'Authorization': 'Bearer sysop' 
            } 
        });
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
            headers: { 
                'Content-Type': 'application/json', 
                'Authorization': 'Bearer sysop'
            },
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
        // Ändere von X-API-Key zu Authorization Bearer
        const response = await fetch('/api/telegram/messages?limit=100', { 
            headers: { 
                'Authorization': 'Bearer sysop'  // Geändert!
            } 
        });
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
        console.error('Telegram load error:', e);
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
        // Ändere von X-API-Key zu Authorization Bearer
        const response = await fetch('/api/telegram/send', {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json', 
                'Authorization': 'Bearer sysop'  // Geändert!
            },
            body: JSON.stringify({ message: msg })
        });
        const data = await response.json();
        input.value = '';
        if (data.status === 'success') {
            addSystemMessage(`✅ Telegram: ${msg.substring(0, 50)}...`);
        } else {
            addSystemMessage(`❌ Telegram Fehler: ${data.message || 'Unbekannt'}`);
        }
        setTimeout(loadTelegramMessages, 500);
    } catch (e) {
        console.error('Telegram send error:', e);
        addSystemMessage(`❌ Telegram Fehler: ${e.message}`);
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