/*
 * Video Nuggets — UI orchestration, narrated player, and NuggetBot chat.
 * Depends on pipeline.js (window.VN) and samples.js (window.VN_SAMPLES).
 */
(function () {
  "use strict";
  const VN = window.VN;
  const $ = (sel) => document.querySelector(sel);

  // ── State ──────────────────────────────────────────────────────────────
  let slides = [];
  let idx = 0;
  let playing = false;
  let rate = 1;
  let captionsOn = true;
  let ragIndex = null;
  let fallbackTimer = null;

  // ── Narration (Web Speech API; maps to Edge TTS in the backend) ─────────
  const synth = window.speechSynthesis || null;
  let preferredVoice = null;

  function loadVoice() {
    if (!synth) return;
    const voices = synth.getVoices();
    if (!voices.length) return;
    const wanted = ["Samantha", "Google US English", "Microsoft Aria", "Microsoft Jenny", "Daniel"];
    preferredVoice =
      voices.find((v) => wanted.some((w) => v.name.includes(w)) && v.lang.startsWith("en")) ||
      voices.find((v) => v.lang.startsWith("en")) ||
      voices[0];
  }
  if (synth) {
    loadVoice();
    synth.addEventListener("voiceschanged", loadVoice);
  }

  function speak(text, onDone) {
    if (synth) synth.cancel();
    if (fallbackTimer) {
      clearTimeout(fallbackTimer);
      fallbackTimer = null;
    }
    if (!synth || !window.SpeechSynthesisUtterance) {
      // No speech engine: estimate read time and auto-advance.
      const ms = Math.max(2500, (text.split(/\s+/).length / 2.5) * 1000);
      fallbackTimer = setTimeout(() => onDone && onDone(), ms / rate);
      return;
    }
    const u = new SpeechSynthesisUtterance(text);
    if (preferredVoice) u.voice = preferredVoice;
    u.rate = rate;
    u.pitch = 1;
    u.onend = () => onDone && onDone();
    u.onerror = () => onDone && onDone();
    synth.speak(u);
  }

  function stopSpeech() {
    if (synth) synth.cancel();
    if (fallbackTimer) {
      clearTimeout(fallbackTimer);
      fallbackTimer = null;
    }
  }

  // ── Slide rendering ─────────────────────────────────────────────────────
  function escapeHtml(s) {
    return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }

  function renderSlide(i) {
    const s = slides[i];
    const stage = $("#stage");
    if (!s) return;
    let inner = "";
    if (s.kind === "intro" || s.kind === "outro") {
      inner = `<div class="slide ${s.kind}">
        <div class="kicker">${s.kind === "intro" ? "Video Nugget" : "The End"}</div>
        <h1>${escapeHtml(s.title)}</h1>
        <div class="accent"></div>
        <p class="sub">${escapeHtml(s.subtitle || "")}</p>
      </div>`;
    } else {
      const bullets = (s.bullets || []).map((b) => `<li>${escapeHtml(b)}</li>`).join("");
      inner = `<div class="slide content">
        <h2>${escapeHtml(s.title)}</h2>
        <div class="content-grid">
          <ul class="bullets">${bullets}</ul>
          <div class="viz-wrap">${s.viz ? s.viz.svg : ""}</div>
        </div>
      </div>`;
    }
    stage.innerHTML = inner;
    stage.classList.remove("animate");
    void stage.offsetWidth;
    stage.classList.add("animate");

    $("#slideCounter").textContent = `${i + 1} / ${slides.length}`;
    $("#progressFill").style.width = `${((i + 1) / slides.length) * 100}%`;
    $("#captionBox").textContent = captionsOn ? s.narration : "";
    $("#captionBox").style.display = captionsOn ? "block" : "none";
    highlightTranscript(i);
  }

  function playFrom(i) {
    idx = Math.max(0, Math.min(slides.length - 1, i));
    renderSlide(idx);
    if (!playing) return;
    speak(slides[idx].narration, () => {
      if (!playing) return;
      if (idx < slides.length - 1) playFrom(idx + 1);
      else setPlaying(false);
    });
  }

  function setPlaying(on) {
    playing = on;
    $("#playBtn").innerHTML = on ? iconPause + " Pause" : iconPlay + " Play";
    if (on) playFrom(idx);
    else stopSpeech();
  }

  // ── Transcript ───────────────────────────────────────────────────────────
  function buildTranscript() {
    const panel = $("#transcriptList");
    panel.innerHTML = slides
      .map(
        (s, i) =>
          `<button class="tr-item" data-i="${i}"><span class="tr-num">${i + 1}</span><span><b>${escapeHtml(
            s.title
          )}</b><br><span class="tr-text">${escapeHtml(s.narration)}</span></span></button>`
      )
      .join("");
    panel.querySelectorAll(".tr-item").forEach((btn) =>
      btn.addEventListener("click", () => {
        const j = parseInt(btn.dataset.i, 10);
        idx = j;
        if (playing) playFrom(j);
        else renderSlide(j);
      })
    );
  }
  function highlightTranscript(i) {
    document.querySelectorAll(".tr-item").forEach((el) => el.classList.toggle("active", +el.dataset.i === i));
  }

  // ── Pipeline run with staged progress ────────────────────────────────────
  const STAGE_DEFS = [
    ["parse", "Parse", "Split the document into clean sections"],
    ["simplify", "Simplify", "Rewrite each section as a friendly analogy"],
    ["visualize", "Visualize", "Pick a chart or diagram per section"],
    ["slides", "Slides", "Lay out a branded slide deck"],
    ["narrate", "Narrate", "Prepare spoken narration per slide"],
    ["index", "Index", "Build the NuggetBot knowledge base"],
  ];

  function renderStages(active, done) {
    $("#stages").innerHTML = STAGE_DEFS.map(([id, label, desc]) => {
      const state = done.has(id) ? "done" : active === id ? "active" : "";
      const mark = done.has(id) ? "✓" : active === id ? "●" : "○";
      return `<div class="stage ${state}"><span class="stage-mark">${mark}</span><div><div class="stage-label">${label}</div><div class="stage-desc">${desc}</div></div></div>`;
    }).join("");
  }

  const wait = (ms) => new Promise((r) => setTimeout(r, ms));

  async function generate() {
    const text = $("#docInput").value.trim();
    if (text.length < 120) {
      setStatus("Please paste a longer document (or pick a sample) — at least a few paragraphs.", true);
      return;
    }
    stopSpeech();
    setPlaying(false);
    $("#generateBtn").disabled = true;
    $("#player").classList.add("hidden");
    $("#chatPanel").classList.add("hidden");
    $("#pipelineCard").classList.remove("hidden");
    const done = new Set();

    const llm = readLLMConfig();

    renderStages("parse", done);
    setStatus("Parsing the document…");
    await wait(450);
    const parsed = VN.parse(text);
    done.add("parse");

    renderStages("simplify", done);
    setStatus(llm ? "Simplifying via your LLM endpoint…" : "Simplifying (deterministic analogies)…");
    await wait(450);
    const simplified = await VN.simplify(parsed, { llm });
    done.add("simplify");

    renderStages("visualize", done);
    setStatus("Generating visuals…");
    await wait(400);
    done.add("visualize");

    renderStages("slides", done);
    setStatus("Building slides…");
    await wait(400);
    slides = VN.buildSlides(simplified);
    done.add("slides");

    renderStages("narrate", done);
    setStatus("Preparing narration…");
    await wait(400);
    done.add("narrate");

    renderStages("index", done);
    setStatus("Indexing for NuggetBot…");
    await wait(350);
    ragIndex = VN.buildIndex(simplified);
    done.add("index");
    renderStages(null, done);

    const tag = simplified.simplifiedBy === "llm" ? "your LLM" : "the deterministic simplifier";
    setStatus(`Ready — ${slides.length} slides, simplified by ${tag}. Press play.`);
    $("#generateBtn").disabled = false;

    idx = 0;
    buildTranscript();
    renderSlide(0);
    $("#player").classList.remove("hidden");
    $("#chatPanel").classList.remove("hidden");
    resetChat(simplified.title);
    $("#player").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function setStatus(msg, isError) {
    const el = $("#genStatus");
    el.textContent = msg;
    el.classList.toggle("error", !!isError);
  }

  function readLLMConfig() {
    if (!$("#llmToggle").checked) return null;
    const endpoint = $("#llmEndpoint").value.trim();
    const apiKey = $("#llmKey").value.trim();
    const model = $("#llmModel").value.trim();
    if (!endpoint || !apiKey) return null;
    return { endpoint, apiKey, model };
  }

  // ── NuggetBot chat ────────────────────────────────────────────────────────
  function resetChat(title) {
    $("#chatLog").innerHTML = "";
    addBot(`Hi! I'm NuggetBot. Ask me anything about "${title}" — I'll answer only from this lesson and show you which slide it came from.`);
    const suggests = ["What is a node?", "Why do teams choose this?", "How does it stay safe when hardware fails?"];
    $("#suggestRow").innerHTML = suggests.map((s) => `<button class="suggest-btn">${escapeHtml(s)}</button>`).join("");
    $("#suggestRow").querySelectorAll(".suggest-btn").forEach((b) =>
      b.addEventListener("click", () => {
        $("#chatInput").value = b.textContent;
        handleAsk();
      })
    );
  }
  function addUser(t) {
    $("#chatLog").insertAdjacentHTML("beforeend", `<div class="msg user">${escapeHtml(t)}</div>`);
    scrollChat();
  }
  function addBot(t, sources) {
    let src = "";
    if (sources && sources.length) {
      src = `<div class="msg-sources">From: ${sources.map((s) => `<span>${escapeHtml(s.title)}</span>`).join("")}</div>`;
    }
    $("#chatLog").insertAdjacentHTML("beforeend", `<div class="msg bot">${escapeHtml(t)}${src}</div>`);
    scrollChat();
  }
  function scrollChat() {
    const log = $("#chatLog");
    log.scrollTop = log.scrollHeight;
  }
  function handleAsk() {
    const q = $("#chatInput").value.trim();
    if (!q || !ragIndex) return;
    addUser(q);
    $("#chatInput").value = "";
    const res = VN.ask(ragIndex, q);
    setTimeout(() => addBot(res.answer, res.sources), 250);
  }

  // ── Icons ─────────────────────────────────────────────────────────────────
  const iconPlay = '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>';
  const iconPause = '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M6 5h4v14H6zM14 5h4v14h-4z"/></svg>';

  // ── Wiring ──────────────────────────────────────────────────────────────
  function init() {
    // Samples
    $("#sampleRow").innerHTML = window.VN_SAMPLES.map(
      (s, i) => `<button class="sample-btn" data-i="${i}"><b>${escapeHtml(s.label)}</b><span>${escapeHtml(s.minutes)}</span></button>`
    ).join("");
    $("#sampleRow").querySelectorAll(".sample-btn").forEach((btn) =>
      btn.addEventListener("click", () => {
        const s = window.VN_SAMPLES[+btn.dataset.i];
        $("#docInput").value = s.text;
        setStatus(`Loaded sample: ${s.label}. Press "Make the nugget".`);
        $("#docInput").scrollIntoView({ behavior: "smooth", block: "center" });
      })
    );

    $("#generateBtn").addEventListener("click", generate);
    $("#playBtn").innerHTML = iconPlay + " Play";
    $("#playBtn").addEventListener("click", () => setPlaying(!playing));
    $("#nextBtn").addEventListener("click", () => {
      idx = Math.min(slides.length - 1, idx + 1);
      if (playing) playFrom(idx);
      else renderSlide(idx);
    });
    $("#prevBtn").addEventListener("click", () => {
      idx = Math.max(0, idx - 1);
      if (playing) playFrom(idx);
      else renderSlide(idx);
    });
    $("#restartBtn").addEventListener("click", () => {
      idx = 0;
      if (playing) playFrom(0);
      else renderSlide(0);
    });
    $("#speedSel").addEventListener("change", (e) => {
      rate = parseFloat(e.target.value);
      if (playing) playFrom(idx); // restart current slide at new rate
    });
    $("#captionToggle").addEventListener("click", () => {
      captionsOn = !captionsOn;
      $("#captionToggle").classList.toggle("on", captionsOn);
      $("#captionBox").style.display = captionsOn ? "block" : "none";
      $("#captionBox").textContent = captionsOn && slides[idx] ? slides[idx].narration : "";
    });
    $("#fullscreenBtn").addEventListener("click", () => {
      const el = $("#stageWrap");
      if (!document.fullscreenElement) el.requestFullscreen?.();
      else document.exitFullscreen?.();
    });

    $("#llmToggle").addEventListener("change", (e) => {
      $("#llmFields").classList.toggle("hidden", !e.target.checked);
    });

    $("#chatForm").addEventListener("submit", (e) => {
      e.preventDefault();
      handleAsk();
    });

    // Stop narration when leaving the page.
    window.addEventListener("beforeunload", stopSpeech);

    // Deep link: ?demo=<index> pre-loads a sample and builds it (no autoplay),
    // so a link can drop someone straight into a finished nugget.
    const demo = new URLSearchParams(location.search).get("demo");
    if (demo !== null) {
      const i = Math.max(0, Math.min(window.VN_SAMPLES.length - 1, parseInt(demo, 10) || 0));
      $("#docInput").value = window.VN_SAMPLES[i].text;
      generate();
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
