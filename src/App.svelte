<script lang="ts">
    import { onMount } from "svelte";
    import type { Message } from "./lib/types";
    import tariqPfp from "./assets/tariqgpt-logo.svg";
    let input = "";
    let disabled = false;
    let messages: Message[] = [];
    
    let temperature = 0.8;
    let maxTokens = 150;
    let volume = 50;

    let model = "Tariq0.6";
    let models: string[] = [];
    let status = "Current Model: "+model;
    const confidenceColor = ["#ff4d4d", "#ff944d", "#ffe44d", "#b3ff66", "#66ff66"];
    //                          0 -Terrible, 1 - Bad, 2 - Okay, 3 - Good, 4 - Great
    const synth = window.speechSynthesis;
    const utterance = new SpeechSynthesisUtterance(
        "Type what you want in the prompt box!",
    );
    synth.speak(utterance);

    async function loadModels() {
        try {
            const res = await fetch("http://localhost:8000/models);
            const data = await res.json();
            models = data.models;
        } catch (err) {
            console.error("Failed to load models:", err);
        }
    }

    async function speak(text: string) {
        if (!synth) return;
        synth.cancel();
        let pitch = Math.random() * 100;
        const utter = new SpeechSynthesisUtterance(text);
        utter.volume = volume / 100;
        utter.pitch = pitch;
        synth.speak(utter);
    }

    async function cleanParams() {
        if (isNaN(temperature)) temperature = 1.0;
        if (isNaN(maxTokens)) maxTokens = 150;
        if (temperature < 0) temperature = 0;
        else if (temperature > 2) temperature = 1;
        if (maxTokens < 0) maxTokens = 0;
        else if (maxTokens > 1000) maxTokens = 150;
    }

    async function handleSend() {
        let container = document.querySelector(".chat");

        if (!input.trim()) return;
        await cleanParams();
        messages = [...messages, { role: "user", content: input }];
        input = "";
        disabled = true;
        
        status = "TariqGPT is typing...";
        if (container) container.scrollTop = container.scrollHeight;  
	try {
            const res = await fetch("http://localhost:8000/generate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    prompt: messages
                        .map((m) => `${m.role}: ${m.content}`)
                        .join("\n"),
                    max_tokens: maxTokens,
                    temperature,
                    model_name: model,
                }),
            });
            const data = await res.json();
            const reply = data.response;
            const confidence = data.confidence;
            const confidence_score = Math.min(Math.floor((data.confidence ?? 0) * 5), 4);
            messages = [...messages, { role: "TariqGPT", content: reply, confidence_score }];
            await speak(reply);
        } catch (err) {
            messages = [
                ...messages,
                { role: "TariqGPT", content: "Error reaching the model." },
            ];
        }
        if (container) container.scrollTop = container.scrollHeight;
        status = "Waiting for prompt";
        disabled = false;

    }

    async function regenerate(index: number) {
        disabled = true;
        let container = document.querySelector(".chat");
        const userMsg = messages
            .slice(0, index)
            .findLast((m) => m.role === "user");
        if (!userMsg) return;
        await cleanParams();
        messages = messages.filter((_, j) => j !== index);
        status = "TariqGPT is regenerating...";
        try {
            const res = await fetch("http://localhost:8000/generate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    prompt: messages
                        .map((m) => `${m.role}: ${m.content}`)
                        .join("\n"),
                    max_tokens: maxTokens,
                    temperature,
                    model_name: model,
                }),
            });
            const data = await res.json();
            const reply = data.response;
            const confidence = data.confidence;
            const confidence_score = Math.min(Math.floor((data.confidence ?? 0) * 5), 4);
            messages = [...messages, { role: "TariqGPT", content: reply, confidence_score }];
            await speak(reply);
        } catch (err) {
            messages = [
                ...messages,
                { role: "TariqGPT", content: "Error reaching the model." },
            ];
        }
        if (container) container.scrollTop = container.scrollHeight;
        status = "Waiting for prompt";
        disabled = false;
    }

    function loadSavedChat() {

        const fileInput = document.createElement("input");
        fileInput.type = "file";
        fileInput.accept = ".json";
        fileInput.onchange = async (e) => {
            const file = (e.target as HTMLInputElement).files?.[0];
            if (!file) return;
            const text = await file.text();
            try {
                const loadedMessages: Message[] = JSON.parse(text);
                messages = loadedMessages;
            } catch (err) {
                alert("Failed to load chat: Invalid file format");
            }
        };
        fileInput.click();
    }

    function saveChat() {
        const blob = new Blob([JSON.stringify(messages, null, 2)], {
            type: "application/json",
        });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "chat.json";
        a.click();
    }

    onMount(async () => {
        await loadModels();

        const slider = document.getElementById(
            "vol-slider",
        ) as HTMLInputElement;
        const volNum = document.getElementById("vol-num")!;
        const volStatus = document.getElementById("vol-status")!;
        const volIcon = document.getElementById("vol-icon")!;
        const confirmBtn = document.getElementById(
            "vol-confirm",
        ) as HTMLButtonElement;

        let pending = 50,
            moves = 0;
        let inverted = false,
            slowMode = false,
            lastMove = 0;

        function icons(v: number) {
            return v === 0 ? "🔇" : v < 30 ? "🔈" : v < 70 ? "🔉" : "🔊";
        }

        slider.addEventListener("input", () => {
            const now = Date.now();
            if (slowMode && now - lastMove < 300) {
                slider.value = String(pending);
                volStatus.textContent = "too fast. slow down.";
                return;
            }
            lastMove = now;
            let v = parseInt(slider.value);
            if (inverted) v = 100 - v;
            pending = v;
            volIcon.textContent = icons(v);
            moves++;

            if (moves === 1) {
                volStatus.textContent = "now confirm it";
                confirmBtn.style.display = "inline-block";
            } else if (moves === 4) {
                slowMode = true;
                volStatus.textContent = "slow mode on";
                confirmBtn.style.display = "inline-block";
            } else if (moves === 6) {
                inverted = !inverted;
                volStatus.textContent = inverted
                    ? "inverted lol"
                    : "un-inverted";
                confirmBtn.style.display = "inline-block";
            } else {
                volStatus.textContent = "confirm again";
                confirmBtn.style.display = "inline-block";
            }
        });

        let confirmPhase = 0;
        confirmBtn.addEventListener("click", () => {
            if (confirmPhase === 0 && moves % 4 === 0) {
                confirmBtn.textContent = "sure?";
                confirmPhase = 1;
                return;
            }
            confirmPhase = 0;
            confirmBtn.textContent = "apply";
            volume = pending;
            volNum.textContent = String(volume);
            volStatus.textContent = "applied. happy?";
            confirmBtn.style.display = "none";
        });
    });
