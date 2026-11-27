// BoardCheck front end. Plain JavaScript, no build step, no libraries.
// User text is only ever set as text, never as HTML.

const $ = (id) => document.getElementById(id);
const SVG = "http://www.w3.org/2000/svg";

function h(tag, props = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v == null || v === false) continue;
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "class") el.className = v;
    else if (k in el && typeof v !== "string") el[k] = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  el.append(...kids.flat().filter((k) => k != null && k !== false));
  return el;
}
function s(tag, props = {}) {
  const el = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(props)) if (v != null) el.setAttribute(k, v);
  return el;
}
async function api(path, opt = {}) {
  if (opt.json !== undefined) {
    opt.body = JSON.stringify(opt.json);
    opt.headers = { "Content-Type": "application/json" };
  }
  let r;
  try { r = await fetch("/api" + path, opt); }
  catch { throw new Error("BoardCheck has stopped running. Start it again, then reload this page."); }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : "That did not work. Please try again.");
  return data;
}
let toastTimer;
function toast(text, { bad = false, action, run } = {}) {
  clearTimeout(toastTimer);
  const box = h("div", { class: bad ? "bad" : "" }, text);
  if (action) box.append(h("button", { onclick: () => { $("toast").replaceChildren(); run(); } }, action));
  $("toast").replaceChildren(box);
  toastTimer = setTimeout(() => $("toast").replaceChildren(), action ? 8000 : 5000);
}
const oops = (e) => toast(e.message, { bad: true });

// ---------------------------------------------------------------- state
const S = { step: 1, board: null, parts: [], sel: null, undo: [], checks: [], open: null, part: null, stage: null };

function steps() {
  const items = [["Good board", true], ["Name parts", !!S.board], ["Check photos", !!S.board && S.parts.length > 0]];
  $("steps").replaceChildren(...items.map(([t, on], i) =>
    h("button", { disabled: !on, "aria-current": S.step === i + 1 ? "step" : null, onclick: () => go(i + 1) }, h("b", {}, String(i + 1)), t)));
  $("which").textContent = S.board ? S.board.name : "";
}
async function go(step) {
  await flush();
  S.step = step;
  if (step === 1) S.board = null;
  steps();
  ({ 1: viewStart, 2: viewName, 3: viewCheck })[step]();
}
$("home").onclick = () => go(1);

function dropTarget(el, take) {
  let depth = 0;
  el.addEventListener("dragenter", (e) => { e.preventDefault(); depth++; el.classList.add("over"); });
  el.addEventListener("dragover", (e) => e.preventDefault());
  el.addEventListener("dragleave", () => { if (--depth <= 0) { depth = 0; el.classList.remove("over"); } });
  el.addEventListener("drop", (e) => {
    e.preventDefault(); e.stopPropagation(); depth = 0; el.classList.remove("over");
    const f = [...e.dataTransfer.files]; if (f.length) take(f);
  });
}
// A photo dropped outside a target must not make the browser leave the app.
addEventListener("dragover", (e) => e.preventDefault());
addEventListener("drop", (e) => e.preventDefault());

function picker(multiple, take) {
  const input = h("input", { type: "file", accept: "image/*,.heic,.heif", multiple, hidden: true,
    onchange: () => { const f = [...input.files]; input.value = ""; if (f.length) take(f); } });
  return input;
}

