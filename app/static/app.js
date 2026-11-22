/* Teach Bot front end. No build step. */
"use strict";

const STAGES = [
  ["Diagnose", "Find out what you already know"],
  ["Map", "Rank skills by exam weight"],
  ["Plan", "Fit them into your time"],
  ["Teach", "Picture, analogy, formula, example"],
  ["Check", "Quiz, mark, adjust"],
];
const SKILLS = { S1: "Inverse-square law", S2: "The magnitude scale", S3: "Magnitude differences", S4: "Distance modulus", S5: "Parallax and units", S6: "Extinction and luminosity" };
const LEVEL = { "not started": 0, "in progress": 1, taught: 2, checked: 3 };
const SUGGEST = [
  ["I've never done physics", "Why does a star look fainter when it's farther away?"],
  ["Test my intuition", "If a star is ten times farther away, is it ten times fainter?"],
  ["Short on time", "I have one hour before a selection test. Where should I start?"],
  ["The backwards scale", "Why does a bigger magnitude mean a dimmer star?"],
];
const EXAMPLES = [
  "A torch shines on a wall 3 metres away. I step back until I'm 9 metres away. How many times dimmer is the patch of light?",
  "A star has m = 12.0 and M = 2.0. How far away is it?",
  "Two stars of magnitude 1 and 2 sit right next to each other. What's their combined magnitude? I tried 3.",
  "Why does a bigger magnitude mean a dimmer star?",
  "A star has a parallax of 0.02 arcseconds and apparent magnitude 8. What is its absolute magnitude?",
  "How does interstellar dust change the distance I'd calculate for a star?",
];

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch {} },
};
const MARK = `<svg class="mark" viewBox="0 0 20 20" aria-hidden="true"><rect width="20" height="20" rx="5"/><path d="M10 4.2l1.3 4.5 4.5 1.3-4.5 1.3L10 15.8l-1.3-4.5L4.2 10l4.5-1.3z"/></svg>`;
const ICON_COPY = `<svg viewBox="0 0 16 16"><rect x="5.5" y="5.5" width="8" height="8" rx="1.5"/><path d="M10.5 5.5V3.5a1 1 0 0 0-1-1h-6a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2"/></svg>`;
const ICON_OK = `<svg viewBox="0 0 16 16"><path d="M3.5 8.5l3 3 6-7"/></svg>`;

const state = { status: null, learner: null, busy: false, view: "lesson" };

/* ------------------------------------------------------------------ */
/* Rendering                                                           */
/* ------------------------------------------------------------------ */
function renderMD(text) {
  const maths = [];
  const keep = (tex, display) => { maths.push([tex, display]); return `@@M${maths.length - 1}@@`; };
  let s = String(text || "")
    .replace(/\$\$([\s\S]+?)\$\$/g, (_, t) => keep(t, true))
    .replace(/\\\[([\s\S]+?)\\\]/g, (_, t) => keep(t, true))
    .replace(/\\\(([\s\S]+?)\\\)/g, (_, t) => keep(t, false))
    .replace(/\$([^\n$]+?)\$/g, (_, t) => keep(t, false));
  let html = window.marked ? window.marked.parse(s, { breaks: true, gfm: true }) : esc(s).replace(/\n/g, "<br>");
  return html.replace(/@@M(\d+)@@/g, (_, i) => {
    const [tex, display] = maths[+i];
    try { return window.katex.renderToString(tex, { displayMode: display, throwOnError: false }); } catch { return `<code>${esc(tex)}</code>`; }
  });
}