</script>

<div class="container">
    <div class="sidebar">
        <h3>Models</h3>
	<div class="info">
		<p>Any response from Tariq is ai generated and should be taken with a grain of salt</p>
		<p>Always double check your information</p>
        
	</div>
	    {#each models as m}
            <button
                class="model-btn"
                on:click={() => {
                    model = m;
                    status = `Switched to model: ${m}`;
                }}
            >
                {m}
            </button>
        {/each}
    </div>

    <div class="chat-container">
        <div class="chat">
            {#each messages as msg, i}
                <div class="bubble-row {msg.role}">
                    <div class="bubble-wrap">
                        {#if msg.role === "TariqGPT"}
                            <img src={tariqPfp} height=34 width=34 class="assistant-logo" alt="TariqGPT Logo"/>
                            
                        {/if}
                        
                        <div class="bubble">{msg.content}</div>
                        
                        <div class="actions">
                            {#if msg.role === "TariqGPT" && msg.confidence_score !== undefined}
                                <span class="action-txt {msg.role}" style="color: {confidenceColor[msg.confidence_score]}">
                                    Confidence: {["Super Confused", "Bad", "Mid", "Good", "Amazing little boy"][msg.confidence_score]}
                                </span>
                                
                            {/if}
                                
                            <button
                                class="action-btn {msg.role}"
                                on:click={() =>
                                    navigator.clipboard.writeText(msg.content)}
                                >Copy</button
                            >
                            <button
                                class="action-btn {msg.role}"
                                on:click={() =>
                                    (messages = messages.filter(
                                        (_, j) => j !== i,
                                    ))}>Delete</button
                            >
                            {#if msg.role === "TariqGPT"}
                            
                                <button
                                    class="action-btn {msg.role}"
                                    on:click={() => regenerate(i)} {disabled}>Retry</button
                                >
                                <button
                                    class="action-btn {msg.role}"
                                    on:click={() => speak(msg.content)}
                                    >Speak</button
                                >
                                
                            {/if}
                        </div>
                    </div>
                </div>
            {/each}
        </div>

        <p class="status">{status} &nbsp;  &nbsp; &nbsp; support us <a href="https://cash.app/$orange3717">here!</a></p>

        <div class="volume-control" id="vol-app">
            <span id="vol-icon">🔉</span>
            <div id="vol-slider-wrapper">
                <input
                    type="range"
                    id="vol-slider"
                    min="0"
                    max="100"
                    value="50"
                    step="1"
                />
            </div>
            <span id="vol-num">50</span>
            <span id="vol-status">try to change me</span>
            <button id="vol-confirm" class="settings-btn">apply</button>
        </div>

        <div class="bot-settings">
            <input
                class="settings-input"
                type="number"
                placeholder="Temperature (0-2)"
                min="0"
                max="2"
                step="0.1"
                bind:value={temperature}
            />
            <input
                class="settings-input"
                type="number"
                placeholder="Max tokens (0-1000)"
                min="0"
                max="300"
                step="10"
                bind:value={maxTokens}
            />
            <button class="action-btn settings-btn" on:click={loadSavedChat}
                >Load Chat</button
            >
        </div>

        <div class="input">
            <input
                bind:value={input}
                {disabled}
                placeholder="Type message to TariqGPT here..."
                on:keydown={(e) => e.key === "Enter" && !disabled && handleSend()}
            />
            <button on:click={handleSend} {disabled}>Send</button>
            <button on:click={() => (messages = [])}>Clear</button>
            <button on:click={saveChat}>Save</button>
        </div>
    </div>
</div>

<style>
    :global(html, body) {
    margin: 0;
    padding: 0;
    overflow-y: hidden;
}

* {
    font-family: "Comic Sans MS", sans-serif;
}

/* ── Color tokens ── */
:root {
    --bg: #ffffff;
    --bg-sidebar: #ffffff;
    --bg-chat: #ffffff;
    --bg-input-area: #ffffff;
    --bg-volume: #ffffff;
    --bg-bot-settings: #ffffff;
    --border: #2c2c2e;
    --text: #000000;
    --text-muted: #636366;
    --input-bg: rgb(223, 223, 223);
    --input-border: #3a3a3c;
    --input-placeholder: #636366;
    --btn-disabled-bg: #3a3a3c;
    --model-btn-bg: #ffffff;
    --model-btn-text: #000;
    --model-btn-border: #3a3a3c;
    --status-color: green;
    --accent: #0b84fe;
    --purple: #5134B7;
    --purple-anim: #a73ad9;
}

@media (prefers-color-scheme: dark) {
    :root {
        --bg: #1c1c1e;
        --bg-sidebar: #1c1c1e;
        --bg-chat: #1c1c1e;
        --bg-input-area: #1c1c1e;
        --bg-volume: #1c1c1e;
        --bg-bot-settings: #1c1c1e;
        --border: #48484a;
        --text: #ffffff;
        --text-muted: #aeaeb2;
        --input-bg: #2c2c2e;
        --input-border: #636366;
        --input-placeholder: #8e8e93;
        --btn-disabled-bg: #48484a;
        --model-btn-bg: #2c2c2e;
        --model-btn-text: #ffffff;
        --model-btn-border: #636366;
        --status-color: #30d158;
        --accent: #0a84ff;
        --purple: #5134B7;
        --purple-anim: #da8fff;
    }
}

.container {
    display: flex;
    height: 100vh;
    background: var(--bg);
}

.sidebar {
    width: 150px;
    padding: 20px;
    background: var(--bg-sidebar);
    border-right: 1px solid var(--border);
    color: var(--model-btn-text);
    overflow-y: auto;
}

.chat-container {
    flex: 1;
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
}

.settings-input {
    width: 180px;
    flex: unset;
    padding: 4px 10px;
    font-size: 12px;
    border-radius: 12px;
}

.settings-btn {
    font-size: 11px;
    padding: 4px 10px;
    height: auto;
    width: auto;
    border-radius: 12px;
    background: var(--accent);
    color: #fff;
}

.bot-settings {
    display: flex;
    gap: 8px;
    padding: 0 12px 8px;
    background: var(--bg-bot-settings);
}

.chat {
    height: 60vh;
    overflow-y: auto;
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 6px;
    background: var(--bg-chat);
}

.status {
    margin: 8px 12px;
    font-size: 14px;
    color: var(--status-color);
    font-weight: bold;
}

.bubble-row {
    display: flex;
    width: 100%;
}

.bubble-row.user {
    justify-content: flex-end;
    
}

.bubble-row.TariqGPT {
    justify-content: flex-start;
    
}

.bubble {
    max-width: 65%;
    padding: 10px 14px;
    border-radius: 18px;
    font-size: 15px;
    line-height: 1.4;
    word-break: break-word;
}

.user .bubble {
    background: var(--accent);
    color: #fff;
    border-bottom-right-radius: 4px;
    max-width:45%;
    margin-left: auto;
}

.TariqGPT .bubble {
    background: var(--purple);
    color: #fff;
    border-bottom-left-radius: 4px;
    max-width:45%;
}

.volume-control {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 4px 12px 6px;
    background: var(--bg-volume);
    position: relative;
}

#vol-slider-wrapper {
    position: relative;
    width: 120px;
    height: 24px;
    flex-shrink: 0;
}

#vol-slider {
    position: absolute;
    width: 120px;
    top: 4px;
    left: 0;
    accent-color: var(--accent);
    cursor: pointer;
}

#vol-num {
    font-size: 12px;
    font-family: monospace;
    color: var(--text);
    min-width: 26px;
    font-weight: 500;
}

#vol-status {
    font-size: 11px;
    color: var(--text-muted);
    font-style: italic;
    flex: 1;
}

#vol-confirm {
    display: none;
}