// ---------------------------------------------------------------- step 1
async function viewStart() {
  const take = async ([file]) => {
    try {
      const f = new FormData(); f.append("photo", file);
      zone.replaceChildren(h("div", { class: "spin" }), h("span", {}, "Reading the photo…"));
      await openBoard(await api("/boards", { method: "POST", body: f }), 2);
    } catch (e) { oops(e); viewStart(); }
  };
  const input = picker(false, take);
  const zone = h("div", { class: "drop" },
    h("strong", {}, "Drop a photo of a good board here"), h("span", {}, "or"),
    h("button", { class: "btn main", onclick: () => input.click() }, "Choose a photo"), input,
    h("span", {}, "Every part should be fitted. JPG, PNG, WebP or HEIC."));
  dropTarget(zone, take);
  const saved = h("section", { class: "saved" }), practice = h("span", {});
  $("view").replaceChildren(h("div", { class: "start" },
    h("h1", {}, "Start with a good board"),
    h("p", {}, "BoardCheck compares every photo with this one. You only name the parts once."),
    zone, h("div", { class: "sample" }, "No photo to hand? ", h("button", { class: "link", onclick: () => loadSample() }, "Try the sample board"), practice), saved));
  try {
    PRACTICE = await api("/practice");
    if (PRACTICE.length) practice.append(h("br"), "Practice boards, parts already named: ",
      ...PRACTICE.map((b) => h("button", { class: "link", onclick: () => loadSample(b) }, b.id)));
  } catch (e) { oops(e); }
  try {
    const boards = await api("/boards");
    if (boards.length) saved.append(h("h2", {}, "Saved boards"), h("div", { class: "boards" }, boards.map((b) =>
      h("div", { class: "board" },
        h("button", { onclick: async () => { try { await openBoard(await api(`/boards/${b.id}`), b.parts ? 3 : 2); } catch (e) { oops(e); } } },
          h("img", { src: `/api/boards/${b.id}/reference.jpg`, alt: "" }),
          h("div", {}, h("b", {}, b.name), h("span", {}, b.parts === 1 ? "1 part named" : `${b.parts} parts named`))),
        h("button", { class: "x", title: `Delete ${b.name}`, "aria-label": `Delete ${b.name}`, onclick: async () => {
          if (!confirm(`Delete "${b.name}" and all its checks? This cannot be undone.`)) return;
          try { await api(`/boards/${b.id}`, { method: "DELETE" }); viewStart(); } catch (e) { oops(e); }
        } }, "×")))));
  } catch (e) { oops(e); }
}
async function openBoard(board, step) {
  S.board = board; S.parts = board.parts; S.sel = null; S.undo = []; S.open = null; S.part = null;
  S.checks = await api(`/boards/${board.id}/checks`);
  await go(step);
}
let PRACTICE = [];
async function loadSample(practice) {
  try {
    const base = practice ? `/practice/${practice.id}` : "/samples";
    const img = await (await fetch(`/api${base}/reference.jpg`)).blob();
    const { parts } = await api(`${base}/parts.json`);
    const f = new FormData(); f.append("photo", img, "reference.jpg"); f.append("name", practice ? practice.name : "Sample board");
    const b = await api("/boards", { method: "POST", body: f });
    const full = await api(`/boards/${b.id}/parts`, { method: "PUT", json: parts.map((p, i) => ({ id: "s" + i, ...p })) });
    await openBoard(full, 2);
  } catch (e) { oops(e); }
}