function parseReply(raw) {
  let plan = null, body = raw, planOpen = false;
  const open = raw.search(/<thought>/i);
  if (open >= 0) {
    const close = raw.search(/<\/thought>/i);
    if (close >= 0) { plan = raw.slice(open + 9, close).trim(); body = raw.slice(0, open) + raw.slice(close + 10); }
    else { plan = raw.slice(open + 9).trim(); body = raw.slice(0, open); planOpen = true; }
  }
  let stage = null;
  const m = body.match(/^\s*\[Stage:\s*(Diagnose|Map|Plan|Teach|Check)\s*\]\s*/i);
  if (m) { stage = m[1][0].toUpperCase() + m[1].slice(1).toLowerCase(); body = body.slice(m[0].length); }
  body = body.replace(/^\s*\[Stage:[^\]\n]*$/i, "");
  return { stage, plan, planOpen, body: body.trim() };
}

/* Markdown + math + hidden answers + live simulators. */
function renderRich(body, streaming) {
  const blocks = [];
  const hold = (html) => { blocks.push(html); return `\n\n@@B${blocks.length - 1}@@\n\n`; };
  let s = body.replace(/<answers>([\s\S]*?)<\/answers>/gi, (_, a) =>
    hold(`<details class="fold answers"><summary>Worked answers<small>try the questions first</small></summary><div class="fbody md">${renderMD(a.trim())}</div></details>`));
  const cut = s.search(/<answers>/i);
  if (cut >= 0) s = s.slice(0, cut) + hold(`<p class="muted">Writing the worked answers…</p>`);
  s = s.replace(/^\s*\[\[sim:([a-z-]+)\]\]\s*$/gim, (_, name) =>
    SIMS.names.includes(name) ? hold(`<div class="sim" data-sim="${name}"></div>`) : "");
  if (streaming) s = s.replace(/\[\[[^\]]*$/, "");
  let html = renderMD(s);
  html = html.replace(/<p>\s*@@B(\d+)@@\s*<\/p>/g, (_, i) => blocks[+i]).replace(/@@B(\d+)@@/g, (_, i) => blocks[+i]);
  return html;
}

function botHTML(raw, streaming, meta = {}) {
  const p = parseReply(raw);
  const plan = p.plan !== null
    ? `<details class="fold plan"${p.planOpen ? " open" : ""}><summary>Teaching plan</summary><div class="fbody">${esc(p.plan)}<p class="note">Written by the model before it answered. A plan, not its hidden reasoning.</p></div></details>` : "";
  return {
    stage: p.stage,
    text: p.body,
    html: `<div class="head">${MARK}<b>Teach Bot</b>${p.stage ? `<span class="stage">${p.stage}</span>` : ""}${meta.seconds ? `<span>${meta.seconds}s</span>` : ""}
             <div class="tools">${streaming ? "" : `<button class="iconbtn" data-copy aria-label="Copy reply">${ICON_COPY}</button>`}</div></div>
           ${plan}<div class="md">${renderRich(p.body, streaming)}</div>`,
  };
}

/* ------------------------------------------------------------------ */
/* Streaming                                                           */
/* ------------------------------------------------------------------ */
async function streamPost(url, body, onEvent) {
  const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!res.ok || !res.body) throw new Error(`${res.status} ${await res.text()}`);
  const reader = res.body.getReader(), dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const line = buf.slice(0, i).split("\n").find((l) => l.startsWith("data: "));
      buf = buf.slice(i + 2);
      if (line) { try { onEvent(JSON.parse(line.slice(6))); } catch {} }
    }
  }
}

/* ------------------------------------------------------------------ */
/* Lesson                                                              */
/* ------------------------------------------------------------------ */
const thread = () => $("#thread");
const scroller = () => $("#scroller");
const nearBottom = () => { const s = scroller(); return s.scrollHeight - s.scrollTop - s.clientHeight < 160; };
const toBottom = () => { const s = scroller(); s.scrollTop = s.scrollHeight; };

function renderStepper(current) {
  const idx = STAGES.findIndex(([s]) => s === current);
  $("#stepper").innerHTML = STAGES.map(([s, d], i) =>
    `<li class="${i < idx ? "done" : i === idx ? "now" : ""}"${i === idx ? ' aria-current="step"' : ""}><b>${s}</b><small>${d}</small></li>`).join("");
}

