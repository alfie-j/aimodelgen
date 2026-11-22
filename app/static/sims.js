/* Live simulators the tutor can place in a lesson with [[sim:<name>]].
   Formulas match tools/physics.py:
     flux ratio = 1/k^2,  delta m = 2.5 log10(k^2) = 5 log10(k)
     d = 10^((m - M - A)/5 + 1) pc */
"use strict";

const SIMS = (() => {
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const fmt = (x, d = 2) => {
    if (!isFinite(x)) return "–";
    if (Math.abs(x) >= 1e5 || (Math.abs(x) > 0 && Math.abs(x) < 1e-3)) return x.toExponential(2).replace("e+", "×10^").replace("e-", "×10^-");
    return Number(x.toFixed(d)).toLocaleString();
  };

  /* --------------------------------------------------------------- */
  function inverseSquare(root) {
    root.innerHTML = `
      <div class="sim-head"><b>Light spreading out</b><span>Drag to move farther from the star</span></div>
      <div class="sim-stage"><svg viewBox="0 0 600 150" role="img" aria-label="Light from a star spreading over a grid of squares"></svg></div>
      <div class="sim-ctrl"><label>Distance factor <input type="range" min="1" max="10" step="1" value="3" aria-label="Distance factor"><output>3×</output></label></div>
      <dl class="sim-read">
        <div><dt>Area the light covers</dt><dd data-k="area"></dd></div>
        <div><dt>Light on each square</dt><dd data-k="flux"></dd></div>
        <div><dt>Fainter by</dt><dd data-k="mag"></dd></div>
      </dl>
      <div class="sim-formula" data-k="formula"></div>`;
    const svg = root.querySelector("svg"), input = root.querySelector("input"), out = root.querySelector("output");
    const set = (k, html) => (root.querySelector(`[data-k=${k}]`).innerHTML = html);
    const draw = () => {
      const k = +input.value, accent = css("--accent"), line = css("--border-2"), text = css("--text-2"), ink = css("--text");
      const sx = 46, sy = 80, gx = 46 + 50 * k, size = 10.4 * k, top = sy - size / 2, cell = size / k;
      const alpha = Math.max(0.07, 1 / (k * k));
      let cells = "";
      for (let i = 0; i < k; i++) for (let j = 0; j < k; j++)
        cells += `<rect x="${gx - size / 2 + i * cell + 0.6}" y="${top + j * cell + 0.6}" width="${cell - 1.2}" height="${cell - 1.2}" fill="${accent}" fill-opacity="${alpha}"/>`;
      // the one square at distance 1, for reference
      const ref = `<rect x="${96 - 5.2}" y="${sy - 5.2}" width="10.4" height="10.4" fill="none" stroke="${text}" stroke-dasharray="2 2"/>
        <text x="96" y="${sy + 22}" font-size="11" fill="${text}" text-anchor="middle">1×</text>`;
      svg.innerHTML = `
        <line x1="${sx}" y1="${sy}" x2="${gx - size / 2}" y2="${top}" stroke="${line}"/>
        <line x1="${sx}" y1="${sy}" x2="${gx - size / 2}" y2="${top + size}" stroke="${line}"/>
        ${k > 1 ? ref : ""}
        ${cells}
        <circle cx="${sx}" cy="${sy}" r="9" fill="${accent}"/>
        <text x="${sx}" y="${sy + 28}" font-size="11" fill="${text}" text-anchor="middle">star</text>
        <text x="${gx}" y="${Math.max(14, top - 10)}" font-size="12" fill="${ink}" text-anchor="middle" font-weight="600">${k}× farther: ${k * k} square${k > 1 ? "s" : ""}</text>`;
      out.textContent = `${k}×`;
      set("area", `${k * k}×`);
      set("flux", k === 1 ? "all of it" : `1/${k * k} <small style="font-weight:400;color:var(--text-3)">(${fmt(100 / (k * k), 1)}%)</small>`);
      set("mag", `${fmt(5 * Math.log10(k), 2)} mag`);
      set("formula", k === 1 ? "Move the slider. The same light spreads over k × k squares, so each square gets 1/k² of it."
        : `Δm = 2.5 log₁₀(${k * k}) = ${fmt(5 * Math.log10(k), 2)} magnitudes. ${k === 10 ? "A factor of 100 is exactly 5 magnitudes." : ""}`);
    };
    input.addEventListener("input", draw);
    draw();
  }

  /* --------------------------------------------------------------- */
  const REF = [["Proxima Centauri", 1.30], ["Vega", 7.68], ["Pleiades", 136], ["Galactic centre", 8200]];
  function distanceModulus(root) {
    root.innerHTML = `
      <div class="sim-head"><b>Distance from magnitudes</b><span>m − M = 5 log₁₀(d / 10 pc) + A</span></div>
      <div class="sim-ctrl">
        <label>Apparent m <input type="range" min="-2" max="20" step="0.1" value="10" data-v="m" aria-label="Apparent magnitude"><output data-o="m"></output></label>
        <label>Absolute M <input type="range" min="-8" max="15" step="0.1" value="2" data-v="M" aria-label="Absolute magnitude"><output data-o="M"></output></label>
        <label>Dust A <input type="range" min="0" max="5" step="0.1" value="0" data-v="A" aria-label="Extinction in magnitudes"><output data-o="A"></output></label>
      </div>
      <div class="sim-stage"><svg viewBox="0 0 600 110" role="img" aria-label="Distance on a logarithmic scale"></svg></div>
      <dl class="sim-read">
        <div><dt>Distance modulus m − M</dt><dd data-k="mu"></dd></div>
        <div><dt>Distance</dt><dd data-k="d"></dd></div>
        <div><dt>In light-years</dt><dd data-k="ly"></dd></div>
      </dl>
      <div class="sim-formula" data-k="formula"></div>`;
    const v = (n) => +root.querySelector(`[data-v=${n}]`).value;
    const set = (k, html) => (root.querySelector(`[data-k=${k}]`).innerHTML = html);
    const svg = root.querySelector("svg");
    const draw = () => {
      const m = v("m"), M = v("M"), A = v("A"), mu = m - M, d = Math.pow(10, (mu - A) / 5 + 1);
      ["m", "M", "A"].forEach((n) => (root.querySelector(`[data-o=${n}]`).textContent = v(n).toFixed(1)));
      const accent = css("--accent"), line = css("--border-2"), text = css("--text-2"), faint = css("--text-3"), ink = css("--text");
      const L = 30, R = 570, lo = -1, hi = 6; // 0.1 pc to 1 Mpc
      const X = (pc) => L + ((Math.log10(pc) - lo) / (hi - lo)) * (R - L);
      let g = `<line x1="${L}" x2="${R}" y1="62" y2="62" stroke="${line}"/>`;
      for (let e = lo; e <= hi; e++) {
        const x = X(10 ** e), lab = e < 0 ? "0.1 pc" : e < 3 ? `${10 ** e} pc` : e < 6 ? `${10 ** (e - 3)} kpc` : "1 Mpc";
        g += `<line x1="${x}" x2="${x}" y1="58" y2="66" stroke="${line}"/><text x="${x}" y="82" font-size="10.5" fill="${faint}" text-anchor="middle">${lab}</text>`;
      }
      REF.forEach(([n, pc], i) => {
        const x = X(pc);
        g += `<circle cx="${x}" cy="62" r="3" fill="${text}"/><text x="${x}" y="${i % 2 ? 100 : 46}" font-size="10.5" fill="${text}" text-anchor="middle">${n}</text>`;
      });
      const xd = Math.min(R, Math.max(L, X(d)));
      g += `<line x1="${xd}" x2="${xd}" y1="20" y2="62" stroke="${accent}" stroke-width="2"/><circle cx="${xd}" cy="62" r="6" fill="${accent}"/>
            <text x="${Math.min(R - 30, Math.max(L + 30, xd))}" y="14" font-size="12" font-weight="600" fill="${ink}" text-anchor="middle">your star</text>`;
      svg.innerHTML = g;
      set("mu", `${mu.toFixed(1)} mag`);
      set("d", d >= 1000 ? `${fmt(d / 1000, 2)} kpc` : `${fmt(d, d < 10 ? 2 : 0)} pc`);
      set("ly", `${fmt(d * 3.26156, d * 3.26 < 100 ? 1 : 0)} ly`);
      set("formula", `d = 10<sup>(${mu.toFixed(1)}${A ? ` − ${A.toFixed(1)}` : ""})/5 + 1</sup> pc = ${fmt(d, 3)} pc.` +
        (A ? ` Without the dust you'd get ${fmt(Math.pow(10, mu / 5 + 1), 3)} pc: ignoring extinction makes a star seem farther.` : mu === 0 ? " At 10 pc, m equals M." : ""));
    };
    root.querySelectorAll("input").forEach((i) => i.addEventListener("input", draw));
    draw();
  }

  const REG = { "inverse-square": inverseSquare, "distance-modulus": distanceModulus };
  return {
    names: Object.keys(REG),
    mount(container) {
      container.querySelectorAll(".sim[data-sim]:not([data-ready])").forEach((el) => {
        const f = REG[el.dataset.sim];
        if (f) { f(el); el.dataset.ready = "1"; }
      });
    },
    redrawAll() {
      document.querySelectorAll(".sim[data-ready]").forEach((el) => {
        el.querySelector("input")?.dispatchEvent(new Event("input"));
      });
    },
  };
})();