// ---------------------------------------------------------------- stage
class Stage {
  constructor({ edit = false, label = "" } = {}) {
    this.edit = edit; this.k = 1; this.x = 0; this.y = 0; this.shapes = []; this.on = {}; this.touched = false;
    this.img = h("img", { alt: label, draggable: false });
    this.svg = s("svg");
    this.pan = h("div", { class: "pan" }, this.img, this.svg);
    this.el = h("div", { class: "stage" + (edit ? " edit" : ""), tabIndex: 0, "aria-label": label }, this.pan,
      h("div", { class: "zoom", onpointerdown: (e) => e.stopPropagation() },
        h("button", { title: "Zoom out", "aria-label": "Zoom out", onclick: () => this.zoom(1 / 1.4) }, "−"),
        h("button", { onclick: () => { this.touched = false; this.fit(); } }, "Fit"),
        h("button", { title: "Zoom in", "aria-label": "Zoom in", onclick: () => this.zoom(1.4) }, "+")));
    this.el.addEventListener("pointerdown", (e) => this.down(e));
    this.el.addEventListener("wheel", (e) => {
      e.preventDefault(); this.touched = true;
      if (e.ctrlKey || e.metaKey) this.zoom(Math.exp(-e.deltaY * .01), e.clientX, e.clientY);
      else { this.x -= e.deltaX; this.y -= e.deltaY; this.apply(); }
    }, { passive: false });
    this.watch = new ResizeObserver(() => { if (!this.touched) this.fit(); });
    this.watch.observe(this.el);
  }
  load(url, w, hh) {
    this.w = w; this.h = hh; this.img.src = url;
    for (const el of [this.img, this.svg]) { el.style.width = w + "px"; el.style.height = hh + "px"; }
    this.svg.setAttribute("viewBox", `0 0 ${w} ${hh}`);
    this.touched = false; this.fit();
  }
  fit() {
    const r = this.el.getBoundingClientRect();
    if (!r.width || !this.w) return;
    this.k = Math.min((r.width - 24) / this.w, (r.height - 24) / this.h);
    this.x = (r.width - this.w * this.k) / 2; this.y = (r.height - this.h * this.k) / 2; this.apply();
  }
  zoom(f, cx, cy) {
    this.touched = true;
    const r = this.el.getBoundingClientRect();
    const px = (cx ?? r.left + r.width / 2) - r.left, py = (cy ?? r.top + r.height / 2) - r.top;
    const k = Math.min(12, Math.max(.05, this.k * f));
    this.x = px - (px - this.x) * k / this.k; this.y = py - (py - this.y) * k / this.k; this.k = k; this.apply();
  }
  focusOn(pts) {
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]), r = this.el.getBoundingClientRect();
    const w = Math.max(...xs) - Math.min(...xs), hh = Math.max(...ys) - Math.min(...ys);
    const fit = Math.min((r.width - 24) / this.w, (r.height - 24) / this.h);
    this.touched = true;
    this.k = Math.min(fit * 3, Math.max(fit, Math.min(r.width / (w * 4), r.height / (hh * 4))));
    this.x = r.width / 2 - (Math.min(...xs) + w / 2) * this.k; this.y = r.height / 2 - (Math.min(...ys) + hh / 2) * this.k; this.apply();
  }
  apply() { this.pan.style.transform = `translate(${this.x}px,${this.y}px) scale(${this.k})`; this.draw(); this.on.view?.(); }
  at(e) { const r = this.el.getBoundingClientRect(); return [(e.clientX - r.left - this.x) / this.k, (e.clientY - r.top - this.y) / this.k]; }
  set(shapes) { this.shapes = shapes; this.draw(); }

  draw() {
    const u = 1 / this.k, out = [];
    const order = [...this.shapes].sort((a, b) => (a.selected ? 1 : 0) - (b.selected ? 1 : 0));
    for (const q of order) {
      const col = { part: "#ffd23f", present: "#ffffff", missing: "#ff3b30", check: "#ffb300", rubber: "#ffd23f" }[q.kind];
      const pts = q.pts.map((p) => p.join(",")).join(" "), quiet = q.kind === "present" && !q.selected;
      if (!quiet) out.push(s("polygon", { points: pts, stroke: "#000", "stroke-opacity": .55, "stroke-width": q.kind === "missing" ? 7 : 5 }));
      out.push(s("polygon", { points: pts, stroke: q.selected && this.edit ? "#5fa8ff" : col, "stroke-opacity": quiet ? .5 : 1,
        "stroke-width": q.kind === "missing" ? 4 : quiet ? 1.5 : 2.5, "stroke-dasharray": q.kind === "check" ? "7 5" : null,
        "data-id": q.id, style: "pointer-events:all;cursor:" + (this.edit ? "move" : "pointer") }));
      if (q.kind === "missing") {  // a cross as well as a colour
        const [a, b, c, d] = q.pts;
        for (const [m, n] of [[a, c], [b, d]]) out.push(s("line", { x1: m[0], y1: m[1], x2: n[0], y2: n[1], stroke: col, "stroke-width": 2, "stroke-opacity": .8, "vector-effect": "non-scaling-stroke", style: "pointer-events:none" }));
      }
      if (q.name && (!quiet || q.selected)) {
        const size = (q.kind === "missing" ? 15 : 13) * u, x = Math.min(...q.pts.map((p) => p[0])), top = Math.min(...q.pts.map((p) => p[1]));
        const bot = Math.max(...q.pts.map((p) => p[1])), inside = top < size * 1.9, w = (q.name.length * .62 + .9) * size, y = inside ? bot + 3 * u : top - size * 1.5 - 3 * u;
        const t = s("text", { x: x + size * .45, y: y + size * 1.08, "font-size": size, "font-family": "ui-monospace, SF Mono, Consolas, monospace", "font-weight": 700,
          fill: q.kind === "missing" ? "#fff" : "#14202b", style: "pointer-events:none" });
        t.textContent = q.name;
        out.push(s("rect", { x, y, width: w, height: size * 1.5, rx: 3 * u, fill: q.selected && this.edit ? "#9cc9ff" : col, style: "pointer-events:none" }), t);
      }
      if (q.selected && this.edit) q.pts.forEach((p, i) => out.push(s("rect", { x: p[0] - 6 * u, y: p[1] - 6 * u, width: 12 * u, height: 12 * u, rx: 2 * u,
        fill: "#fff", stroke: "#2340a8", "stroke-width": 2, "vector-effect": "non-scaling-stroke", "data-id": q.id, "data-corner": i,
        style: `pointer-events:all;cursor:${i % 2 ? "nesw" : "nwse"}-resize` })));
    }
    this.svg.replaceChildren(...out);
  }
  down(e) {
    if (e.target.closest(".zoom, .namer")) return;
    const id = e.target.dataset?.id, corner = e.target.dataset?.corner, start = this.at(e), sx = e.clientX, sy = e.clientY;
    const panning = e.button === 1 || e.shiftKey || !this.edit;
    if (e.button > 1) return;
    e.preventDefault(); this.el.focus({ preventScroll: true });
    const x0 = this.x, y0 = this.y;
    let moved = false;
    this.el.setPointerCapture(e.pointerId);
    const move = (m) => {
      if (!moved && Math.hypot(m.clientX - sx, m.clientY - sy) < 5) return;
      moved = true;
      if (panning) { this.touched = true; this.x = x0 + m.clientX - sx; this.y = y0 + m.clientY - sy; this.apply(); }
      else if (id) this.on.drag?.(id, corner, start, this.at(m), false);
      else this.on.rubber?.(start, this.at(m), false);
    };
    const up = (m) => {
      this.el.removeEventListener("pointermove", move); this.el.removeEventListener("pointerup", up); this.el.removeEventListener("pointercancel", up);
      if (!moved) { id ? this.on.pick?.(id) : this.edit && !panning ? this.on.point?.(start) : this.on.pick?.(null); }
      else if (!panning) id ? this.on.drag?.(id, corner, start, this.at(m), true) : this.on.rubber?.(start, this.at(m), true);
    };
    this.el.addEventListener("pointermove", move); this.el.addEventListener("pointerup", up); this.el.addEventListener("pointercancel", up);
  }
}
const corners = (b) => [[b.x, b.y], [b.x + b.w, b.y], [b.x + b.w, b.y + b.h], [b.x, b.y + b.h]];