function renderMemory(rec) {
  const m = rec.memory;
  renderStepper(m.stage);
  $("#skills").innerHTML = Object.entries(m.skills).map(([k, v]) => {
    const n = LEVEL[v] ?? 0;
    return `<li><span>${esc(SKILLS[k] || k)}</span><span>${esc(v)}</span><span class="seg${n === 3 ? " checked" : ""}" aria-hidden="true">${[1, 2, 3].map((j) => `<i class="${j <= n ? "on" : ""}"></i>`).join("")}</span></li>`;
  }).join("");
  $("#memSummary").textContent = m.summary;
  const right = m.quiz.filter((q) => q.correct).length;
  $("#memExtra").innerHTML =
    (m.misconceptions.length ? `<ul class="memlist">${m.misconceptions.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : "") +
    (m.quiz.length ? `<div class="kv"><span>Quiz answers</span><b>${right} of ${m.quiz.length} right</b></div>` : "") +
    `<p class="next">Next step<b>${esc(m.next_step)}</b></p>`;
  $("#memMeta").textContent = rec.memory_updates ? `updated ${rec.memory_updates}×` : "";
}

function addMsg(cls, html) {
  const el = document.createElement("div");
  el.className = `msg ${cls}`;
  el.innerHTML = html;
  thread().appendChild(el);
  return el;
}

function wireMsg(el, text) {
  SIMS.mount(el);
  const b = el.querySelector("[data-copy]");
  if (b) b.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(text); b.innerHTML = ICON_OK; setTimeout(() => (b.innerHTML = ICON_COPY), 1200); } catch {}
  });
}

function welcome() {
  thread().innerHTML = `<div class="welcome">${MARK}<h2>Learn how bright a star looks, and how far away it is</h2>
    <p>Teach Bot finds out what you already know, plans around your time, teaches each idea with a picture first, then checks that it stuck.</p>
    <div class="suggest">${SUGGEST.map(([t, q]) => `<button type="button" data-q="${esc(q)}"><b>${esc(t)}</b><span>${esc(q)}</span></button>`).join("")}</div></div>`;
  $$(".suggest button").forEach((b) => b.addEventListener("click", () => { $("#input").value = b.dataset.q; send(); }));
}

function renderThread() {
  const h = state.learner.history;
  $("#lessonTitle").textContent = lessonTitle(state.learner);
  if (!h.length) return welcome();
  thread().innerHTML = "";
  for (const m of h) {
    if (m.role === "user") addMsg("user", `<div class="ubox">${esc(m.content)}</div>`);
    else { const r = botHTML(m.content, false); wireMsg(addMsg("bot", r.html), r.text); }
  }
  requestAnimationFrame(toBottom);
}

function lessonTitle(rec) {
  const first = rec.history.find((h) => h.role === "user");
  return first ? first.content.slice(0, 70) + (first.content.length > 70 ? "…" : "") : "New lesson";
}

async function loadRecent() {
  const list = await fetch("/api/learners").then((r) => r.json()).catch(() => []);
  const ul = $("#recent");
  const items = list.filter((x) => x.turns > 0);
  ul.innerHTML = items.length ? items.map((x) =>
    `<li><button type="button" data-id="${x.id}" aria-current="${state.learner && x.id === state.learner.id}"><span>${esc(x.title || "Lesson")}</span><small>${x.turns} ${x.turns === 1 ? "message" : "messages"}</small></button></li>`).join("")
    : `<li class="empty">Your lessons appear here.</li>`;
  $$("#recent button").forEach((b) => b.addEventListener("click", () => { openLearner(b.dataset.id); closeSide(); }));
}

async function openLearner(id) {
  const r = await fetch(`/api/learners/${id}`);
  if (!r.ok) return newLesson();
  state.learner = await r.json();
  store.set("teachbot.learner", id);
  renderThread(); renderMemory(state.learner); showView("lesson"); loadRecent();
}

async function newLesson() {
  if (state.learner && !state.learner.history.length) { showView("lesson"); $("#input").focus(); return; }
  const r = await fetch("/api/learners", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  state.learner = await r.json();
  store.set("teachbot.learner", state.learner.id);
  renderThread(); renderMemory(state.learner); showView("lesson"); loadRecent();
  $("#input").focus();
}

async function pollMemory() {
  const before = state.learner.memory_updates || 0, id = state.learner.id;
  for (const wait of [1500, 2500, 4000, 6000, 10000]) {
    await new Promise((r) => setTimeout(r, wait));
    if (!state.learner || state.learner.id !== id) return;
    const rec = await fetch(`/api/learners/${id}`).then((r) => r.json()).catch(() => null);
    if (rec) { state.learner = rec; renderMemory(rec); if ((rec.memory_updates || 0) > before) return; }
  }
}

async function send() {
  const input = $("#input"), text = input.value.trim();
  if (!text || state.busy) return;
  state.busy = true; $("#sendBtn").disabled = true;
  if ($(".welcome")) thread().innerHTML = "";
  input.value = ""; autosize();
  addMsg("user", `<div class="ubox">${esc(text)}</div>`);
  if (!state.learner.history.length) $("#lessonTitle").textContent = text.slice(0, 70);
  const el = addMsg("bot typing", botHTML("", true).html);
  toBottom();
  let raw = "", frame = 0, err = null, seconds = null;
  const paint = (streaming) => {
    const stick = nearBottom();
    const r = botHTML(raw, streaming, { seconds });
    el.innerHTML = r.html;
    if (r.stage) renderStepper(r.stage);
    if (!streaming) { el.classList.remove("typing"); wireMsg(el, r.text); }
    if (err) el.insertAdjacentHTML("beforeend", `<div class="errbox">${esc(err)}</div>`);
    if (stick) toBottom();
  };
  try {
    await streamPost("/api/chat", { learner_id: state.learner.id, message: text }, (ev) => {
      if (ev.type === "token") { raw += ev.text; if (!frame) frame = requestAnimationFrame(() => { frame = 0; paint(true); }); }
      else if (ev.type === "error") err = ev.message;
      else if (ev.type === "done") seconds = ev.seconds;
    });
  } catch (e) { err = `Couldn't reach the app server: ${e.message}`; }
  cancelAnimationFrame(frame); paint(false);
  state.busy = false; $("#sendBtn").disabled = false; input.focus();
  if (!err) {
    state.learner.history.push({ role: "user", content: text }, { role: "assistant", content: raw });
    loadRecent(); pollMemory();
  }
}

function autosize() { const t = $("#input"); t.style.height = "auto"; t.style.height = Math.min(200, t.scrollHeight) + "px"; }

/* ------------------------------------------------------------------ */
/* Compare                                                             */
/* ------------------------------------------------------------------ */
function setupCompare() {
  const sel = $("#preset");
  sel.innerHTML = `<option value="">Example questions</option>` + EXAMPLES.map((q, i) => `<option value="${i}">${esc(q)}</option>`).join("");
  sel.addEventListener("change", () => { if (sel.value !== "") $("#cmpInput").value = EXAMPLES[+sel.value]; });
  $("#cmpBtn").addEventListener("click", runCompare);
}

async function runOne(i, mode, q) {
  const col = $(`#col${i}`), body = $(".col-body", col), foot = $("footer", col);
  body.innerHTML = `<div class="typing"><div class="md"></div></div>`; foot.innerHTML = "";
  let raw = "", frame = 0, err = null;
  const t0 = performance.now();
  const paint = (streaming) => {
    const p = parseReply(raw);
    body.innerHTML = (p.plan !== null ? `<details class="fold plan"><summary>Teaching plan</summary><div class="fbody">${esc(p.plan)}</div></details>` : "") +
      `<div class="${streaming ? "typing" : ""}"><div class="md">${renderRich(p.body, streaming)}</div></div>` + (err ? `<div class="errbox">${esc(err)}</div>` : "");
    if (!streaming) SIMS.mount(body);
  };
  try {
    await streamPost("/api/oneshot", { mode, message: q }, (ev) => {
      if (ev.type === "token") { raw += ev.text; if (!frame) frame = requestAnimationFrame(() => { frame = 0; paint(true); }); }
      if (ev.type === "error") err = ev.message;
    });
  } catch (e) { err = e.message; }
  cancelAnimationFrame(frame); paint(false);
  const p = parseReply(raw), words = p.body.split(/\s+/).filter(Boolean).length;
  const plain = p.body.replace(/<answers>[\s\S]*?<\/answers>/gi, "").replace(/\[\[sim:[^\]]+\]\]/g, "").trim();
  const asks = /\?\s*(\*\*)?\s*$/.test(plain.split("\n").filter(Boolean).slice(-3).join(" ")) || /\?[^?]{0,80}$/.test(plain);
  if (!err) foot.innerHTML = `<span><b>${words}</b> words</span><span><b>${((performance.now() - t0) / 1000).toFixed(1)}</b> s</span>
    <span>${p.plan !== null ? "Teaching plan" : "No plan"}</span><span>${asks ? "Ends with a question" : "No check-in question"}</span>
    ${/\[\[sim:/.test(p.body) ? "<span>Used a simulator</span>" : ""}`;
}

