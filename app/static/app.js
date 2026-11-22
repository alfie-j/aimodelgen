/* Teach Bot front end. No build step. */
"use strict";

const STAGES = [
  ["Diagnose", "What do you already know?"],
  ["Map", "Rank skills by exam weight"],
  ["Plan", "Fit them into your time"],
  ["Teach", "Picture, analogy, formula, example"],
  ["Check", "Quiz, mark, adjust"],
];
const SKILL_NAMES = { S1: "Inverse square", S2: "Magnitudes", S3: "Mag. ratios", S4: "Dist. modulus", S5: "Parallax", S6: "Extinction" };
const STARTERS = [
  "I've never done physics. Why does a star look fainter when it's farther away?",
  "If a star is ten times farther away, is it ten times fainter?",
  "I have one hour before a selection test. Where do I start?",
  "Why does a bigger magnitude mean a dimmer star?",
];
const ASK_FINAL = "\n\n(At the very end, after your check-in question, write one line: 'Final answer: <number>'.)";

const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch {} },
  del(k) { try { localStorage.removeItem(k); } catch {} },
};

const state = { backends: [], backend: null, learner: null, heldout: [], busy: false, testMode: false };

/* ------------------------------------------------------------------ */
/* Rendering: markdown with math protected from the markdown parser    */
/* ------------------------------------------------------------------ */
function renderMD(text) {
  const maths = [];
  let s = String(text || "");
  const keep = (tex, display) => { maths.push([tex, display]); return `@@M${maths.length - 1}@@`; };
  s = s.replace(/\$\$([\s\S]+?)\$\$/g, (_, t) => keep(t, true))
       .replace(/\\\[([\s\S]+?)\\\]/g, (_, t) => keep(t, true))
       .replace(/\\\(([\s\S]+?)\\\)/g, (_, t) => keep(t, false))
       .replace(/\$([^\n$]+?)\$/g, (_, t) => keep(t, false));
  let html = window.marked ? window.marked.parse(s, { breaks: true, gfm: true }) : esc(s).replace(/\n/g, "<br>");
  html = html.replace(/@@M(\d+)@@/g, (_, i) => {
    const [tex, display] = maths[+i];
    if (window.katex) {
      try { return window.katex.renderToString(tex, { displayMode: display, throwOnError: false }); } catch {}
    }
    return `<code>${esc(tex)}</code>`;
  });
  return html;
}

/* Split a (possibly still streaming) reply into stage, plan and body. */
function parseReply(raw) {
  let plan = null, body = raw;
  const open = raw.search(/<thought>/i);
  if (open >= 0) {
    const close = raw.search(/<\/thought>/i);
    if (close >= 0) {
      plan = raw.slice(open + 9, close).trim();
      body = raw.slice(0, open) + raw.slice(close + 10);
    } else {
      plan = raw.slice(open + 9).trim();
      body = raw.slice(0, open);
    }
  }
  let stage = null;
  const m = body.match(/^\s*\[Stage:\s*(Diagnose|Map|Plan|Teach|Check)\s*\]\s*/i);
  if (m) { stage = m[1][0].toUpperCase() + m[1].slice(1).toLowerCase(); body = body.slice(m[0].length); }
  body = body.replace(/^\s*\[Stage:[^\]]*$/i, ""); // half-streamed stage tag
  return { stage, plan, body: body.trim(), planOpen: open >= 0 && raw.search(/<\/thought>/i) < 0 };
}

function badge(b) {
  if (!b) return "";
  const word = { "fine-tuned": "fine-tuned", base: "base model", teacher: "teacher", test: "test" }[b.kind] || b.kind;
  return `<span class="badge ${esc(b.kind)}" title="${esc(b.detail)}">${esc(word)}</span>`;
}

/* ------------------------------------------------------------------ */
/* SSE over fetch                                                      */
/* ------------------------------------------------------------------ */
async function streamPost(url, body, onEvent) {
  const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!res.ok || !res.body) throw new Error(`${res.status} ${await res.text()}`);
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const chunk = buf.slice(0, i); buf = buf.slice(i + 2);
      const line = chunk.split("\n").find((l) => l.startsWith("data: "));
      if (line) { try { onEvent(JSON.parse(line.slice(6))); } catch {} }
    }
  }
}