// ---------------------------------------------------------------- step 2
let saveTimer = null, saving = Promise.resolve();
const badNames = () => {
  const seen = new Map(), bad = new Set();
  for (const p of S.parts) {
    const n = p.name.trim().toLowerCase();
    if (!n) bad.add(p.id);
    else if (seen.has(n)) { bad.add(p.id); bad.add(seen.get(n)); } else seen.set(n, p.id);
  }
  return bad;
};
function remember() { S.undo.push(JSON.stringify(S.parts)); if (S.undo.length > 60) S.undo.shift(); }
function changed() { paint(); clearTimeout(saveTimer); saveTimer = setTimeout(flush, 350); }
async function flush() {
  if (!saveTimer) return saving;
  clearTimeout(saveTimer); saveTimer = null;
  if (!S.board || badNames().size) return;
  const id = S.board.id, body = S.parts.map(({ id, name, x, y, w, h }) => ({ id, name: name.trim(), x, y, w, h }));
  saving = saving.then(async () => {
    try {
      const b = await api(`/boards/${id}/parts`, { method: "PUT", json: body });
      if (S.board?.id !== id) return;
      for (const p of S.parts) p.visibility = b.parts.find((q) => q.id === p.id)?.visibility;
      status("Saved on this computer"); tags();
    } catch (e) { oops(e); status("Not saved"); }
  });
  return saving;
}
const status = (t) => { const el = $("saved"); if (el) el.textContent = t; };
function nextName() {
  const last = S.parts.at(-1)?.name.match(/^(.*?)(\d+)$/);
  if (!last) return "";
  const used = new Set(S.parts.map((p) => p.name.toLowerCase()));
  let n = +last[2] + 1;
  while (used.has((last[1] + n).toLowerCase())) n++;
  return last[1] + n;
}
let ui = {};
function viewName() {
  const st = new Stage({ edit: true, label: "Photo of the good board" });
  S.stage = st;
  ui = { hint: h("div", { class: "hint" }, "Click a part, or drag a box around it"), list: h("ul", { class: "list" }),
    next: h("button", { class: "btn main", onclick: () => go(3) }, "Check photos"), count: h("p", {}),
    find: h("button", { class: "btn small", onclick: findAll, title: "Box and number every part the app can see. Remove any box that is not a part." }, "Find all parts") };
  st.el.append(ui.hint);
  $("view").replaceChildren(h("div", { class: "split" }, st.el, h("aside", { class: "side" },
    h("header", {}, h("h2", {}, "Parts on this board"), ui.count, ui.find), ui.list,
    h("footer", {}, h("small", { id: "saved" }), ui.next))));
  st.load(`/api/boards/${S.board.id}/reference.jpg`, S.board.width, S.board.height);
  st.on.pick = (id) => { closeNamer(); S.sel = id; paint(); };
  st.on.rubber = (a, b, done) => {
    closeNamer();
    const box = clampBox({ x: Math.min(a[0], b[0]), y: Math.min(a[1], b[1]), w: Math.abs(a[0] - b[0]), h: Math.abs(a[1] - b[1]) });
    S.rubber = box; paint();
    if (done) { if (box.w >= 6 && box.h >= 6) openNamer(box); else { S.rubber = null; paint(); toast("That box is too small. Drag a bigger one."); } }
  };
  st.on.point = async ([x, y]) => {
    closeNamer();
    if (x < 0 || y < 0 || x > S.board.width || y > S.board.height) { S.sel = null; return paint(); }
    try {
      await flush();
      const { box } = await api(`/boards/${S.board.id}/suggest`, { method: "POST", json: { x, y } });
      if (S.stage !== st) return;
      if (!box) return toast("No clear part there. Drag a box around it instead.");
      S.rubber = clampBox(box); paint(); openNamer(S.rubber);
    } catch (e) { oops(e); }
  };
  let before = null;
  st.on.drag = (id, corner, from, to, done) => {
    const p = S.parts.find((q) => q.id === id);
    if (!p) return;
    closeNamer();
    if (!before) { remember(); before = { ...p }; S.sel = id; }
    const dx = to[0] - from[0], dy = to[1] - from[1];
    if (corner == null) { p.x = Math.min(S.board.width - before.w, Math.max(0, before.x + dx)); p.y = Math.min(S.board.height - before.h, Math.max(0, before.y + dy)); }
    else {
      let x0 = before.x, y0 = before.y, x1 = before.x + before.w, y1 = before.y + before.h;
      if (corner === "0" || corner === "3") x0 = Math.min(x1 - 6, x0 + dx); else x1 = Math.max(x0 + 6, x1 + dx);
      if (corner < 2) y0 = Math.min(y1 - 6, y0 + dy); else y1 = Math.max(y0 + 6, y1 + dy);
      Object.assign(p, clampBox({ x: x0, y: y0, w: x1 - x0, h: y1 - y0 }));
    }
    if (done) { before = null; changed(); } else paint();
  };
  st.on.view = placeNamer;
  st.el.addEventListener("keydown", (e) => {
    if (e.target !== st.el) return;
    const p = S.parts.find((q) => q.id === S.sel), n = e.shiftKey ? 10 : 1;
    const d = { ArrowLeft: [-n, 0], ArrowRight: [n, 0], ArrowUp: [0, -n], ArrowDown: [0, n] }[e.key];
    if (p && d) { e.preventDefault(); remember(); p.x = Math.max(0, p.x + d[0]); p.y = Math.max(0, p.y + d[1]); changed(); }
    else if (p && (e.key === "Delete" || e.key === "Backspace")) { e.preventDefault(); removePart(p.id); }
  });
  S.rubber = null; rows(); paint(); tags();
}
addEventListener("keydown", (e) => {
  if (S.step === 2 && (e.metaKey || e.ctrlKey) && e.key === "z" && !["INPUT"].includes(document.activeElement?.tagName) && S.undo.length) {
    e.preventDefault(); S.parts = JSON.parse(S.undo.pop()); S.sel = null; rows(); changed();
  }
});
function clampBox(b) {
  const x = Math.max(0, b.x), y = Math.max(0, b.y);
  return { x, y, w: Math.max(0, Math.min(S.board.width, b.x + b.w) - x), h: Math.max(0, Math.min(S.board.height, b.y + b.h) - y) };
}
function paint() {
  if (S.step !== 2) return;
  const shapes = S.parts.map((p) => ({ id: p.id, name: p.name, kind: "part", pts: corners(p), selected: p.id === S.sel }));
  if (S.rubber) shapes.push({ kind: "rubber", pts: corners(S.rubber) });
  S.stage.set(shapes);
  for (const li of ui.list.children) li.classList.toggle("sel", li.dataset.id === S.sel);
  const bad = badNames();
  for (const i of ui.list.querySelectorAll("input")) i.classList.toggle("bad", bad.has(i.dataset.id));
  ui.next.disabled = !S.parts.length || bad.size > 0;
  ui.count.textContent = !S.parts.length ? "None named yet" : S.parts.length === 1 ? "1 part named" : `${S.parts.length} parts named`;
  if (bad.size) status("Each part needs its own name");
  ui.hint.hidden = S.parts.length > 3 || !!S.rubber;
  steps();
}
function rows() {
  ui.list.replaceChildren(...(S.parts.length ? S.parts.map((p) => h("li", { "data-id": p.id, onclick: () => { S.sel = p.id; paint(); } },
    h("input", { value: p.name, maxLength: 40, "aria-label": "Part name", "data-id": p.id, onfocus: () => { remember(); S.sel = p.id; paint(); },
      oninput: (e) => { p.name = e.target.value; changed(); }, onkeydown: (e) => { if (e.key === "Enter") e.target.blur(); } }),
    h("span", { class: "tag", hidden: true, "data-tag": p.id }),
    h("button", { class: "x", title: `Remove ${p.name}`, "aria-label": `Remove ${p.name}`, onclick: (e) => { e.stopPropagation(); removePart(p.id); } }, "×")))
    : [h("div", { class: "empty" }, "Click the first part on the photo. A box appears around it and you type its name. Or press Find all parts and the app boxes and numbers them for you.")]));
}
function tags() {
  for (const t of document.querySelectorAll("[data-tag]")) {
    const v = S.parts.find((p) => p.id === t.dataset.tag)?.visibility;
    t.hidden = !v || v === "clear";
    t.textContent = v === "hard" ? "Hard to see" : "Faint";
    t.title = "This part looks a lot like the board behind it, so a missing one may be flagged for checking by eye. A tighter box can help.";
  }
}
async function findAll() {
  const st = S.stage;
  ui.find.disabled = true; closeNamer(); status("Looking for parts…");
  try {
    await flush();
    const { boxes } = await api(`/boards/${S.board.id}/find`, { method: "POST" });
    if (S.stage !== st) return;
    if (!boxes.length) { status(""); return toast(S.parts.length ? "No more parts found. Click or drag to add the rest." : "No parts found. Click a part, or drag a box around it."); }
    remember();
    const used = new Set(S.parts.map((p) => p.name.trim().toLowerCase()));
    let n = 1;
    for (const box of boxes) {
      while (used.has(`part ${n}`)) n++;
      used.add(`part ${n}`);
      S.parts.push({ id: "p" + Math.random().toString(36).slice(2, 10), name: `Part ${n}`, ...clampBox(box) });
    }
    S.sel = null; rows(); changed();
    toast(`Found ${boxes.length} parts. Click any box that is not a part and press Delete. Click a name to rename it.`,
      { action: "Undo", run: () => { S.parts = JSON.parse(S.undo.pop()); rows(); changed(); } });
  } catch (e) { oops(e); status(""); } finally { ui.find.disabled = false; }
}
function removePart(id) {
  remember(); const p = S.parts.find((q) => q.id === id);
  S.parts = S.parts.filter((q) => q.id !== id); S.sel = null; rows(); changed();
  toast(`${p.name} removed`, { action: "Undo", run: () => { S.parts = JSON.parse(S.undo.pop()); rows(); changed(); } });
}
let namer = null;
function openNamer(box) {
  const input = h("input", { placeholder: "Part name, e.g. R1", maxLength: 40, "aria-label": "Part name", value: nextName() });
  const err = h("div", { class: "err", hidden: true });
  const ok = () => {
    const name = input.value.trim();
    if (!name) { err.textContent = "Type a name for this part"; err.hidden = false; return input.focus(); }
    if (S.parts.some((p) => p.name.trim().toLowerCase() === name.toLowerCase())) { err.textContent = `${name} is already used`; err.hidden = false; return input.select(); }
    remember();
    const id = "p" + Math.random().toString(36).slice(2, 10);
    S.parts.push({ id, name, ...box }); S.sel = id; closeNamer(); rows(); changed();
    ui.list.lastElementChild?.scrollIntoView({ block: "nearest" }); S.stage.el.focus({ preventScroll: true });
  };
  namer = { box, el: h("form", { class: "namer", onsubmit: (e) => { e.preventDefault(); ok(); } }, input,
    h("button", { class: "btn main" }, "Add"), h("button", { class: "btn", type: "button", onclick: () => closeNamer() }, "Cancel"), err) };
  input.addEventListener("keydown", (e) => { e.stopPropagation(); if (e.key === "Escape") closeNamer(); });
  S.stage.el.append(namer.el); placeNamer(); input.focus(); input.select();
}
function placeNamer() {
  if (!namer) return;
  const st = S.stage, r = st.el.getBoundingClientRect(), b = namer.box, w = namer.el.offsetWidth, hh = namer.el.offsetHeight;
  let y = (b.y + b.h) * st.k + st.y + 10;
  if (y + hh > r.height - 34) y = Math.max(8, b.y * st.k + st.y - hh - 10);
  namer.el.style.left = Math.max(8, Math.min(r.width - w - 8, b.x * st.k + st.x)) + "px"; namer.el.style.top = y + "px";
}
function closeNamer() { namer?.el.remove(); namer = null; S.rubber = null; if (S.step === 2) paint(); }

