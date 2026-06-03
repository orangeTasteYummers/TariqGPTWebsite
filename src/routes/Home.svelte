

<script lang="ts">
    // svolumtuff
    import { onMount } from "svelte";
    import type { Message } from "../lib/types";
    import { API_URL } from "../lib/config";
    import tariqPfp from "../assets/tariqgpt-logo.svg";
    let input = "";
    let disabled = false;
    let messages: Message[] = [];

    
    let temperature = 0.8;
    let maxTokens = 150;
    let volume = 25;

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
            const res = await fetch(`${API_URL}/models`);
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
            const res = await fetch(`${API_URL}/generate`, {
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
            const res = await fetch(`${API_URL}/generate`, {
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
    async function clearChat() {
        if (confirm("This will delete ALL chats on the current page, are you sure?")) {
            messages = [];
        }
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
        const volIcon = document.getElementById("vol-icon")!;

        function icons(v: number) {
            return v === 0 ? "🔇" : v < 30 ? "🔈" : v < 70 ? "🔉" : "🔊";
        }

        slider.addEventListener("input", () => {
            
            let v = parseInt(slider.value);
            
            volIcon.textContent = icons(v);

        });
    });
</script>

<div class="container">
    <div class="sidebar">
        <h3>Models</h3>
    <a href="#/info">Curious about Tariq? click here!</a>
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
            <input type="range" id="vol-slider" min="0" max="100" step="5"
                bind:value={volume}
            />
            <span id="vol-icon">🔉</span>
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
                placeholder="Max tokens (0-300)"
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
            <button on:click={handleSend} {disabled}><i class="ti ti-send"></i></button>
            <button on:click={clearChat}><i class="ti ti-eraser"></i></button>
            <button on:click={saveChat}><i class="ti ti-download"></i></button>
        </div>
    </div>
</div>