/* ------------------------------------------------------------------ */
/* Lesson tab                                                          */
/* ------------------------------------------------------------------ */
function renderStages(current) {
  const idx = STAGES.findIndex(([s]) => s === current);
  $("#stages").innerHTML = STAGES.map(([s, d], i) =>
    `<div class="stage ${i < idx ? "done" : i === idx ? "now" : ""}"><span class="dot"></span><div>${s}<small>${d}</small></div></div>`).join("");
}

function renderMemory(rec) {
  const m = rec.memory;
  $("#memSummary").textContent = m.summary;
  $("#skills").innerHTML = Object.entries(m.skills).map(([k, v]) =>
    `<div class="skill ${v.replace(/\s/g, "")}" title="${esc(v)}"><b>${k}</b>${esc(SKILL_NAMES[k] || "")}</div>`).join("");
  const right = m.quiz.filter((q) => q.correct).length;
  $("#memExtra").innerHTML =
    (m.misconceptions.length ? `<p class="kv">Misconceptions seen<br>${m.misconceptions.map((x) => `<span class="pill">${esc(x)}</span>`).join("")}</p>` : "") +
    (m.quiz.length ? `<p class="kv">Quiz: <b>${right} of ${m.quiz.length}</b> right</p>` : "") +
    `<p class="kv">Next: <b>${esc(m.next_step)}</b></p>`;
  $("#memUpdated").textContent = rec.memory_updates ? `updated ${rec.memory_updates}×` : "";
  renderStages(m.stage);
}

function botMessage(raw, b, streaming) {
  const p = parseReply(raw);
  const planHTML = p.plan !== null
    ? `<details class="plan"${p.planOpen ? " open" : ""}><summary>Teaching plan</summary><div class="pbody">${esc(p.plan)}</div>
       <div class="pnote">Written by the model before it answered. It's a plan, not its hidden reasoning.</div></details>` : "";
  return { stage: p.stage, html:
    `<div class="meta">${p.stage ? `<span class="stagechip">${p.stage}</span>` : ""}<span>${esc(b?.label || "")}</span>${badge(b)}</div>
     <div class="bubble">${planHTML}<div class="md${streaming ? " cursor" : ""}">${renderMD(p.body)}</div></div>` };
}

function addMsg(role, html) {
  const el = document.createElement("div");
  el.className = `msg ${role === "user" ? "user" : "bot"}`;
  el.innerHTML = html;
  $("#msgs").appendChild(el);
  $("#msgs").scrollTop = $("#msgs").scrollHeight;
  return el;
}

function renderWelcome() {
  $("#msgs").innerHTML = `<div class="welcome"><h1>How bright is a star,<br>and how far away?</h1>
    <p>Teach Bot will find out what you know, plan around your time, teach with pictures first, then check you've got it.</p>
    <div class="starters">${STARTERS.map((s) => `<button type="button">${esc(s)}</button>`).join("")}</div></div>`;
  $("#msgs").querySelectorAll(".starters button").forEach((b) => b.addEventListener("click", () => { $("#input").value = b.textContent; send(); }));
}

function renderHistory() {
  const h = state.learner.history;
  if (!h.length) return renderWelcome();
  $("#msgs").innerHTML = "";
  for (const m of h) {
    if (m.role === "user") addMsg("user", `<div class="bubble">${esc(m.content)}</div>`);
    else addMsg("bot", botMessage(m.content, state.backends.find((b) => b.id === m.backend) || { label: m.backend, kind: "" }, false).html);
  }
}

async function loadLearner(id) {
  const r = await fetch(`/api/learners/${id}`);
  if (!r.ok) return null;
  return r.json();
}

async function newLearner(name = "") {
  const r = await fetch("/api/learners", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) });
  state.learner = await r.json();
  store.set("teachbot.learner", state.learner.id);
  $("#learnerName").value = state.learner.name === "Learner" ? "" : state.learner.name;
  renderHistory(); renderMemory(state.learner);
}

