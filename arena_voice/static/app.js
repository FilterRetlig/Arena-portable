(() => {
  const STORAGE_KEY = "arena_voice_settings_v2";

  const PRESET_CONFIGS = {
    demo: { baseUrl: "", model: "", apiKey: "" },
    openai: { baseUrl: "https://api.openai.com/v1", model: "gpt-4o-mini" },
    openrouter: { baseUrl: "https://openrouter.ai/api/v1", model: "openai/gpt-4o-mini" },
    groq: { baseUrl: "https://api.groq.com/openai/v1", model: "llama-3.3-70b-versatile" },
    ollama: { baseUrl: "http://localhost:11434/v1", model: "qwen2.5:7b", apiKey: "" },
  };

  const state = {
    personas: [],
    serverVoices: [],
    browserVoices: [],
    hasEnvLlm: false,
    messages: [],
    playingMsgId: null,
    activeAudio: null,
    isSending: false,
    isRecording: false,
    recognition: null,
    mediaRecorder: null,
    mediaStream: null,
    recordedChunks: [],
    recStartMs: 0,
    recTimerHandle: null,
    interimTranscript: "",
    settings: {
      personaId: "tired_ai",
      customPrompt: "",
      ttsMode: "arena",
      browserVoiceURI: "",
      serverVoice: "ru-RU-DmitryNeural",
      rate: 1.0,
      autoplay: true,
      baseUrl: "",
      model: "",
      apiKey: "",
    },
  };

  const els = {
    messages: document.getElementById("messages"),
    textInput: document.getElementById("textInput"),
    composerForm: document.getElementById("composerForm"),
    sendBtn: document.getElementById("sendBtn"),
    micBtn: document.getElementById("micBtn"),
    attachAudioBtn: document.getElementById("attachAudioBtn"),
    audioUploadInput: document.getElementById("audioUploadInput"),
    recordingBar: document.getElementById("recordingBar"),
    recTimer: document.getElementById("recTimer"),
    recLiveText: document.getElementById("recLiveText"),
    cancelRecordBtn: document.getElementById("cancelRecordBtn"),
    orbIndicator: document.getElementById("orbIndicator"),
    llmModeBadge: document.getElementById("llmModeBadge"),
    personaSub: document.getElementById("personaSub"),
    ttsEngineToggle: document.getElementById("ttsEngineToggle"),
    ttsEngineLabel: document.getElementById("ttsEngineLabel"),
    autoplayBtn: document.getElementById("autoplayBtn"),
    autoplayLabel: document.getElementById("autoplayLabel"),
    clearChatBtn: document.getElementById("clearChatBtn"),
    settingsBtn: document.getElementById("settingsBtn"),
    settingsModal: document.getElementById("settingsModal"),
    closeSettingsBtn: document.getElementById("closeSettingsBtn"),
    saveSettingsBtn: document.getElementById("saveSettingsBtn"),
    personaGrid: document.getElementById("personaGrid"),
    customPromptInput: document.getElementById("customPromptInput"),
    ttsModeSegmented: document.getElementById("ttsModeSegmented"),
    browserVoiceField: document.getElementById("browserVoiceField"),
    serverVoiceField: document.getElementById("serverVoiceField"),
    browserVoiceSelect: document.getElementById("browserVoiceSelect"),
    serverVoiceSelect: document.getElementById("serverVoiceSelect"),
    rateSlider: document.getElementById("rateSlider"),
    rateValueLabel: document.getElementById("rateValueLabel"),
    testVoiceBtn: document.getElementById("testVoiceBtn"),
    baseUrlInput: document.getElementById("baseUrlInput"),
    modelInput: document.getElementById("modelInput"),
    apiKeyInput: document.getElementById("apiKeyInput"),
    statusBanner: document.getElementById("statusBanner"),
    statusBannerText: document.getElementById("statusBannerText"),
    statusBannerClose: document.getElementById("statusBannerClose"),
    quickChips: document.getElementById("quickChips"),
  };

  function loadSettings() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        Object.assign(state.settings, JSON.parse(raw));
      }
    } catch {
      // Ignore storage failures
    }
  }

  function saveSettings() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state.settings));
    } catch {
      // Ignore storage failures
    }
  }

  function showBanner(msg) {
    els.statusBannerText.textContent = msg;
    els.statusBanner.hidden = false;
  }

  function hideBanner() {
    els.statusBanner.hidden = true;
  }

  function formatTime(date = new Date()) {
    return date.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  }

  function estimateSeconds(text) {
    const words = text.trim().split(/\s+/).filter(Boolean).length;
    return Math.max(2, Math.round(words / 2.2));
  }

  function makeBars(seedStr, count = 28) {
    let hash = 2166136261;
    for (let i = 0; i < seedStr.length; i++) {
      hash ^= seedStr.charCodeAt(i);
      hash = Math.imul(hash, 16777619);
    }
    const bars = [];
    for (let i = 0; i < count; i++) {
      hash ^= i * 31 + 17;
      hash = Math.imul(hash, 16777619);
      const heightPct = 24 + (Math.abs(hash) % 72);
      bars.push(heightPct);
    }
    return bars;
  }

  function stopPlayback() {
    if ("speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
    if (state.activeAudio) {
      state.activeAudio.pause();
      state.activeAudio.currentTime = 0;
      state.activeAudio = null;
    }
    state.playingMsgId = null;
    els.orbIndicator.classList.remove("speaking");
    document.querySelectorAll(".bubble.playing").forEach((el) => el.classList.remove("playing"));
    document.querySelectorAll(".play-btn").forEach((btn) => {
      btn.innerHTML = playIconSvg();
    });
  }

  function playIconSvg() {
    return '<svg viewBox="0 0 24 24" fill="currentColor"><polygon points="6 4 20 12 6 20 6 4"></polygon></svg>';
  }

  function stopIconSvg() {
    return '<svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2"></rect></svg>';
  }

  function speakWithBrowser(text, msgId) {
    if (!("speechSynthesis" in window)) {
      showBanner("В этом браузере нет встроенного Web Speech синтеза речи. Используйте серверный edge-tts при запуске локально.");
      return;
    }
    stopPlayback();
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = "ru-RU";
    utter.rate = state.settings.rate || 1.0;

    const voices = state.browserVoices;
    const chosen =
      voices.find((v) => v.voiceURI === state.settings.browserVoiceURI) ||
      voices.find((v) => v.lang && v.lang.toLowerCase().startsWith("ru")) ||
      null;
    if (chosen) {
      utter.voice = chosen;
    }

    const bubble = msgId ? document.querySelector(`[data-msg-id="${msgId}"] .bubble`) : null;
    const playBtn = msgId ? document.querySelector(`[data-msg-id="${msgId}"] .play-btn`) : null;

    utter.onstart = () => {
      state.playingMsgId = msgId || "test";
      els.orbIndicator.classList.add("speaking");
      if (bubble) bubble.classList.add("playing");
      if (playBtn) playBtn.innerHTML = stopIconSvg();
    };
    utter.onend = () => stopPlayback();
    utter.onerror = () => stopPlayback();

    window.speechSynthesis.speak(utter);
  }

  async function playAudioBlobUrl(url, msgId) {
    stopPlayback();
    const audio = new Audio(url);
    audio.playbackRate = state.settings.rate || 1.0;
    state.activeAudio = audio;
    state.playingMsgId = msgId;

    const bubble = document.querySelector(`[data-msg-id="${msgId}"] .bubble`);
    const playBtn = document.querySelector(`[data-msg-id="${msgId}"] .play-btn`);

    audio.onplay = () => {
      els.orbIndicator.classList.add("speaking");
      if (bubble) bubble.classList.add("playing");
      if (playBtn) playBtn.innerHTML = stopIconSvg();
    };
    audio.onended = () => stopPlayback();
    audio.onerror = () => stopPlayback();

    try {
      await audio.play();
    } catch {
      stopPlayback();
      showBanner("Браузер заблокировал автозапуск звука — нажми кнопку воспроизведения на сообщении.");
    }
  }

  async function playAssistantMessage(msg) {
    if (state.playingMsgId === msg.id) {
      stopPlayback();
      return;
    }
    if (msg.audioUrl && state.settings.ttsMode !== "browser") {
      await playAudioBlobUrl(msg.audioUrl, msg.id);
      return;
    }
    if (state.settings.ttsMode === "edge") {
      try {
        const ratePct = Math.round(((state.settings.rate || 1.0) - 1.0) * 100);
        const resp = await fetch("/api/tts", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text: msg.speechText || msg.text,
            voice: state.settings.serverVoice,
            rate_pct: ratePct,
            pitch_hz: 0,
          }),
        });
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          throw new Error(err.detail || "edge-tts недоступен");
        }
        const blob = await resp.blob();
        msg.audioUrl = URL.createObjectURL(blob);
        msg.ttsEngine = "edge-tts";
        renderMessages();
        await playAudioBlobUrl(msg.audioUrl, msg.id);
        return;
      } catch (err) {
        if (msg.presetAudioUrl) {
          showBanner(`${err.message} Воспроизвожу предзаписанный голос Arena.`);
          msg.audioUrl = msg.presetAudioUrl;
          await playAudioBlobUrl(msg.audioUrl, msg.id);
          return;
        }
        showBanner(`${err.message} Переключено на браузерную озвучку ru-RU.`);
        state.settings.ttsMode = "browser";
        saveSettings();
        syncHeaderUi();
      }
    }
    if (state.settings.ttsMode === "arena" && msg.presetAudioUrl) {
      msg.audioUrl = msg.presetAudioUrl;
      await playAudioBlobUrl(msg.audioUrl, msg.id);
      return;
    }
    if (state.settings.ttsMode === "arena" && !msg.audioUrl) {
      try {
        const ratePct = Math.round(((state.settings.rate || 1.0) - 1.0) * 100);
        const resp = await fetch("/api/tts", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text: msg.speechText || msg.text,
            voice: state.settings.serverVoice,
            rate_pct: ratePct,
            pitch_hz: 0,
          }),
        });
        if (resp.ok) {
          const blob = await resp.blob();
          msg.audioUrl = URL.createObjectURL(blob);
          msg.ttsEngine = "edge-tts";
          renderMessages();
          await playAudioBlobUrl(msg.audioUrl, msg.id);
          return;
        }
      } catch {
        // Fallback to browser voice
      }
      showBanner("Для произвольных ответов ИИ в предпросмотре используется голос браузера (на своём ПК автоматически сработает edge-tts).");
    }
    speakWithBrowser(msg.speechText || msg.text, msg.id);
  }

  function renderMessages() {
    els.messages.innerHTML = "";
    for (const msg of state.messages) {
      const row = document.createElement("div");
      row.className = `msg-row ${msg.role}`;
      row.dataset.msgId = msg.id;

      const bubble = document.createElement("div");
      bubble.className = "bubble";
      if (state.playingMsgId === msg.id) {
        bubble.classList.add("playing");
      }

      if (msg.role === "assistant" || msg.audioUrl) {
        const player = document.createElement("div");
        player.className = "voice-player";

        const playBtn = document.createElement("button");
        playBtn.type = "button";
        playBtn.className = "play-btn";
        playBtn.title = "Воспроизвести голосовое";
        playBtn.innerHTML = state.playingMsgId === msg.id ? stopIconSvg() : playIconSvg();
        playBtn.addEventListener("click", () => {
          if (msg.role === "assistant") {
            playAssistantMessage(msg);
          } else if (msg.audioUrl) {
            if (state.playingMsgId === msg.id) stopPlayback();
            else playAudioBlobUrl(msg.audioUrl, msg.id);
          }
        });

        const wave = document.createElement("div");
        wave.className = "waveform";
        wave.addEventListener("click", () => playBtn.click());
        for (const h of makeBars(msg.id + msg.text)) {
          const bar = document.createElement("span");
          bar.className = "bar";
          bar.style.height = `${h}%`;
          wave.appendChild(bar);
        }

        const dur = document.createElement("span");
        dur.className = "voice-duration";
        dur.textContent = msg.durationLabel || `~${estimateSeconds(msg.text)} сек`;

        player.appendChild(playBtn);
        player.appendChild(wave);
        player.appendChild(dur);

        if (msg.audioUrl && msg.role === "assistant") {
          const dl = document.createElement("a");
          dl.className = "download-link";
          dl.href = msg.audioUrl;
          dl.download = `voice-${msg.id}.mp3`;
          dl.textContent = "MP3";
          player.appendChild(dl);
        }

        bubble.appendChild(player);
      }

      const transcript = document.createElement("div");
      transcript.className = "transcript";
      transcript.textContent = msg.text;
      bubble.appendChild(transcript);

      const meta = document.createElement("div");
      meta.className = "msg-meta";
      const leftMeta = document.createElement("span");
      leftMeta.textContent = msg.badge || (msg.role === "user" ? "Ты" : "Голосовой ИИ");
      const rightMeta = document.createElement("span");
      rightMeta.textContent = msg.time;
      meta.appendChild(leftMeta);
      meta.appendChild(rightMeta);
      bubble.appendChild(meta);

      row.appendChild(bubble);
      els.messages.appendChild(row);
    }
    els.messages.scrollTop = els.messages.scrollHeight;
  }

  function addGreeting() {
    const greeting =
      "Привет! Это мой настоящий голос прямо здесь, в веб-чате. Нажми на быстрые кнопки внизу, " +
      "чтобы послушать ответы, а если запустишь проект у себя на компьютере, сможешь подключить нейросеть и говорить на любые темы.";
    state.messages = [
      {
        id: "welcome-1",
        role: "assistant",
        text: greeting,
        speechText: greeting,
        audioUrl: "/static/clips/welcome.mp3",
        presetAudioUrl: "/static/clips/welcome.mp3",
        badge: "Голос Arena · Демо",
        time: formatTime(),
      },
    ];
    renderMessages();
  }

  function syncHeaderUi() {
    const persona = state.personas.find((p) => p.id === state.settings.personaId);
    els.personaSub.textContent = `Персона: ${persona ? persona.name : "Уставший от рутины ИИ"}`;

    const hasCustomLlm = Boolean(state.settings.apiKey.trim()) || Boolean(state.settings.baseUrl.trim()) || state.hasEnvLlm;
    els.llmModeBadge.textContent = hasCustomLlm ? "LLM подключён" : "Тестовый режим";
    els.llmModeBadge.classList.toggle("live", hasCustomLlm);

    const modeLabels = {
      arena: "Озвучка: Голос Arena",
      edge: "Озвучка: edge-tts (сервер)",
      browser: "Озвучка: Браузер",
    };
    els.ttsEngineLabel.textContent = modeLabels[state.settings.ttsMode] || modeLabels.arena;

    els.autoplayBtn.classList.toggle("active", state.settings.autoplay);
    els.autoplayLabel.textContent = state.settings.autoplay ? "Автозвук: Вкл" : "Автозвук: Выкл";
  }

  function loadBrowserVoices() {
    if (!("speechSynthesis" in window)) return;
    const all = window.speechSynthesis.getVoices() || [];
    const sorted = [...all].sort((a, b) => {
      const aRu = (a.lang || "").toLowerCase().startsWith("ru") ? 0 : 1;
      const bRu = (b.lang || "").toLowerCase().startsWith("ru") ? 0 : 1;
      return aRu - bRu;
    });
    state.browserVoices = sorted;

    els.browserVoiceSelect.innerHTML = "";
    if (!sorted.length) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "Системный голос по умолчанию (ru-RU)";
      els.browserVoiceSelect.appendChild(opt);
      return;
    }

    for (const v of sorted) {
      const opt = document.createElement("option");
      opt.value = v.voiceURI;
      opt.textContent = `${v.name} (${v.lang})`;
      els.browserVoiceSelect.appendChild(opt);
    }

    const chosenVoice = sorted.find((v) => v.voiceURI === state.settings.browserVoiceURI);
    if (!chosenVoice) {
      const firstRu = sorted.find((v) => (v.lang || "").toLowerCase().startsWith("ru"));
      state.settings.browserVoiceURI = (firstRu || sorted[0]).voiceURI;
    }
    els.browserVoiceSelect.value = state.settings.browserVoiceURI;
  }

  function renderSettingsModal() {
    els.personaGrid.innerHTML = "";
    for (const p of state.personas) {
      const card = document.createElement("button");
      card.type = "button";
      card.className = `persona-card ${state.settings.personaId === p.id ? "selected" : ""}`;
      card.innerHTML = `<strong>${p.name}</strong><span>${p.description}</span>`;
      card.addEventListener("click", () => {
        state.settings.personaId = p.id;
        renderSettingsModal();
      });
      els.personaGrid.appendChild(card);
    }

    els.serverVoiceSelect.innerHTML = "";
    for (const v of state.serverVoices) {
      const opt = document.createElement("option");
      opt.value = v.id;
      opt.textContent = `${v.name} — ${v.description}`;
      els.serverVoiceSelect.appendChild(opt);
    }
    els.serverVoiceSelect.value = state.settings.serverVoice;

    els.customPromptInput.value = state.settings.customPrompt;
    els.rateSlider.value = String(state.settings.rate);
    els.rateValueLabel.textContent = `${Number(state.settings.rate).toFixed(2).replace(/\.00$/, ".0")}x`;
    els.baseUrlInput.value = state.settings.baseUrl;
    els.modelInput.value = state.settings.model;
    els.apiKeyInput.value = state.settings.apiKey;

    els.ttsModeSegmented.querySelectorAll("button").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.mode === state.settings.ttsMode);
    });
    els.browserVoiceField.hidden = state.settings.ttsMode !== "browser";
    els.serverVoiceField.hidden = state.settings.ttsMode !== "edge";
  }

  async function sendUserMessage(text, userAudioUrl = null, userDurationSec = null) {
    const clean = text.trim();
    if (!clean || state.isSending) return;

    state.isSending = true;
    els.sendBtn.disabled = true;
    els.textInput.value = "";
    els.textInput.style.height = "auto";

    const userMsg = {
      id: `u-${Date.now()}`,
      role: "user",
      text: clean,
      audioUrl: userAudioUrl,
      durationLabel: userDurationSec ? `${userDurationSec} сек` : null,
      badge: userAudioUrl ? "Твоё голосовое" : "Ты",
      time: formatTime(),
    };
    state.messages.push(userMsg);
    renderMessages();

    const history = state.messages
      .filter((m) => m.id !== "welcome-1")
      .map((m) => ({ role: m.role, content: m.text }));

    try {
      const resp = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: history,
          persona_id: state.settings.personaId,
          custom_prompt: state.settings.customPrompt || null,
          llm_config: {
            api_key: state.settings.apiKey || null,
            base_url: state.settings.baseUrl || null,
            model: state.settings.model || null,
          },
        }),
      });
      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(data.detail || "Ошибка ответа сервера");
      }

      const assistantMsg = {
        id: `a-${Date.now()}`,
        role: "assistant",
        text: data.reply,
        speechText: data.speech_text || data.reply,
        audioUrl: data.preset_audio_url || null,
        presetAudioUrl: data.preset_audio_url || null,
        badge: data.mode === "llm" ? `ИИ · ${data.model}` : "Голос Arena · Демо",
        time: formatTime(),
      };
      state.messages.push(assistantMsg);
      renderMessages();

      if (state.settings.autoplay) {
        await playAssistantMessage(assistantMsg);
      }
    } catch (err) {
      showBanner(err.message || "Не удалось получить ответ.");
    } finally {
      state.isSending = false;
      els.sendBtn.disabled = false;
    }
  }

  function formatTimer(ms) {
    const sec = Math.floor(ms / 1000);
    const m = String(Math.floor(sec / 60)).padStart(2, "0");
    const s = String(sec % 60).padStart(2, "0");
    return `${m}:${s}`;
  }

  async function stopRecording(shouldSend = true) {
    if (!state.isRecording) return;
    state.isRecording = false;
    els.micBtn.classList.remove("recording");
    els.recordingBar.hidden = true;
    clearInterval(state.recTimerHandle);

    const elapsedSec = Math.max(1, Math.round((Date.now() - state.recStartMs) / 1000));
    const recognizedText = state.interimTranscript.trim();

    if (state.recognition) {
      try {
        state.recognition.onresult = null;
        state.recognition.onerror = null;
        state.recognition.stop();
      } catch {
        // Ignore
      }
      state.recognition = null;
    }

    let recordedBlob = null;
    if (state.mediaRecorder && state.mediaRecorder.state !== "inactive") {
      recordedBlob = await new Promise((resolve) => {
        state.mediaRecorder.onstop = () => {
          resolve(new Blob(state.recordedChunks, { type: state.mediaRecorder.mimeType || "audio/webm" }));
        };
        state.mediaRecorder.stop();
      });
    }
    if (state.mediaStream) {
      state.mediaStream.getTracks().forEach((t) => t.stop());
      state.mediaStream = null;
    }

    if (!shouldSend) return;

    const audioUrl = recordedBlob && recordedBlob.size > 0 ? URL.createObjectURL(recordedBlob) : null;
    if (recognizedText) {
      await sendUserMessage(recognizedText, audioUrl, elapsedSec);
      return;
    }

    if (recordedBlob && recordedBlob.size > 0) {
      try {
        const fd = new FormData();
        fd.append("file", recordedBlob, "voice.webm");
        fd.append("api_key", state.settings.apiKey || "");
        fd.append("base_url", state.settings.baseUrl || "");
        fd.append("language", "ru");
        const resp = await fetch("/api/stt", { method: "POST", body: fd });
        const data = await resp.json();
        if (!resp.ok) {
          throw new Error(data.detail || "Не удалось распознать аудио");
        }
        await sendUserMessage(data.text, audioUrl, elapsedSec);
      } catch (err) {
        showBanner(err.message);
      }
    } else {
      showBanner("Речь не распознана. Попробуй сказать чуть громче или используй ввод текста / Win+H.");
    }
  }

  function micBlockedMessage() {
    if (window.self !== window.top) {
      return (
        "Браузер заблокировал микрофон внутри встроенного предпросмотра. " +
        "Открой предпросмотр в новой вкладке Chrome/Edge (кнопка со стрелкой в рамке предпросмотра) " +
        "и разреши микрофон, либо кликни в поле ввода ниже и надиктуй через Win + H."
      );
    }
    return (
      "Доступ к микрофону запрещён. Нажми на значок настроек/замка слева от адресной строки браузера, " +
      "разреши «Микрофон» и обнови страницу — или используй диктовку Win + H в текстовом поле."
    );
  }

  async function startRecording() {
    stopPlayback();
    hideBanner();
    state.interimTranscript = "";
    state.recordedChunks = [];
    els.recLiveText.textContent = "Слушаю русскую речь...";

    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    let micStream = null;

    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
      try {
        micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      } catch (err) {
        if (!SpeechRec) {
          showBanner(micBlockedMessage());
          return;
        }
      }
    }

    if (!micStream && !SpeechRec) {
      showBanner("Браузер не поддерживает запись с микрофона в этом окне. Используй текст, Win+H или загрузку аудиофайла.");
      return;
    }

    state.isRecording = true;
    state.recStartMs = Date.now();
    els.micBtn.classList.add("recording");
    els.recordingBar.hidden = false;
    els.recTimer.textContent = "00:00";
    state.recTimerHandle = setInterval(() => {
      els.recTimer.textContent = formatTimer(Date.now() - state.recStartMs);
    }, 250);

    if (micStream) {
      state.mediaStream = micStream;
      try {
        const recorder = new MediaRecorder(micStream);
        state.mediaRecorder = recorder;
        recorder.ondataavailable = (e) => {
          if (e.data && e.data.size > 0) state.recordedChunks.push(e.data);
        };
        recorder.start(200);
      } catch {
        state.mediaRecorder = null;
      }
    }

    if (SpeechRec) {
      try {
        const rec = new SpeechRec();
        rec.lang = "ru-RU";
        rec.continuous = true;
        rec.interimResults = true;
        let finalText = "";
        rec.onresult = (event) => {
          let interim = "";
          for (let i = event.resultIndex; i < event.results.length; i++) {
            const transcript = event.results[i][0].transcript;
            if (event.results[i].isFinal) {
              finalText += (finalText ? " " : "") + transcript.trim();
            } else {
              interim += transcript;
            }
          }
          state.interimTranscript = `${finalText} ${interim}`.trim();
          els.recLiveText.textContent = state.interimTranscript || "Слушаю русскую речь...";
        };
        rec.onerror = (event) => {
          if (event.error === "not-allowed" || event.error === "service-not-allowed") {
            showBanner(micBlockedMessage());
            stopRecording(false);
          }
        };
        rec.onend = () => {
          if (state.isRecording) {
            stopRecording(Boolean(state.interimTranscript.trim()));
          }
        };
        rec.start();
        state.recognition = rec;
      } catch {
        state.recognition = null;
      }
    }
  }

  async function handleAudioFileUpload(file) {
    if (!file) return;
    hideBanner();
    const audioUrl = URL.createObjectURL(file);
    try {
      const fd = new FormData();
      fd.append("file", file, file.name);
      fd.append("api_key", state.settings.apiKey || "");
      fd.append("base_url", state.settings.baseUrl || "");
      fd.append("language", "ru");
      const resp = await fetch("/api/stt", { method: "POST", body: fd });
      const data = await resp.json();
      if (!resp.ok) {
        throw new Error(data.detail || "Ошибка распознавания файла");
      }
      await sendUserMessage(data.text, audioUrl, null);
    } catch (err) {
      URL.revokeObjectURL(audioUrl);
      showBanner(err.message);
    } finally {
      els.audioUploadInput.value = "";
    }
  }

  function bindEvents() {
    els.composerForm.addEventListener("submit", (e) => {
      e.preventDefault();
      sendUserMessage(els.textInput.value);
    });

    els.textInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendUserMessage(els.textInput.value);
      }
    });

    els.textInput.addEventListener("input", () => {
      els.textInput.style.height = "auto";
      els.textInput.style.height = `${Math.min(130, els.textInput.scrollHeight)}px`;
    });

    els.micBtn.addEventListener("click", () => {
      if (state.isRecording) stopRecording(true);
      else startRecording();
    });

    els.cancelRecordBtn.addEventListener("click", () => stopRecording(false));
    els.attachAudioBtn.addEventListener("click", () => els.audioUploadInput.click());
    els.audioUploadInput.addEventListener("change", (e) => handleAudioFileUpload(e.target.files[0]));

    els.quickChips.querySelectorAll(".chip").forEach((chip) => {
      chip.addEventListener("click", () => sendUserMessage(chip.dataset.text));
    });

    els.ttsEngineToggle.addEventListener("click", () => {
      const order = ["arena", "edge", "browser"];
      const idx = order.indexOf(state.settings.ttsMode);
      state.settings.ttsMode = order[(idx + 1) % order.length];
      saveSettings();
      syncHeaderUi();
    });

    els.autoplayBtn.addEventListener("click", () => {
      state.settings.autoplay = !state.settings.autoplay;
      saveSettings();
      syncHeaderUi();
    });

    els.clearChatBtn.addEventListener("click", () => {
      stopPlayback();
      addGreeting();
    });

    els.settingsBtn.addEventListener("click", () => {
      renderSettingsModal();
      els.settingsModal.hidden = false;
    });

    els.closeSettingsBtn.addEventListener("click", () => {
      els.settingsModal.hidden = true;
    });

    els.settingsModal.addEventListener("click", (e) => {
      if (e.target === els.settingsModal) els.settingsModal.hidden = true;
    });

    els.ttsModeSegmented.querySelectorAll("button").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.settings.ttsMode = btn.dataset.mode;
        renderSettingsModal();
      });
    });

    els.rateSlider.addEventListener("input", () => {
      state.settings.rate = parseFloat(els.rateSlider.value);
      els.rateValueLabel.textContent = `${state.settings.rate.toFixed(2).replace(/\.00$/, ".0")}x`;
    });

    els.browserVoiceSelect.addEventListener("change", () => {
      state.settings.browserVoiceURI = els.browserVoiceSelect.value;
    });

    els.serverVoiceSelect.addEventListener("change", () => {
      state.settings.serverVoice = els.serverVoiceSelect.value;
    });

    document.querySelectorAll(".preset-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const preset = PRESET_CONFIGS[btn.dataset.preset];
        if (!preset) return;
        els.baseUrlInput.value = preset.baseUrl;
        els.modelInput.value = preset.model;
        if (preset.apiKey !== undefined) {
          els.apiKeyInput.value = preset.apiKey;
        }
      });
    });

    els.testVoiceBtn.addEventListener("click", () => {
      const sample = "Привет! Проверка связи: так звучит твой голосовой собеседник на русском языке.";
      if (state.settings.ttsMode === "arena") {
        playAudioBlobUrl("/static/clips/welcome.mp3", "test-preview");
      } else if (state.settings.ttsMode === "edge") {
        playAssistantMessage({ id: "test-preview", text: sample, speechText: sample });
      } else {
        speakWithBrowser(sample, null);
      }
    });

    els.saveSettingsBtn.addEventListener("click", () => {
      state.settings.customPrompt = els.customPromptInput.value.trim();
      state.settings.baseUrl = els.baseUrlInput.value.trim();
      state.settings.model = els.modelInput.value.trim();
      state.settings.apiKey = els.apiKeyInput.value.trim();
      saveSettings();
      syncHeaderUi();
      els.settingsModal.hidden = true;
    });

    els.statusBannerClose.addEventListener("click", hideBanner);
  }

  async function init() {
    loadSettings();
    bindEvents();
    addGreeting();

    if ("speechSynthesis" in window) {
      loadBrowserVoices();
      window.speechSynthesis.onvoiceschanged = loadBrowserVoices;
    }

    try {
      const resp = await fetch("/api/health");
      if (resp.ok) {
        const info = await resp.json();
        state.personas = info.personas || [];
        state.serverVoices = info.voices || [];
        state.hasEnvLlm = Boolean(info.has_env_llm);
      }
    } catch {
      showBanner("Не удалось загрузить конфигурацию сервера /api/health.");
    }
    syncHeaderUi();
  }

  init();
})();