.input {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    background: var(--bg-input-area);
    border-top: 1px solid var(--border);
    border-radius: 24px;
}

input {
    flex: 1;
    background: var(--input-bg);
    color: var(--text);
    border: 1px solid var(--input-border);
    border-radius: 20px;
    padding: 8px 14px;
    font-size: 15px;
    outline: none;
}

input::placeholder {
    color: var(--input-placeholder);
}

button {
    background: var(--accent);
    color: #fff;
    border: none;
    border-radius: 25px;
    width: 64px;
    height: 24px;
    font-size: 16px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
}

.action-btn {
    background: transparent;
    color: var(--text-muted);
    border: none;
    font-size: 12px;
    height: 12px;
    width: auto;
    padding: 10px;
    cursor: pointer;
    
}

.action-txt {
  background: transparent;
  color: var(--text-muted);
  border: none;
  font-size: 8px;
  height:8px;
  width: auto;
  padding: 5px;
}


.action-btn.TariqGPT {
    background: transparent;
    color: var(--text-muted);
    border: none;
    font-size: 12px;
    height: 12px;
    width: auto;
    padding: 10px;
    cursor: pointer;
    
}

.action-txt.TariqGPT {
    background: transparent;
    color: var(--text-muted);
    border: none;
    font-size: 12px;
    height: 12px;
    width: auto;
    padding: 10px;
}