async function refreshMemory(times = [2500, 6000, 12000, 25000]) {
  const before = state.learner.memory_updates || 0;
  for (const t of times) {
    await new Promise((r) => setTimeout(r, t - (times[times.indexOf(t) - 1] || 0)));
    const rec = await loadLearner(state.learner.id);
    if (rec) { state.learner = rec; renderMemory(rec); if ((rec.memory_updates || 0) > before) return; }
  }
}

async function send() {
  const text = $("#input").value.trim();
  if (!text || state.busy || !state.backend) return;
  state.busy = true; $("#sendBtn").disabled = true;
  if ($("#msgs .welcome")) $("#msgs").innerHTML = "";
  $("#input").value = ""; autosize();
  addMsg("user", `<div class="bubble">${esc(text)}</div>`);
  const b = state.backends.find((x) => x.id === state.backend);
  const el = addMsg("bot", botMessage("", b, true).html);
  let raw = "", frame = 0;
  const paint = (streaming) => {
    const r = botMessage(raw, b, streaming);
    el.innerHTML = r.html;
    if (r.stage) renderStages(r.stage);
    const box = $("#msgs"); if (box.scrollHeight - box.scrollTop - box.clientHeight < 200) box.scrollTop = box.scrollHeight;
  };
  try {
    await streamPost("/api/chat", { learner_id: state.learner.id, backend: state.backend, message: text }, (ev) => {
      if (ev.type === "token") { raw += ev.text; if (!frame) frame = requestAnimationFrame(() => { frame = 0; paint(true); }); }
      else if (ev.type === "error") { raw += `\n\n*${ev.message}*`; el.insertAdjacentHTML("beforeend", `<p class="err">${esc(ev.message)}</p>`); }
      else if (ev.type === "done") { paint(false); }
    });
    cancelAnimationFrame(frame); paint(false);
    refreshMemory();
  } catch (e) {
    el.insertAdjacentHTML("beforeend", `<p class="err">Couldn't reach the tutor: ${esc(e.message)}</p>`);
  } finally {
    state.busy = false; $("#sendBtn").disabled = false; $("#input").focus();
  }
}

function autosize() { const t = $("#input"); t.style.height = "auto"; t.style.height = Math.min(180, t.scrollHeight) + "px"; }

/* ------------------------------------------------------------------ */
/* Compare tab                                                         */
/* ------------------------------------------------------------------ */
function pair() {
  const base = state.backends.find((b) => b.kind === "base");
  const ft = state.backends.find((b) => b.kind === "fine-tuned");
  if (state.testMode) { const t = state.backends[0]; return [t, t]; }
  return base && ft ? [base, ft] : null;
}

function finalAnswer(text) {
  const hits = [...text.matchAll(/final\s+answer\s*[:=]\s*\**\s*([^\n]+)/gi)];
  if (!hits.length) return null;
  let s = hits[hits.length - 1][1].replace(/[−]/g, "-").replace(/\$/g, "").replace(/\\times|×/g, "x").replace(/≈|\\approx/g, "");
  const frac = s.match(/(\d+(?:\.\d+)?)\s*\/\s*(\d+(?:\.\d+)?)/);
  const num = s.match(/-?\d[\d,]*(?:\.\d+)?(?:\s*(?:[eE]-?\d+|x\s*10\s*\^?\s*\{?-?\d+\}?))?/);
  if (frac && (!num || frac.index <= num.index)) return +frac[1] / +frac[2];
  if (!num) return null;
  const t = num[0].replace(/[,\s]/g, "");
  const sci = t.match(/^(-?[\d.]+)x10\^?\{?(-?\d+)\}?$/);
  return sci ? +sci[1] * 10 ** +sci[2] : parseFloat(t);
}
function correct(kind, exp, got) {
  if (got == null || isNaN(got)) return false;
  if (kind === "mag") return Math.abs(got - exp) <= 0.06;
  if (kind === "ratio" && exp < 1 && got > 1) got = 1 / got;
  return Math.abs(got - exp) <= 0.03 * Math.max(Math.abs(exp), Math.abs(got));
}