// ---------------------------------------------------------------- step 3
const WORD = { ok: "OK", missing: "MISSING", check: "CHECK BY EYE", unreadable: "CAN'T CHECK", busy: "Checking…" };
const ICON = { ok: "M5 13l5 5L20 6", missing: "M6 6l12 12M18 6L6 18", check: "M12 5v9M12 18.5v.5", unreadable: "M5 12h14" };
const final = (p) => p.answer || p.verdict;
const named = (c, v) => c.parts.filter((p) => final(p) === v).map((p) => p.name);
function summary(c) {
  if (c.status === "busy") return c.file;
  if (c.status === "unreadable") return c.note;
  const m = named(c, "missing"), q = named(c, "check");
  if (c.status === "missing") return m.join(", ") + (q.length ? `. Check by eye: ${q.join(", ")}` : "");
  return c.status === "check" ? q.join(", ") : c.parts.length === 1 ? "The part is in place" : `All ${c.parts.length} parts are in place`;
}
const icon = (st, size) => {
  const g = s("svg", { viewBox: "0 0 24 24", width: size, height: size, fill: "none", stroke: "currentColor", "stroke-width": 3.4, "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true" });
  g.append(s("path", { d: ICON[st] })); return g;
};
function viewCheck() { S.stage = null; S.part = null; if (!S.checks.some((c) => c.id === S.open)) S.open = S.checks.at(-1)?.id ?? null; drawCheck(); }