.action-txt.user {
    background: transparent;
    color: var(--text-muted);
    border: none;
    font-size: 12px;
    height: 12px;
    width: auto;
    padding: 10px;
    margin-left: auto;
}

.action-btn.user {
    background: transparent;
    color: var(--text-muted);
    border: none;
    font-size: 12px;
    height: 12px;
    width: auto;
    padding: 10px;
    cursor: pointer;
    margin-left: auto;
}

.action-btn:hover {
    animation:
        gray-to-purple-color 2s infinite,
        stretch 2s forwards;
}

@keyframes pulse {
    0%   { transform: scale(1); }
    50%  { transform: scale(1.1); }
    100% { transform: scale(1); }
}

@keyframes stretch {
    0%   { transform: scale(1); }
    100% { transform: scale(1.2, 0.8); }
}

button:hover {
    animation: pulse 3s infinite;
}

button:disabled {
    background: var(--btn-disabled-bg);
}

@keyframes white-to-purple {
    0%   { background-color: var(--model-btn-bg); }
    50%  { background-color: var(--purple-anim); }
    100% { background-color: var(--model-btn-bg); }
}

@keyframes gray-to-purple-color {
    0%   { color: var(--text-muted); }
    50%  { color: var(--purple-anim); }
    100% { color: var(--text-muted); }
}

@keyframes grow {
    0%   { transform: scale(1); }
    100% { transform: scale(1.15); }
}

.model-btn {
    display: block;
    width: 100%;
    height: 64px;
    margin-bottom: 8px;
    padding: 8px 12px;
    font-size: 14px;
    background: var(--model-btn-bg);
    color: var(--model-btn-text);
    border: 1px solid var(--model-btn-border);
    border-radius: 12px;
    cursor: pointer;
}

.model-btn:hover {
    animation:
        white-to-purple 2s infinite,
        grow 1.5s forwards;
    cursor: pointer;
}

.info {
    color: red;
    font-size: 8px;
    display: inline;
}

</style>