function setupCompare() {
  const p = pair();
  const cols = $("#cols");
  if (!p) {
    cols.innerHTML = `<div class="col"><div class="body empty">Side by side needs both a base and a fine-tuned backend. Start the app with
      <code>TEACHBOT_BACKENDS=teachbot-hf,base-hf</code>.</div></div>`;
    $("#cmpBtn").disabled = true; return;
  }
  cols.innerHTML = p.map((b, i) => `<div class="col" id="col${i}"><header><div class="t">${esc(b.label)} ${badge(b)}</div><div class="d">${esc(b.detail)}</div></header>
    <div class="body"><p class="empty">Waiting for a question.</p></div><footer></footer></div>`).join("");
  const sel = $("#preset");
  sel.innerHTML = `<option value="">Pick a held-out question (never in training)…</option>` +
    state.heldout.map((q, i) => `<option value="${i}">${esc(q.skill)} · ${esc(q.question.slice(0, 90))}${q.question.length > 90 ? "…" : ""}</option>`).join("");
  sel.addEventListener("change", () => { const q = state.heldout[+sel.value]; $("#cmpInput").value = q ? q.question : ""; });
  $("#cmpBtn").addEventListener("click", runCompare);
}

async function runCompare() {
  const p = pair(); const q = $("#cmpInput").value.trim();
  if (!p || !q) return;
  const preset = state.heldout[+$("#preset").value];
  const isPreset = preset && preset.question === q;
  const msg = isPreset ? q + ASK_FINAL : q;
  $("#cmpBtn").disabled = true;
  // run one after the other: on a single GPU the two share the same weights
  for (let i = 0; i < 2; i++) {
    const col = $(`#col${i}`), body = $(".body", col), foot = $("footer", col);
    body.innerHTML = `<div class="md cursor"></div>`; foot.innerHTML = "";
  }
  for (let i = 0; i < 2; i++) {
    const col = $(`#col${i}`), body = $(".body", col), foot = $("footer", col);
    let raw = "", frame = 0; const t0 = performance.now();
    const paint = (streaming) => {
      const r = parseReply(raw);
      body.innerHTML = (r.plan !== null ? `<details class="plan"><summary>Teaching plan</summary><div class="pbody">${esc(r.plan)}</div></details>` : "") +
        `<div class="md${streaming ? " cursor" : ""}">${renderMD(r.body)}</div>`;
    };
    try {
      await streamPost("/api/oneshot", { backend: p[i].id, message: msg, temperature: 0 }, (ev) => {
        if (ev.type === "token") { raw += ev.text; if (!frame) frame = requestAnimationFrame(() => { frame = 0; paint(true); }); }
        if (ev.type === "error") body.insertAdjacentHTML("beforeend", `<p class="err">${esc(ev.message)}</p>`);
      });
    } catch (e) { body.insertAdjacentHTML("beforeend", `<p class="err">${esc(e.message)}</p>`); }
    cancelAnimationFrame(frame); paint(false);
    const secs = ((performance.now() - t0) / 1000).toFixed(1);
    const words = parseReply(raw).body.split(/\s+/).filter(Boolean).length;
    let v = "";
    if (isPreset) {
      const got = finalAnswer(raw); const ok = correct(preset.kind, preset.answer, got);
      v = `<span class="verdict ${ok ? "ok" : "no"}">${ok ? "✓ correct" : "✗ " + (got == null ? "no final answer" : "wrong")}</span>
           <span>answer ${got == null ? "—" : +got.toPrecision(4)} · expected ${+preset.answer.toPrecision(4)}</span>`;
    }
    foot.innerHTML = `${v}<span>${words} words · ${secs}s</span><span>${/<thought>/i.test(raw) ? "wrote a plan" : "no plan"}</span>`;
  }
  $("#cmpBtn").disabled = false;
}

/* ------------------------------------------------------------------ */
/* How it was built                                                    */
/* ------------------------------------------------------------------ */
const nf = (x, d = 0) => (x == null ? "—" : Number(x).toLocaleString(undefined, { maximumFractionDigits: d }));
const notYet = (cmd, what) => `<div class="notyet">${what} Run <code>${esc(cmd)}</code></div>`;
const stat = (v, l) => `<div class="stat"><div class="v">${v}</div><div class="l">${esc(l)}</div></div>`;