async function runCompare() {
  const q = $("#cmpInput").value.trim();
  if (!q) { $("#cmpInput").focus(); return; }
  $("#cmpBtn").disabled = true;
  await Promise.all([runOne(0, "tutor", q), runOne(1, "plain", q)]);
  $("#cmpBtn").disabled = false;
}

/* ------------------------------------------------------------------ */
/* How it works                                                        */
/* ------------------------------------------------------------------ */
function bars(groups, max, keys) {
  // grouped horizontal bars in HTML, so labels stay readable at any width
  return `<div class="hbars">${groups.map(([label, vals]) => `<div class="grp"><span>${esc(label)}</span>${vals.map((v, j) =>
    `<div class="row"><i style="width:${Math.max(0.5, (78 * v) / max)}%;background:${keys[j][1]}" title="${esc(keys[j][0])}"></i>${v}</div>`).join("")}</div>`).join("")}</div>`;
}

function renderHow() {
  const st = state.status.study, t = st.groups.teachbot, n = st.groups.no_ai, p = st.groups.pilot;
  const model = state.status.model;
  const keys = [["Teach Bot", "var(--accent)"], ["No AI", "var(--text-3)"]];
  $("#how").innerHTML = `<div class="inner">
    <h2 class="h-xl">How Teach Bot works</h2>
    <p class="intro">An AI tutor for one small piece of olympiad astronomy: how bright a star looks and how far away it is. It teaches in five stages, starts every idea from a picture, and checks understanding before moving on.</p>
    <div class="note"><b>About this demo.</b> It is an example of what our tutor does. It runs the Teach Bot method as a prompt on ${esc(model.label)}${model.test ? " (test mode, no model connected)" : ""}, with the topic notes and past problems pinned into every turn. The fine-tuned student model from the project is not part of this demo.</div>

    <section class="part">
      <h3>The method we built</h3>
      <p>A large teacher model wrote physics-checked lessons, and a small student model learned to teach from them, so it could run without calling the expensive teacher for every lesson.</p>
      <div class="flow">
        <div><em>Teacher</em><b>Kimi K3</b><span>Picked for teaching: picture first, everyday analogies, check-in questions</span></div>
        <div><em>Generate</em><b>Feynman lessons</b><span>A teaching plan in thought tags, then the explanation a learner reads</span></div>
        <div><em>Filter</em><b>Physics checks</b><span>Duplicates out; numbers and geometry checked; contradictions and invented methods rejected</span></div>
        <div><em>Student</em><b>Qwen2.5-14B</b><span>Fine-tuned with QLoRA on the plans and the explanations</span></div>
        <div><em>Test</em><b>Real learners</b><span>Five-question tests before, straight after, and later</span></div>
      </div>
    </section>

    <section class="part">
      <h3>How a lesson runs</h3>
      <p>Every session moves through the same five stages. The progress panel in the Lesson view shows where you are, and the memory panel shows what Teach Bot has noted about you.</p>
      <table class="spec"><tbody>${STAGES.map(([s, d]) => `<tr><td>${s}</td><td>${d}</td></tr>`).join("")}</tbody></table>
    </section>

    <section class="part sims-demo">
      <h3>The two simulators</h3>
      <p>The tutor drops these into a lesson when they help. They're computed from the same formulas the project used to check its data.</p>
      <div class="sim" data-sim="inverse-square"></div>
      <div class="sim" data-sim="distance-modulus"></div>
    </section>

    <section class="part">
      <h3>Training settings in the original project</h3>
      <p>As reported by the team. Not used by this demo.</p>
      <table class="spec"><tbody>
        <tr><td>Teacher</td><td>Kimi K3</td></tr>
        <tr><td>Student base</td><td>Qwen2.5-14B-Instruct</td></tr>
        <tr><td>Method</td><td>Sequence-level distillation by supervised fine-tuning on tagged plans and final explanations</td></tr>
        <tr><td>Loading</td><td>QLoRA, 4-bit NF4 with double quantization, bf16 compute, two 24 GB GPUs</td></tr>
        <tr><td>Adapter</td><td>Rank 64, alpha 128, on q, k, v, o, gate, up and down projections</td></tr>
        <tr><td>Schedule</td><td>Cosine, peak 2e-4, warm-up ratio 0.05, effective batch 32, 3 epochs</td></tr>
        <tr><td>Data format</td><td>ShareGPT-style JSONL after deduplication and physics checks</td></tr>
      </tbody></table>
    </section>

    <section class="part">
      <h3>The study</h3>
      <p>${t.n} participants learned with Teach Bot and ${n.n} studied without AI. Everyone took a five-question test before, straight after, and a recall test later. Group averages, out of 5.</p>
      <dl class="figs">
        <div><dt>Teach Bot, straight after</dt><dd>${t.post.toFixed(2)}<small>/ 5</small></dd></div>
        <div><dt>No AI, straight after</dt><dd>${n.post.toFixed(2)}<small>/ 5</small></dd></div>
        <div><dt>Teach Bot, recall</dt><dd>${t.recall.toFixed(2)}<small>/ 5</small></dd></div>
        <div><dt>No AI, recall</dt><dd>${n.recall.toFixed(2)}<small>/ 5</small></dd></div>
      </dl>
      <div class="two">
        <div class="chart"><h4>Average score <span class="key"><i style="background:var(--accent)"></i>Teach Bot</span><span class="key"><i style="background:var(--text-3)"></i>No AI</span></h4>
          ${bars([["Before", [t.pre, n.pre]], ["Straight after", [t.post, n.post]], ["Recall", [t.recall, n.recall]]], 5, keys)}</div>
        <div class="chart"><h4>Recorded study time, minutes</h4>
          ${bars([["Mean", [t.study_min_mean, n.study_min_mean]], ["Median", [t.study_min_median, n.study_min_median]]], 300, keys)}
          <p class="muted" style="font-size:12.5px;margin-top:6px">About four times as long without AI, but study time wasn't matched, so it isn't credited to the tutor alone.</p></div>
      </div>
      <div class="note" style="margin:0 0 20px">A pilot of ${p.n} people with ${p.study_min_mean}-minute sessions is kept separate and never averaged in: ${esc(p.note)}.</div>
      <h3 style="font-size:15px">Limits we state out loud</h3>
      <ul class="limits">${st.limits.map((l) => `<li>${esc(l[0].toUpperCase() + l.slice(1))}</li>`).join("")}</ul>
    </section></div>`;
  SIMS.mount($("#how"));
}