async function takePhotos(files) {
  const board = S.board, fresh = files.map((file, i) => ({ id: "busy" + Date.now() + i, status: "busy", file: file.name, parts: [], blob: file, url: URL.createObjectURL(file) }));
  S.checks.push(...fresh); S.open = fresh[0].id; S.part = null; drawCheck();
  let firstBad = null;
  for (const c of fresh) {
    const f = new FormData(); f.append("photo", c.blob, c.file);
    try {
      const done = await api(`/boards/${board.id}/checks`, { method: "POST", body: f });
      replaceCheck(c, done);
      if (!firstBad && done.status !== "ok") firstBad = done.id;
    } catch (e) { replaceCheck(c, { ...c, status: "unreadable", note: e.message, failed: true }); if (!firstBad) firstBad = c.id; }
    if (S.board !== board || S.step !== 3) return;
    drawCheck();
  }
  if (firstBad && fresh.length > 1) { S.open = firstBad; S.part = null; drawCheck(); }
}
function replaceCheck(old, now) { const i = S.checks.indexOf(old); if (i >= 0) S.checks[i] = now; if (S.open === old.id) S.open = now.id; }
const photoUrl = (c) => c.url || `/api/boards/${S.board.id}/checks/${c.id}/photo.jpg`;

function drawCheck() {
  const input = picker(true, takePhotos);
  const own = PRACTICE.find((b) => b.name === S.board.name);
  const trySample = (S.board.name === "Sample board" || own) &&
    h("button", { class: "btn", onclick: () => sampleChecks(own) }, own ? `Use the ${own.photos.length} practice photos` : "Use the 3 sample photos");
  if (!S.checks.length) {
    const zone = h("div", { class: "drop" }, h("strong", {}, "Drop photos of the same board here"), h("span", {}, "One or many, taken from the same camera position"),
      h("button", { class: "btn main", onclick: () => input.click() }, "Choose photos"), trySample, input);
    dropTarget(zone, takePhotos);
    return $("view").replaceChildren(h("div", { class: "big-empty" }, zone));
  }
  const add = h("button", { class: "add", onclick: () => input.click() }, "Add photos", h("span", {}, "or drop them here"));
  const tray = h("div", { class: "tray" }, add, input, S.checks.map((c) =>
    h("button", { class: `tile ${c.status}`, "aria-pressed": String(c.id === S.open), onclick: () => { S.open = c.id; S.part = null; drawCheck(); } },
      h("img", { src: photoUrl(c), alt: "" }), h("div", {}, h("b", {}, WORD[c.status]), h("span", {}, c.status === "busy" || c.status === "ok" ? c.file : summary(c))))));
  dropTarget(tray, takePhotos);
  const c = S.checks.find((q) => q.id === S.open);
  const box = h("div", { class: "checks" }, tray);
  $("view").replaceChildren(box);
  if (c) drawOne(box, c);
  tray.querySelector("[aria-pressed=true]")?.scrollIntoView({ block: "nearest", inline: "nearest" });
}
function drawOne(box, c) {
  const bannerIcon = c.status === "busy" ? h("div", { class: "spin" }) : icon(c.status, 40);
  box.append(h("div", { class: `banner ${c.status}`, role: "status" }, bannerIcon, h("div", {}, h("b", {}, c.status === "missing" ? `MISSING: ${named(c, "missing").join(", ")}` : c.status === "check" ? `CHECK BY EYE: ${named(c, "check").join(", ")}` : WORD[c.status]),
    h("br"), h("span", {}, c.status === "missing" ? (named(c, "check").length ? `Also check by eye: ${named(c, "check").join(", ")}` : c.file) : c.status === "check" ? "The app is not certain. Compare and decide." : summary(c)))));
  const st = new Stage({ label: "Checked photo" });
  S.stage = st;
  const split = h("div", { class: "split" }, st.el);
  box.append(split);
  if (c.status === "busy" || c.status === "unreadable") {
    const im = new Image(); im.onload = () => st.load(im.src, im.naturalWidth, im.naturalHeight); im.src = photoUrl(c);
    if (c.status === "unreadable") split.append(h("aside", { class: "side" }, h("header", {}, h("h2", {}, "This photo was not judged"), h("p", {}, c.note)), h("footer", {}, removeBtn(c))));
    return;
  }
  st.load(photoUrl(c), c.width, c.height);
  const rank = { missing: 0, check: 1, present: 2 };
  const parts = [...c.parts].sort((a, b) => rank[a.verdict] - rank[b.verdict]);
  const list = h("ul", { class: "found" }), detail = h("div", {});
  const pick = (id, zoom) => {
    S.part = id; const p = c.parts.find((q) => q.id === id);
    for (const b of list.querySelectorAll("button")) b.setAttribute("aria-pressed", String(b.dataset.id === id));
    st.set(c.parts.map((q) => ({ id: q.id, name: q.name, kind: final(q), pts: q.quad, selected: q.id === id })));
    detail.replaceChildren(...(p ? [compare(c, p)] : []));
    if (zoom && p) st.focusOn(p.quad);
  };
  list.append(...parts.map((p) => h("li", {}, h("button", { "data-id": p.id, onclick: () => pick(p.id, true) }, h("code", {}, p.name),
    h("span", { class: `pill ${final(p)}` }, { present: "In place", missing: "Missing", check: "Check by eye" }[final(p)] + (p.answer ? " (you)" : ""))))));
  split.append(h("aside", { class: "side" }, list, detail, h("footer", {}, h("div", { class: "row", style: "margin:0" }, h("button", { class: "btn small", onclick: exportCsv }, "Save results (CSV)"), removeBtn(c)))));
  st.on.pick = (id) => pick(id, false);
  pick(S.part ?? parts.find((p) => final(p) !== "present")?.id ?? null, false);
}
function removeBtn(c) {
  return h("button", { class: "btn small", onclick: async () => {
    try { if (!c.failed && !c.id.startsWith("busy")) await api(`/boards/${S.board.id}/checks/${c.id}`, { method: "DELETE" }); } catch (e) { return oops(e); }
    S.checks = S.checks.filter((q) => q !== c); S.open = S.checks.at(-1)?.id ?? null; S.part = null; drawCheck();
  } }, "Remove photo");
}
function compare(c, p) {
  const good = h("canvas", { width: 320, height: 320 }), now = h("canvas", { width: 320, height: 320 });
  const ref = new Image(), al = new Image();
  const crop = (cv, im, k) => {
    const side = Math.max(p.box.w, p.box.h) * 1.9, cx = p.box.x + p.box.w / 2, cy = p.box.y + p.box.h / 2, g = cv.getContext("2d");
    g.fillStyle = "#e3e8ec"; g.fillRect(0, 0, 320, 320); g.imageSmoothingQuality = "high";
    g.drawImage(im, (cx - side / 2) * k, (cy - side / 2) * k, side * k, side * k, 0, 0, 320, 320);
    const f = 320 / side; g.strokeStyle = "#ffd23f"; g.lineWidth = 3; g.setLineDash([8, 6]);
    g.strokeRect((p.box.x - cx + side / 2) * f, (p.box.y - cy + side / 2) * f, p.box.w * f, p.box.h * f);
  };
  const drawNow = () => crop(now, al, al.naturalWidth / S.board.width);
  ref.onload = () => crop(good, ref, ref.naturalWidth / S.board.width);
  al.onload = drawNow;
  ref.src = `/api/boards/${S.board.id}/reference.jpg`; al.src = `/api/boards/${S.board.id}/checks/${c.id}/aligned.jpg`;
  const decide = async (answer) => {
    try { const done = await api(`/boards/${S.board.id}/checks/${c.id}`, { method: "PATCH", json: { part_id: p.id, answer } }); replaceCheck(c, done); drawCheck(); } catch (e) { oops(e); }
  };
  const f = final(p);
  return h("div", { class: "compare" }, h("h3", {}, p.name, h("span", { class: `pill ${f}` }, { present: "In place", missing: "Missing", check: "Check by eye" }[f])),
    h("p", {}, p.answer ? "You decided this one." : p.reason),
    h("div", { class: "pair" }, h("figure", {}, good, h("figcaption", {}, "Good board")), h("figure", {}, now, h("figcaption", {}, "This photo"))),
    h("div", { class: "row" },
      p.answer ? h("button", { class: "btn small", onclick: () => decide(null) }, "Undo my answer")
        : [f !== "present" && h("button", { class: "btn", onclick: () => decide("present") }, "It's there"), f !== "missing" && h("button", { class: "btn", onclick: () => decide("missing") }, "It's missing")]));
}
async function sampleChecks(practice) {
  try {
    const base = practice ? `/api/practice/${practice.id}/` : "/api/samples/";
    const names = practice ? practice.photos : (await api("/samples")).filter((n) => n.startsWith("photo"));
    takePhotos(await Promise.all(names.map(async (n) => new File([await (await fetch(base + n)).blob()], n, { type: "image/jpeg" }))));
  } catch (e) { oops(e); }
}
function exportCsv() {
  const q = (v) => { let t = String(v); if (/^[=+\-@]/.test(t)) t = "'" + t; return `"${t.replace(/"/g, '""')}"`; };
  const rows = [["photo", "result", "part", "verdict", "decided by"]];
  for (const c of S.checks) for (const p of c.parts.length ? c.parts : [{ name: "", verdict: c.status }]) rows.push([c.file, WORD[c.status], p.name, final(p), p.answer ? "operator" : "app"]);
  const a = h("a", { href: URL.createObjectURL(new Blob([rows.map((r) => r.map(q).join(",")).join("\n")], { type: "text/csv" })), download: `${S.board.name}.csv` });
  a.click(); URL.revokeObjectURL(a.href);
}
go(1);