function lossChart(loss, evalLoss) {
  const W = 760, H = 240, P = { l: 44, r: 14, t: 12, b: 30 };
  const all = [...loss, ...evalLoss];
  const xs = all.map((d) => d.step), ys = all.map((d) => d.loss);
  const x0 = Math.min(...xs), x1 = Math.max(...xs) || 1, y0 = 0, y1 = Math.max(...ys) * 1.08;
  const X = (v) => P.l + ((v - x0) / Math.max(1, x1 - x0)) * (W - P.l - P.r);
  const Y = (v) => H - P.b - ((v - y0) / (y1 - y0)) * (H - P.t - P.b);
  const ticks = 4, grid = [];
  for (let i = 0; i <= ticks; i++) {
    const v = y0 + (i / ticks) * (y1 - y0);
    grid.push(`<line x1="${P.l}" x2="${W - P.r}" y1="${Y(v)}" y2="${Y(v)}" stroke="rgba(236,228,255,.08)"/><text x="${P.l - 8}" y="${Y(v) + 4}" text-anchor="end" font-size="11" fill="#9a95c7">${v.toFixed(2)}</text>`);
  }
  const epochs = [];
  const maxEp = Math.ceil(Math.max(...loss.map((d) => d.epoch || 0)));
  for (let e = 1; e < maxEp; e++) {
    const pt = loss.find((d) => (d.epoch || 0) >= e);
    if (pt) epochs.push(`<line x1="${X(pt.step)}" x2="${X(pt.step)}" y1="${P.t}" y2="${H - P.b}" stroke="rgba(242,179,61,.35)" stroke-dasharray="3 4"/><text x="${X(pt.step) + 4}" y="${P.t + 12}" font-size="11" fill="#f2b33d">epoch ${e + 1}</text>`);
  }
  const line = loss.map((d, i) => `${i ? "L" : "M"}${X(d.step).toFixed(1)},${Y(d.loss).toFixed(1)}`).join("");
  const ev = evalLoss.map((d) => `<circle cx="${X(d.step)}" cy="${Y(d.loss)}" r="4" fill="#86a8ff"><title>step ${d.step}: eval loss ${d.loss.toFixed(3)}</title></circle>`).join("");
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Training loss by step">${grid.join("")}${epochs.join("")}
    <path d="${line}" fill="none" stroke="#f2b33d" stroke-width="2"/>${ev}
    <text x="${(W + P.l) / 2}" y="${H - 6}" text-anchor="middle" font-size="11" fill="#9a95c7">optimizer step</text></svg>
    <div class="legend"><span><i style="background:#f2b33d"></i>training loss</span>${evalLoss.length ? `<span><i style="background:#86a8ff"></i>validation loss</span>` : ""}</div>`;
}

function bars(items, max) {
  return `<div class="bars">${items.map(([l, v, cls]) =>
    `<div class="bar"><span>${esc(l)}</span><div class="track"><div class="fill ${cls || ""}" style="width:${max ? (100 * v) / max : 0}%"></div></div><span class="v">${nf(v, 2)}</span></div>`).join("")}</div>`;
}

function exampleCard(r, kept) {
  const notes = (r.filter?.notes || []).join("; ");
  return `<div class="ex"><div class="why ${kept ? "keep" : ""}">${kept ? "KEPT" : "REJECTED at " + esc(r.filter?.gate)}${notes ? ": " + esc(notes) : ""}</div>
    <div class="q">${esc(r.learner)}</div>
    <details><summary>Show the plan and lesson</summary>
      ${r.plan ? `<p><b>Plan</b></p><div style="white-space:pre-wrap;font-size:13px">${esc(r.plan)}</div>` : ""}
      <p><b>Lesson</b></p><div class="md">${renderMD(r.explanation || "")}</div>
      ${r.checks ? `<p><b>Checked claims</b></p><code style="font-size:12px;white-space:pre-wrap">${esc(JSON.stringify(r.checks))}</code>` : ""}
    </details></div>`;
}

async function renderBuilt() {
  const [d, ex] = await Promise.all([fetch("/api/pipeline").then((r) => r.json()), fetch("/api/examples").then((r) => r.json())]);
  const S = [];
  const step = (n, title, lede, inner) => S.push(`<div class="step"><div class="num">${n}</div><div><h2>${title}</h2><p class="lede">${lede}</p>${inner}</div></div>`);
  const spendFor = (prefix) => Object.entries(d.spend).filter(([k]) => k.endsWith(":" + prefix)).reduce((a, [, v]) => ({ calls: a.calls + v.calls, tok: a.tok + v.tokens_out, usd: a.usd + v.cost_usd }), { calls: 0, tok: 0, usd: 0 });

  // 1 teacher choice
  step(1, "Choosing a teacher", "Each candidate answered the same beginner prompts, with our system prompt and with no prompt design. We read them blind and rated them as teachers, not calculators. Our judgment on our own prompts, not a ranking of models.",
    d.compare && d.compare.length
      ? `<div class="tablewrap"><table class="t"><tr><th>Model</th><th>Condition</th><th>Rated</th><th>Physics right</th><th>Assumes little</th><th>Beginner can follow</th><th>Picture first</th><th>Checks understanding</th><th>Words</th></tr>
         ${d.compare.map((r) => `<tr><td>${esc(r.model)}</td><td>${esc(r.condition)}</td><td class="n">${r.rated}</td><td class="n">${nf(r.physics_right, 2)}</td><td class="n">${nf(r.assumes_little, 2)}</td><td class="n">${nf(r.beginner_can_follow, 2)}</td><td class="n">${nf(r.picture_first, 2)}</td><td class="n">${nf(r.checks_understanding, 2)}</td><td class="n">${nf(r.mean_words)}</td></tr>`).join("")}</table></div>`
      : d.compare_runs ? notYet("python make_blind.py && python summarise.py", `${d.compare_runs} answers collected, not yet rated.`) : notYet("python run_compare.py", "Comparison not run yet."));

  // 2 generation
  const g = spendFor("generate");
  step(2, "Generating teaching data", "A Feynman-technique meta-prompt asked the teacher for a teaching plan inside thought tags, then the lesson a learner reads, then every number it used as checkable JSON.",
    d.generated ? `<div class="stats">${stat(nf(d.seeds), "learner prompts")}${stat(nf(d.generated), "lessons generated")}${stat(nf(g.tok), "tokens written")}${stat("$" + nf(g.usd, 2), "teacher cost")}</div>`
      : notYet("make data", "Not generated yet."));

  // 3 filter
  const f = d.filter;
  if (f) {
    const gates = Object.entries(f.by_gate).filter(([, v]) => v.rejected || v.to_review);
    const max = Math.max(1, ...gates.map(([, v]) => v.rejected + v.to_review));
    step(3, "Filtering: which lessons deserve to be copied", "Every number in every lesson is recomputed. Contradictions, sign slips, invented coordinate transformations, missing check-in questions and near-duplicates are thrown out. Anything a program can't decide goes to a human physics check.",
      `<div class="stats">${stat(nf(f.generated), "generated")}${stat(nf(f.rejected), "rejected")}${stat(nf(f.awaiting_review), "sent to human review")}${stat(nf(d.reviewed), "human decisions")}${stat(nf(f.kept_automatically), "kept automatically")}</div>
       ${bars(gates.flatMap(([k, v]) => [[k + " (rejected)", v.rejected, "bad"], ...(v.to_review ? [[k + " (review)", v.to_review, "info"]] : [])]).filter((x) => x[1]), max)}
       ${ex.rejected.slice(0, 4).map((r) => exampleCard(r, false)).join("")}${ex.kept.slice(0, 1).map((r) => exampleCard(r, true)).join("")}`);
  } else step(3, "Filtering", "Recomputes every number, rejects contradictions and invented methods, queues the rest for a human physics check.", notYet("make filter", "Not filtered yet."));

  // 4 dataset
  const ds = d.dataset;
  step(4, "The training set", "Survivors become ShareGPT-style chat lines. The model is trained to write the plan as well as the lesson, so it learns how a lesson is built, not just the final answer.",
    ds ? `<div class="stats">${stat(nf(ds.train), "training lines")}${stat(nf(ds.val), "validation lines")}${stat(nf(ds.accepted_after_review), "accepted after review")}${stat(nf(ds.dropped_for_overlap_with_heldout), "dropped: overlap with test")}</div>
         ${bars(Object.entries(ds.by_skill).map(([k, v]) => [k + " " + (SKILL_NAMES[k] || ""), v]), Math.max(...Object.values(ds.by_skill)))}` : notYet("make dataset", "Not built yet."));

  // 5 training
  const rc = d.run_card;
  step(5, "Training the student", "Qwen2.5-14B-Instruct, frozen in 4-bit. Only small low-rank adapters on the attention and feed-forward projections are trained.",
    rc ? `<div class="stats">${stat(nf(rc.steps), "optimizer steps")}${stat(nf(rc.train_loss, 3), "mean training loss")}${rc.final_eval?.eval_loss ? stat(nf(rc.final_eval.eval_loss, 3), "final validation loss") : ""}${stat(nf(rc.wall_clock_min, 1) + " min", "wall clock")}${stat(nf(rc.trainable_params / 1e6, 1) + "M", "trainable parameters")}</div>
         ${d.loss.length ? lossChart(d.loss, d.eval_loss) : ""}
         <div class="tablewrap"><table class="t"><tr><th>Setting</th><th>Value</th></tr>
         <tr><td>Base</td><td>${esc(rc.base)}</td></tr><tr><td>Loading</td><td>${esc(rc.quantisation)}</td></tr>
         <tr><td>Adapter</td><td>rank ${rc.lora.r}, alpha ${rc.lora.alpha}, dropout ${rc.lora.dropout}</td></tr>
         <tr><td>Target modules</td><td>${esc(rc.lora.target_modules.join(", "))}</td></tr>
         <tr><td>Schedule</td><td>${esc(rc.schedule.scheduler)}, peak ${rc.schedule.lr}, warm-up ratio ${rc.schedule.warmup_ratio}, effective batch ${rc.schedule.effective_batch}, ${rc.schedule.epochs} epochs</td></tr>
         <tr><td>Data</td><td>${nf(rc.data.train_examples)} examples, ${nf(rc.data.trained_on_tokens)} trained-on tokens</td></tr>
         <tr><td>Hardware</td><td>${esc(rc.hardware.join(", "))}</td></tr><tr><td>Finished</td><td>${esc(rc.finished)}</td></tr></table></div>
         <p class="hint">A finished run proves an adapter exists. Whether it teaches better is the next step.</p>` : notYet("make train", "Not trained yet."));

  // 6 eval
  const e = d.eval;
  step(6, "Does fine-tuning help? Base vs fine-tuned", "The comparison our films said we hadn't done. Same weights, same prompt, held-out questions the student never trained on, greedy decoding.",
    e ? `<div class="grid2"><div>${bars([[e.systems.a, e.a.accuracy * 100, "info"], [e.systems.b, e.b.accuracy * 100]], 100)}<p class="hint">% of ${e.n_questions} questions with the correct final answer. 95% intervals: ${e.systems.a} ${Math.round(e.a.accuracy_95ci[0] * 100)}–${Math.round(e.a.accuracy_95ci[1] * 100)}%, ${e.systems.b} ${Math.round(e.b.accuracy_95ci[0] * 100)}–${Math.round(e.b.accuracy_95ci[1] * 100)}%. Paired exact McNemar p = ${e.paired.mcnemar_exact_p}.</p></div>
         <div class="tablewrap"><table class="t"><tr><th></th><th>${esc(e.systems.a)}</th><th>${esc(e.systems.b)}</th></tr>
         <tr><td>Wrote a teaching plan</td><td class="n">${e.a.has_plan}</td><td class="n">${e.b.has_plan}</td></tr>
         <tr><td>Ended with a check-in question</td><td class="n">${e.a.check_in}</td><td class="n">${e.b.check_in}</td></tr>
         <tr><td>Mean words</td><td class="n">${e.a.mean_words}</td><td class="n">${e.b.mean_words}</td></tr>
         ${e.a.judge_means ? ["physics", "followable", "picture_first", "check_in"].map((c) => `<tr><td>Blind judge: ${c}</td><td class="n">${e.a.judge_means[c]}</td><td class="n">${e.b.judge_means[c]}</td></tr>`).join("") : ""}
         ${e.judge_preference ? `<tr><td>Judge preferred</td><td class="n">${e.judge_preference.a}</td><td class="n">${e.judge_preference.b}</td></tr>` : ""}</table></div></div>
         <p class="hint">Measures answers to templated questions, not learning in people. An automatic judge is not a learner.</p>` : notYet("make eval", "Not evaluated yet."));

  // 7 study
  const st = d.study;
  if (st) {
    const t = st.groups.teachbot, n = st.groups.no_ai, p = st.groups.pilot;
    const grp = (label, k) => [[`Teach Bot · ${label}`, t[k]], [`No AI · ${label}`, n[k], "info"]];
    step(7, "The participant study", `${t.n} learned with Teach Bot, ${n.n} studied without AI. Five-question tests before, straight after, and later. Group averages, out of 5.`,
      `<div class="grid2"><div>${bars([...grp("pre", "pre"), ...grp("post", "post"), ...grp("recall", "recall")], 5)}</div>
       <div>${bars([["Teach Bot · minutes", t.study_min_mean], ["No AI · minutes", n.study_min_mean, "info"]], 300)}
       <p class="hint">Recorded study time. About four times as long without AI, but study time wasn't matched, so it isn't credited to the tutor alone.</p>
       <div class="notyet" style="margin-top:10px">Pilot, kept separate (n = ${p.n}, ${p.study_min_mean}-minute sessions): ${esc(p.note)}. Never averaged in.</div></div></div>
       <ul class="limits">${st.limits.map((l) => `<li>${esc(l)}</li>`).join("")}</ul>`);
  }
  $("#built").innerHTML = S.join("");
}

/* ------------------------------------------------------------------ */
/* Init                                                                */
/* ------------------------------------------------------------------ */
function showTab(name) {
  document.querySelectorAll("nav button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === name)));
  ["lesson", "compare", "built"].forEach((t) => ($(`#tab-${t}`).hidden = t !== name));
  $("#who").style.visibility = name === "lesson" ? "visible" : "hidden";
  if (name === "built") renderBuilt().catch((e) => ($("#built").innerHTML = `<p class="err">${esc(e.message)}</p>`));
  store.set("teachbot.tab", name);
}