/* ------------------------------------------------------------------ */
/* Shell                                                               */
/* ------------------------------------------------------------------ */
function showView(v) {
  state.view = v;
  ["lesson", "compare", "how"].forEach((x) => ($(`#view-${x}`).hidden = x !== v));
  $$(".nav button").forEach((b) => (b.dataset.view === v ? b.setAttribute("aria-current", "page") : b.removeAttribute("aria-current")));
  if (v === "how" && !$("#how").children.length) renderHow();
  store.set("teachbot.view", v);
}
function openSide() { $("#app").classList.add("side-open"); $("#scrim").hidden = false; }
function closeSide() { $("#app").classList.remove("side-open"); $("#scrim").hidden = true; }

function setupInspector() {
  const body = $(".lesson-body"), btn = $("#inspBtn");
  const wide = () => matchMedia("(min-width:1181px)").matches;
  let hidden = store.get("teachbot.insp") === "off";
  const apply = () => {
    if (wide()) { body.classList.toggle("no-insp", hidden); body.classList.remove("show-insp"); btn.setAttribute("aria-pressed", String(!hidden)); }
    else { body.classList.remove("no-insp"); btn.setAttribute("aria-pressed", String(body.classList.contains("show-insp"))); }
  };
  btn.addEventListener("click", () => {
    if (wide()) { hidden = !hidden; store.set("teachbot.insp", hidden ? "off" : "on"); }
    else body.classList.toggle("show-insp");
    apply();
  });
  matchMedia("(min-width:1181px)").addEventListener("change", apply);
  apply();
}

function setupTheme() {
  $("#themeBtn").addEventListener("click", () => {
    const dark = getComputedStyle(document.documentElement).colorScheme.includes("dark");
    const next = dark ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    store.set("teachbot.theme", next);
    SIMS.redrawAll();
    if (state.view === "how") renderHow();
  });
}

function renderStatus() {
  const m = state.status.model, el = $("#status");
  el.className = `status ${m.ready ? "ok" : "bad"}`;
  $("#statusText").textContent = m.test ? "Test mode" : m.ready ? m.label : "No API key";
  el.title = m.problem || (m.test ? "Scripted replies, no model" : `${m.label} (${m.model_id}) via ${m.provider}`);
  $("#testbar").hidden = !m.test;
  if (m.test) $("#fineprint").textContent = "Test mode: fixed replies for checking the interface. No model is connected.";
  else $("#fineprint").textContent = `Example of the Teach Bot method, running on ${m.label} with our tutor prompt. It can make mistakes.`;
}

async function init() {
  state.status = await fetch("/api/status").then((r) => r.json());
  renderStatus(); setupTheme(); setupInspector(); setupCompare();
  $("#composer").addEventListener("submit", (e) => { e.preventDefault(); send(); });
  $("#input").addEventListener("input", autosize);
  $("#input").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); } });
  $("#newLesson").addEventListener("click", () => { newLesson(); closeSide(); });
  $$(".nav button").forEach((b) => b.addEventListener("click", () => { showView(b.dataset.view); closeSide(); }));
  $$("[data-open-side]").forEach((b) => b.addEventListener("click", openSide));
  $("#scrim").addEventListener("click", closeSide);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeSide(); });

  const lid = store.get("teachbot.learner");
  const rec = lid ? await fetch(`/api/learners/${lid}`).then((r) => (r.ok ? r.json() : null)).catch(() => null) : null;
  if (rec) { state.learner = rec; renderThread(); renderMemory(rec); } else await newLesson();
  loadRecent();
  showView(store.get("teachbot.view") || "lesson");
}
init();