function setBackend(id) {
  state.backend = id; store.set("teachbot.backend", id);
  $("#backendBadge").innerHTML = badge(state.backends.find((b) => b.id === id));
}

async function init() {
  const s = await fetch("/api/status").then((r) => r.json());
  state.backends = s.backends; state.heldout = s.heldout; state.testMode = s.test_mode;
  $("#testbanner").hidden = !s.test_mode;
  const sel = $("#backendSel");
  sel.innerHTML = s.backends.map((b) => `<option value="${esc(b.id)}" title="${esc(b.detail)}">${esc(b.label)}</option>`).join("");
  const saved = store.get("teachbot.backend");
  const pick = s.backends.find((b) => b.id === saved) || s.backends.find((b) => b.kind === "fine-tuned") || s.backends[0];
  if (pick) { sel.value = pick.id; setBackend(pick.id); }
  sel.addEventListener("change", () => setBackend(sel.value));

  const lid = store.get("teachbot.learner");
  const rec = lid ? await loadLearner(lid) : null;
  if (rec) { state.learner = rec; $("#learnerName").value = rec.name === "Learner" ? "" : rec.name; renderHistory(); renderMemory(rec); }
  else await newLearner();

  $("#composer").addEventListener("submit", (e) => { e.preventDefault(); send(); });
  $("#input").addEventListener("input", autosize);
  $("#input").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } });
  $("#newLearner").addEventListener("click", () => newLearner($("#learnerName").value));
  document.querySelectorAll("nav button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
  setupCompare();
  showTab(store.get("teachbot.tab") || "lesson");
}
init();
