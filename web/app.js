"use strict";
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const SVG = {
  ok:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9.5"/><path d="m8 12.3 2.7 2.7L16.2 9.5"/></svg>',
  bad:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9.5"/><path d="m9 9 6 6M15 9l-6 6"/></svg>',
  warn: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9.5"/><path d="M12 7.5v5.5"/><path d="M12 16.5h.01"/></svg>',
  na:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9.5"/><path d="M8 12h8"/></svg>',
  none: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M10 12.5a2 2 0 1 1 2.6 1.9c-.4.2-.6.5-.6.9v.4"/><path d="M12 18h.01"/></svg>',
  chev: '<svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 6 6 6-6 6"/></svg>',
};

// ---------------------------------------------------------------- Sprache und Einstellungen
// localStorage hält ausschließlich die Spracheinstellung, niemals Rechnungsdaten.
function stored(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }
function store(key, v) { try { localStorage.setItem(key, v); } catch (e) { /* ohne Speicher geht es auch */ } }
let lang = stored("ev-lang") || ((navigator.language || "de").toLowerCase().startsWith("de") ? "de" : "en");
function t(text, vars) {
  let out = lang === "en" ? (I18N_EN[text] ?? text) : (I18N_DE[text] ?? text);
  if (vars) for (const k in vars) out = out.split(`{${k}}`).join(vars[k]);
  return out;
}
const pick = o => (o && typeof o === "object" ? o[lang] ?? o.de : o);
const num = (n, d = 1) => n.toLocaleString(lang === "de" ? "de-DE" : "en-GB", {maximumFractionDigits: d});
const kb = n => n < 1024 ? t("{n} Byte", {n}) : `${num(n / 1024)} KB`;

let config = {maxBytes: 25 * 1048576, maxBatch: 200, parallel: 2, versions: {}};

function applyStatic() {
  document.documentElement.lang = lang;
  document.title = t("E-Rechnung prüfen");
  document.querySelectorAll("[data-i18n]").forEach(el => { el.textContent = t(el.dataset.i18n); });
  document.querySelectorAll("[data-i18n-html]").forEach(el => { el.innerHTML = t(el.dataset.i18nHtml); });
  document.querySelectorAll(".lang button").forEach(b => b.setAttribute("aria-pressed", b.dataset.lang === lang));
  $("#dropText").textContent = t("PDF mit ZUGFeRD/Factur-X oder reine XML (XRechnung, CII, UBL). Bis zu {n} Dateien auf einmal – bei mehreren mit Gesamtübersicht und ZIP-Download.", {n: config.maxBatch});
  const v = config.versions || {};
  $("#versions").textContent = v.mustang ? t("Mustang {m} · KoSIT-Validator {k} · XRechnung-Konfiguration {c} · KoSIT-Ansicht {w}", {m: v.mustang, k: v.kosit, c: v.kosit_config, w: v.viewer}) : "";
}
document.querySelectorAll(".lang button").forEach(b => b.onclick = () => {
  lang = b.dataset.lang;
  store("ev-lang", lang);
  applyStatic();
  renderAll();
});

// Titelleiste beim Scrollen
new IntersectionObserver(([e]) => $("#bar").classList.toggle("on", !e.isIntersecting), {rootMargin: "-44px 0px 0px 0px"}).observe($("#title"));

// Toast
let toastTimer;
function toast(msg, err) {
  $("#toastText").textContent = msg;
  const el = $("#toast");
  el.classList.toggle("err", !!err);
  el.classList.add("on");
  clearTimeout(toastTimer);
  if (!err) toastTimer = setTimeout(() => el.classList.remove("on"), 2500);
}
$("#toastX").onclick = () => $("#toast").classList.remove("on");

// ---------------------------------------------------------------- Upload

const input = $("#file"), drop = $("#drop");
$("#pick").onclick = () => input.click();
input.onchange = () => { queue([...input.files]); input.value = ""; };
["dragenter", "dragover"].forEach(ev => document.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach(ev => document.addEventListener(ev, e => { e.preventDefault(); if (ev === "drop" || !e.relatedTarget) drop.classList.remove("over"); }));
document.addEventListener("drop", e => queue([...e.dataTransfer.files]));

// Alle Ergebnisse liegen nur hier im Arbeitsspeicher der Seite. Mit dem Schließen sind sie weg.
const entries = new Map();   // id → {id, file, res, tab, views: {lang: html}, split, batch, index}
const blocks = [];           // Reihenfolge der Ergebnisblöcke: {kind: "single", entry} oder {kind: "batch", ...}
let nextId = 1;

function newEntry(file, extra) {
  const e = {id: nextId++, file, res: null, tab: "report", views: {}, split: false, ...extra};
  entries.set(e.id, e);
  return e;
}

function queue(files) {
  files = files.filter(f => /\.(pdf|xml)$/i.test(f.name) || /pdf|xml/.test(f.type));
  if (!files.length) { toast(t("Bitte eine PDF- oder XML-Datei wählen."), true); return; }
  $("#about").hidden = true;
  if (files.length === 1) single(files[0]);
  else batch(files);
  $("#results").scrollIntoView({behavior: "smooth", block: "start"});
}

const sleep = ms => new Promise(r => setTimeout(r, ms));

// Schickt die Datei an den Server. Nur der Inhalt wird übertragen, der Dateiname bleibt im Browser.
async function post(url, file) {
  if (file.size > config.maxBytes) return {error: {de: `Die Datei ist größer als ${config.maxBytes / 1048576} MB.`, en: `The file is larger than ${config.maxBytes / 1048576} MB.`}};
  for (let attempt = 0; attempt < 60; attempt++) {
    let res;
    try {
      res = await fetch(url, {method: "POST", body: file, headers: {"Content-Type": "application/octet-stream"}, cache: "no-store"});
    } catch (e) {
      return {error: {de: "Keine Verbindung zum Server.", en: "No connection to the server."}};
    }
    if (res.status === 503) { await sleep((+res.headers.get("Retry-After") || 5) * 1000); continue; }
    return {res};
  }
  return {error: {de: "Der Dienst ist gerade ausgelastet.", en: "The service is busy right now."}};
}

async function validateFile(file) {
  const {res, error} = await post("/api/validate", file);
  if (error) return {error};
  const data = await res.json().catch(() => null);
  if (!data) return {error: {de: "Unerwartete Antwort vom Server.", en: "Unexpected response from the server."}};
  if (!res.ok || data.error) return {error: data.error || {de: "Prüfung fehlgeschlagen.", en: "The check failed."}};
  return data;
}

// ---------------------------------------------------------------- Einzelne Rechnung

function single(file) {
  const entry = newEntry(file);
  const box = document.createElement("section");
  box.className = "result";
  box.dataset.entry = entry.id;
  blocks.unshift({kind: "single", entry, box});
  $("#results").prepend(box);
  renderEntry(entry, box);
  validateFile(file).then(res => { entry.res = res; renderEntry(entry, box); });
}

const rep = e => e.res && e.res.reports ? e.res.reports[lang] : null;
const isPdfFile = f => /\.pdf$/i.test(f.name) || f.type === "application/pdf";

function busyCard(name, msg) {
  return `<div class="card busy"><div class="spin"></div><div><div class="t">${esc(name)}</div><div style="color:var(--label2);font-size:15px">${esc(msg)}</div></div></div>`;
}
function errorCard(name, msg) {
  return `<div class="card hero none">${SVG.none}<h2>${esc(t("Konnte nicht geprüft werden"))}</h2><p>${esc(msg)}</p><div class="file">${esc(name)}</div></div>`;
}

function renderEntry(e, box) {
  if (!e.res) { box.innerHTML = busyCard(e.file.name, t("Wird geprüft … das dauert ein paar Sekunden.")); return; }
  if (e.res.error) { box.innerHTML = errorCard(e.file.name, pick(e.res.error)); return; }
  const tabs = [["report", t("Bericht")]];
  if (e.res.xml) tabs.push(["view", t("Rechnung")]);
  if (isPdfFile(e.file)) tabs.push(["pdf", "PDF"]);
  if (e.res.xml) tabs.push(["xml", "XML"]);
  if (!tabs.some(([k]) => k === e.tab)) e.tab = "report";
  const bar = tabs.length > 1 ? `<div class="tabs" role="tablist">${tabs.map(([k, l]) => `<button type="button" role="tab" aria-selected="${k === e.tab}" data-act="tab" data-tab="${k}">${esc(l)}</button>`).join("")}</div>` : "";
  box.innerHTML = `${bar}<div class="pane"></div>`;
  renderPane(e, box.querySelector(".pane"));
}

function renderPane(e, pane) {
  if (e.pdfUrl && e.tab !== "pdf" && !e.split) { URL.revokeObjectURL(e.pdfUrl); e.pdfUrl = null; }
  if (e.tab === "report") pane.innerHTML = reportHTML(e);
  else if (e.tab === "view") renderView(e, pane);
  else if (e.tab === "pdf") pane.innerHTML = pdfHTML(e);
  else if (e.tab === "xml") pane.innerHTML = xmlHTML(e);
}

// ---------------------------------------------------------------- Bericht

function rowKV(k, v, sub) {
  if (!v) return "";
  return `<div class="row"><div class="k">${esc(k)}</div><div class="v">${esc(v)}${sub ? `<small>${esc(sub)}</small>` : ""}</div></div>`;
}

function probHTML(p, dot) {
  const where = [];
  if (p.fields && p.fields.length) where.push(`${esc(t("Betrifft:"))} ${p.fields.map(esc).join(" · ")}${p.count > p.fields.length ? " …" : ""}`);
  if (p.values && p.values.length) where.push(`${esc(t("Gefunden:"))} ${p.values.map(v => `<code>${esc(v)}</code>`).join(" ")}`);
  if (p.sums) where.push(`${esc(t("Beträge in der Rechnung:"))} ${esc(p.sums)}`);
  const bullets = (p.bullets || []).length ? `<ul style="margin:6px 0 0;padding-left:20px;font-size:15px;line-height:20px">${p.bullets.map(b => `<li>${esc(b)}</li>`).join("")}</ul>` : "";
  const src = (p.sources || []).length ? `\n${t("Gemeldet von:")} ${p.sources.join(", ")}` : "";
  return `<div class="prob${dot ? " row" : ""}">
    ${dot ? `<span class="dot ${dot}"></span>` : ""}
    <div class="main">
      <div class="t">${esc(p.title)}${p.count > 1 ? `<span class="pill">${p.count}×</span>` : ""}${(p.sources || []).length > 1 ? `<span class="src">${esc(t("beide Engines"))}</span>` : ""}</div>
      ${p.text ? `<p>${esc(p.text)}</p>` : ""}${bullets}
      ${p.fix ? `<p class="fix"><b>${esc(t("Lösung:"))}</b> ${esc(p.fix)}</p>` : ""}
      ${where.length ? `<div class="where">${where.join("<br>")}</div>` : ""}
      ${p.id || p.tech ? `<details class="tech"><summary>${esc(t("Technische Details"))}</summary><pre>${esc([p.id ? `${t("Regel:")} ${p.id}` : "", p.tech].filter(Boolean).join("\n") + src)}</pre></details>` : ""}
    </div></div>`;
}

function group(title, items, dot) {
  if (!items.length) return "";
  return `<div class="section"><div class="sh"><span>${esc(title)}</span><span>${items.length}</span></div>
    <div class="list">${items.map(p => probHTML(p, dot)).join("")}</div></div>`;
}

function collapsible(title, explain, items) {
  if (!items.length) return "";
  return `<div class="section"><div class="list"><details class="more">
    <summary class="row ic"><span class="ico na">${SVG.warn}</span><div class="main"><div>${esc(title)}</div><div class="s">${esc(items.length === 1 ? t("1 Punkt – nur bei Bedarf relevant") : t("{n} Punkte – nur bei Bedarf relevant", {n: items.length}))}</div></div>${SVG.chev}</summary>
    <p class="explain">${esc(explain)}</p>
    <div class="inner">${items.map(p => probHTML(p, "")).join("")}</div>
  </details></div></div>`;
}

function noticeRow(title, body) {
  return `<div class="section"><div class="list"><div class="row"><span class="dot orange"></span><div class="main"><div class="t">${esc(title)}</div><div class="s">${esc(body)}</div></div></div></div></div>`;
}

const stepState = s => s.ok === true ? t("bestanden") : s.ok === false ? (s.key === "xr" ? t("nein") : t("nicht bestanden")) : t("nicht geprüft");

function reportHTML(e) {
  const d = rep(e), inv = d.invoice || {}, xml = e.res.xml;
  const icon = {ok: SVG.ok, fail: SVG.bad, warn: SVG.warn, none: SVG.none}[d.verdict];
  const badge = d.verdict === "fail" ? `<span class="badge">${esc(d.headline)}</span>` : esc(d.headline);
  let h = `<div class="card hero ${d.verdict}">${icon}<h2>${badge}</h2><p>${esc(d.lead)}</p><div class="file">${esc(e.file.name)}</div></div>`;
  if (d.conflict) h += noticeRow(t("Prüf-Engines uneinig"), d.conflict);
  if (d.legal) h += noticeRow(t("Wichtiger Hinweis zum Profil"), d.legal);

  const rows = [
    rowKV(t("Rechnungsnummer"), inv.number), rowKV(t("Art"), inv.type), rowKV(t("Datum"), inv.date),
    rowKV(t("Verkäufer"), inv.seller), rowKV(t("Käufer"), inv.buyer), rowKV(t("Netto"), inv.net), rowKV(t("Brutto"), inv.total),
    inv.due && inv.due !== inv.total ? rowKV(t("Zahlbetrag"), inv.due) : "",
    rowKV(t("Leitweg-ID / Käuferreferenz"), inv.leitweg),
    rowKV(t("Format"), inv.profile ? (inv.syntax === "UBL" ? "UBL · " : "") + inv.profile : "", inv.profile_desc),
    xml && xml.embedded ? rowKV(t("Eingebettete Datei"), xml.embedded, kb(xml.size)) : "",
  ].join("");
  if (rows) h += `<div class="section"><div class="sh">${esc(t("Rechnung"))}</div><div class="list">${rows}</div></div>`;

  if (d.steps && d.steps.length) {
    h += `<div class="section"><div class="sh">${esc(t("Prüfschritte"))}</div><div class="list">` + d.steps.map(s => {
      const cls = s.ok === true ? "ok" : s.ok === false ? (s.key === "xr" ? "warn" : "bad") : "na";
      const detail = s.detail || (s.ok === null ? t("übersprungen") : "");
      return `<div class="row ic"><span class="ico ${cls}" role="img" aria-label="${esc(stepState(s))}">${SVG[cls]}</span><div class="main">${esc(s.label)}</div><div class="v" style="flex:0 0 auto;max-width:50%">${esc(detail)}</div></div>`;
    }).join("") + `</div></div>`;
  }

  h += group(d.verdict === "none" ? t("Außerdem aufgefallen") : t("Was nicht stimmt"), d.errors || [], "red");
  h += group(t("Hinweise"), d.warnings || [], "orange");
  h += collapsible(t("Für Rechnungen an Behörden (XRechnung)"),
    t("Diese Punkte zählen nur, wenn die Rechnung an eine öffentliche Stelle geht (Bund, Länder, Kommunen). Dort wird das strengere Format XRechnung verlangt. Für Rechnungen an Unternehmen sind sie unerheblich."),
    d.xrechnung || []);
  h += collapsible(t("Französische Zusatzregeln"), t("Diese Regeln gelten nur für Rechnungen im französischen E-Rechnungssystem."), d.france || []);

  const xmlBtn = xml && xml.embedded ? `<button class="link" type="button" data-act="xml-download">${esc(t("XML herunterladen"))}</button>` : "";
  h += `<div class="actions">${xmlBtn}${e.batch ? "" : `<button class="link" type="button" data-act="print">${esc(t("Bericht drucken"))}</button><button class="link" type="button" data-act="pick">${esc(t("Weitere Rechnung prüfen"))}</button>`}</div>`;
  if (d.duration !== undefined) h += `<p class="foot" style="text-align:center">${esc(t("Geprüft in {s} s", {s: num(d.duration)}))}</p>`;
  return h;
}

// ---------------------------------------------------------------- Rechnungsansicht (KoSIT)

// Felder mit Befunden: Das HTML der Ansicht trägt die BT-Nummer als CSS-Klasse. Geprüft wird ohne Ausführen in einem inerten Dokument.
function marksFor(e, html) {
  const d = rep(e);
  const collect = list => [...new Set(list.flatMap(p => p.bts || []))];
  const err = collect(d.errors || []), warn = collect(d.warnings || []).filter(b => !err.includes(b));
  const doc = new DOMParser().parseFromString(html, "text/html");
  const sel = b => `.${b},[title="${b}"],[data-title="${b}"]`;   // aktuelle Ansicht: Klasse und data-title, Rückfall-Ansicht: title
  const has = b => !!doc.querySelector(sel(b));
  const css = [
    ...err.filter(has).map(b => `${sel(b)}{background:rgba(255,59,48,.16)!important;outline:2px solid #ff3b30;outline-offset:1px;border-radius:3px}`),
    ...warn.filter(has).map(b => `${sel(b)}{background:rgba(255,149,0,.16)!important;outline:2px solid #ff9500;outline-offset:1px;border-radius:3px}`),
  ].join("");
  return {css, shown: err.filter(has).length + warn.filter(has).length, missing: [...err, ...warn].filter(b => !has(b))};
}

function frameFor(e, html) {
  const {css} = marksFor(e, html);
  const f = document.createElement("iframe");
  f.className = "frame";
  f.title = t("Rechnungsansicht");
  f.setAttribute("sandbox", "allow-downloads");   // bewusst ohne allow-scripts und allow-same-origin
  f.srcdoc = css ? html.replace("</head>", `<style>${css}</style></head>`) : html;
  return f;
}

async function loadView(file, l) {
  const {res, error} = await post(`/api/visualize?lang=${l}`, file);
  if (error) return {error};
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    return {error: (data && data.error) || {de: "Die Ansicht konnte nicht erzeugt werden.", en: "The view could not be created."}};
  }
  return {html: await res.text()};
}

async function renderView(e, pane) {
  const l = lang;
  if (!e.views[l]) {
    pane.innerHTML = busyCard(e.file.name, t("Ansicht wird erstellt …"));
    e.views[l] = await loadView(e.file, l);
    if (e.tab !== "view" || lang !== l || !pane.isConnected) return;
  }
  const v = e.views[l];
  if (v.error) { pane.innerHTML = errorCard(e.file.name, pick(v.error)); delete e.views[l]; return; }
  const {shown, missing} = marksFor(e, v.html);
  const canSplit = isPdfFile(e.file) && window.matchMedia("(min-width:1000px)").matches;
  const notes = [];
  if (shown) notes.push(t("{n} Felder mit Befunden sind farbig markiert (rot: Fehler, orange: Hinweis).", {n: shown}));
  if (missing.length) notes.push(t("Ohne Stelle in der Ansicht, weil das Feld fehlt: {list}.", {list: missing.join(", ")}));
  if (rep(e).invoice && rep(e).invoice.profile === "EXTENDED") notes.push(t("EXTENDED-Zusatzfelder, die EN 16931 nicht kennt, zeigt die Ansicht nicht; sie stehen vollständig im XML."));
  pane.innerHTML = `${canSplit ? `<div class="pane-actions"><button class="link" type="button" data-act="split">${esc(e.split ? t("PDF ausblenden") : t("PDF daneben anzeigen"))}</button></div>` : ""}<div class="${e.split && canSplit ? "split" : ""}" data-frames></div>
    <p class="pane-note">${esc(t("Darstellung der strukturierten Rechnungsdaten nach KoSIT."))} ${esc(notes.join(" "))}</p>`;
  const holder = pane.querySelector("[data-frames]");
  holder.append(frameFor(e, v.html));
  if (e.split && canSplit) holder.insertAdjacentHTML("beforeend", pdfFrame(e));
}

// ---------------------------------------------------------------- PDF und XML

function pdfFrame(e) {
  e.pdfUrl = e.pdfUrl || URL.createObjectURL(new Blob([e.file], {type: "application/pdf"}));
  return `<iframe class="frame" title="PDF" src="${e.pdfUrl}"></iframe>`;
}

function pdfHTML(e) {
  return `<div class="pane-actions"><button class="link" type="button" data-act="pdf-download">${esc(t("PDF herunterladen"))}</button></div>${pdfFrame(e)}
    <p class="pane-note">${esc(t("Das Original wird direkt aus Ihrem Browser angezeigt, ohne erneute Übertragung. Bleibt die Fläche leer, blockiert der Browser die PDF-Anzeige; dann bitte herunterladen."))}</p>`;
}

const xmlBytes = e => Uint8Array.from(atob(e.res.xml.b64), c => c.charCodeAt(0));
const MAX_XML_VIEW = 2 * 1048576;

function indentXml(node, depth, out) {
  const pad = "  ".repeat(depth);
  if (node.nodeType !== 1) return;
  const attrs = [...node.attributes].map(a => ` ${esc(a.name)}="${esc(a.value)}"`).join("");
  const kids = [...node.childNodes].filter(c => c.nodeType === 1);
  const txt = kids.length ? "" : node.textContent.trim();
  const name = esc(node.nodeName);
  if (kids.length) {
    out.push(`${pad}<span class="tag">&lt;${name}${attrs}&gt;</span>`);
    kids.forEach(c => indentXml(c, depth + 1, out));
    out.push(`${pad}<span class="tag">&lt;/${name}&gt;</span>`);
  } else if (txt) out.push(`${pad}<span class="tag">&lt;${name}${attrs}&gt;</span><span class="val">${esc(txt)}</span><span class="tag">&lt;/${name}&gt;</span>`);
  else out.push(`${pad}<span class="tag">&lt;${name}${attrs}/&gt;</span>`);
}

function xmlHTML(e) {
  const raw = xmlBytes(e);
  const actions = `<div class="pane-actions"><button class="link" type="button" data-act="xml-download">${esc(t("XML herunterladen"))}</button></div>`;
  if (raw.length > MAX_XML_VIEW) return `${actions}<p class="pane-note">${esc(t("Die XML ist für die Anzeige zu groß, bitte herunterladen."))}</p>`;
  const text = new TextDecoder().decode(raw);
  const doc = new DOMParser().parseFromString(text, "application/xml");
  if (doc.querySelector("parsererror")) return `${actions}<pre class="xml">${esc(text)}</pre>`;
  const out = [];
  indentXml(doc.documentElement, 0, out);
  return `${actions}<pre class="xml">${out.join("\n")}</pre>`;
}

function saveBlob(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement("a"), {href: url, download: name});
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}
const safeName = s => s.replace(/[\\/:*?"<>|\x00-\x1f]+/g, "_").replace(/^[\s.]+|[\s.]+$/g, "");
function xmlName(e) {
  const base = safeName(e.file.name.replace(/\.(pdf|xml)$/i, "")) || "invoice";
  return e.res.xml.embedded ? `${base}_${safeName(e.res.xml.embedded)}` : `${base}.xml`;
}

// ---------------------------------------------------------------- Aktionen (statt Inline-Handlern wegen CSP)

document.addEventListener("click", ev => {
  const el = ev.target.closest("[data-act]");
  if (!el) return;
  const box = el.closest("[data-entry]");
  const e = box ? entries.get(+box.dataset.entry) : null;
  switch (el.dataset.act) {
    case "tab": e.tab = el.dataset.tab; renderEntry(e, box); break;
    case "split": e.split = !e.split; renderEntry(e, box); break;
    case "print": window.print(); break;
    case "pick": input.click(); break;
    case "xml-download": saveBlob(new Blob([xmlBytes(e)], {type: "application/xml"}), xmlName(e)); toast(t("XML heruntergeladen")); break;
    case "pdf-download": saveBlob(e.file, safeName(e.file.name) || "invoice.pdf"); break;
    case "zip": downloadBatch(blocks.find(b => b.key === +el.dataset.batch), el); break;
    case "go": { // vor/zurück in der Gesamtübersicht
      const row = el.closest("details"), next = el.dataset.dir === "next" ? row.nextElementSibling : row.previousElementSibling;
      if (next) { row.open = false; next.open = true; next.scrollIntoView({behavior: "smooth", block: "start"}); }
      break;
    }
  }
});

function renderAll() {
  for (const b of blocks) {
    if (b.kind === "single") renderEntry(b.entry, b.box);
    else renderBatch(b);
  }
}

// ---------------------------------------------------------------- Mehrere Rechnungen

const statusOf = e => !e.res ? "wait" : e.res.error ? "error" : rep(e).verdict;
const STATUS = () => ({
  ok:    {ico: "ok",   svg: "ok",   label: t("Gültig")},
  warn:  {ico: "warn", svg: "warn", label: t("Gültig mit Hinweisen")},
  fail:  {ico: "bad",  svg: "bad",  label: t("Nicht gültig")},
  none:  {ico: "na",   svg: "none", label: t("Keine E-Rechnung")},
  error: {ico: "na",   svg: "none", label: t("Nicht prüfbar")},
});
const STATUS_RANK = {fail: 0, error: 1, none: 2, warn: 3, ok: 4};
let batchKey = 0;

async function batch(files) {
  if (files.length > config.maxBatch) {
    toast(t("Es werden nur die ersten {n} von {m} Dateien geprüft.", {n: config.maxBatch, m: files.length}), true);
    files = files.slice(0, config.maxBatch);
  }
  const key = ++batchKey;
  const b = {kind: "batch", key, list: [], next: 0, done: 0, date: new Date(), finished: false, withViews: false};
  b.list = files.map((f, i) => newEntry(f, {batch: b, index: i}));
  b.box = document.createElement("section");
  b.box.className = "result batch";
  blocks.unshift(b);
  $("#results").prepend(b.box);
  renderBatch(b);

  // so viele parallel, wie der Server Prüfplätze hat
  const worker = async () => {
    while (b.next < b.list.length) {
      const e = b.list[b.next++];
      updateRow(b, e);
      e.res = await validateFile(e.file);
      b.done++;
      updateRow(b, e);
      renderHero(b);
    }
  };
  await Promise.all(Array.from({length: config.parallel}, worker));
  b.finished = true;
  // Problemfälle nach oben
  b.list.sort((x, y) => STATUS_RANK[statusOf(x)] - STATUS_RANK[statusOf(y)] || x.index - y.index);
  renderBatch(b);
}

function renderBatch(b) {
  b.box.innerHTML = `<div class="card hero" data-hero></div>
    <div class="section"><div class="sh"><span>${esc(t("Rechnungen"))}</span><span>${b.list.length}</span></div><div class="list" data-rows>${b.list.map(e =>
      `<details class="more" data-entry="${e.id}"><summary class="row ic"></summary><div class="sub"><div class="sub-view"></div></div></details>`).join("")}</div></div>
    <div data-actions></div>`;
  b.box.querySelectorAll("details").forEach(el => el.addEventListener("toggle", () => { if (el.open) openRow(b, el); }));
  b.list.forEach(e => updateRow(b, e));
  renderHero(b);
  if (b.finished) {
    b.box.querySelector("[data-actions]").innerHTML = `<label class="opt"><input type="checkbox" data-with-views ${b.withViews ? "checked" : ""}> ${esc(t("Rechnungsansicht (HTML) je Rechnung ins ZIP legen"))}</label>
      <div class="actions" style="margin-top:8px"><button class="btn" type="button" data-act="zip" data-batch="${b.key}">${esc(t("ZIP herunterladen"))}</button>
      <button class="link" type="button" data-act="pick">${esc(t("Weitere Rechnungen prüfen"))}</button></div>`;
    b.box.querySelector("[data-with-views]").onchange = ev => { b.withViews = ev.target.checked; };
  }
}

function openRow(b, el) {
  const e = entries.get(+el.dataset.entry);
  if (!e.res) return;
  renderEntry(e, el.querySelector(".sub-view"));
  const sub = el.querySelector(".sub");
  sub.querySelector(".pager")?.remove();
  if (b.list.length > 1) sub.insertAdjacentHTML("beforeend", `<div class="pager"><button class="link" type="button" data-act="go" data-dir="prev">‹ ${esc(t("Vorherige"))}</button><button class="link" type="button" data-act="go" data-dir="next">${esc(t("Nächste"))} ›</button></div>`);
}

function updateRow(b, e) {
  const el = b.box.querySelector(`details[data-entry="${e.id}"]`);
  if (!el) return;
  const sum = el.querySelector("summary"), st = statusOf(e);
  if (st === "wait") {
    const running = b.list.indexOf(e) < b.next;
    sum.innerHTML = `${running ? `<span class="spin"></span>` : `<span class="ico na">${SVG.na}</span>`}<div class="main"><div>${esc(e.file.name)}</div><div class="s">${esc(running ? t("Wird geprüft …") : t("Wartet"))}</div></div>`;
    return;
  }
  const s = STATUS()[st], d = rep(e), inv = (d && d.invoice) || {};
  const info = [inv.number, inv.seller, inv.total].filter(Boolean).join(" · ") || (e.res.error ? pick(e.res.error) : d.headline);
  const n = d ? (d.errors || []).length : 0, w = d ? (d.warnings || []).length : 0;
  const v = st === "fail" ? (n === 1 ? t("1 Fehler") : t("{n} Fehler", {n}))
    : st === "warn" ? (w === 1 ? t("1 Hinweis") : w ? t("{n} Hinweise", {n: w}) : t("Hinweis zum Profil"))
    : st === "ok" ? t("gültig") : s.label;
  sum.innerHTML = `<span class="ico ${s.ico}" role="img" aria-label="${esc(s.label)}">${SVG[s.svg]}</span><div class="main"><div>${esc(e.file.name)}</div><div class="s">${esc(info)}</div></div><div class="v">${esc(v)}</div>${SVG.chev}`;
  if (el.open) openRow(b, el);
}

function batchCounts(b) {
  const c = {ok: 0, warn: 0, fail: 0, none: 0, error: 0, wait: 0};
  b.list.forEach(e => c[statusOf(e)]++);
  return c;
}

function renderHero(b) {
  const hero = b.box.querySelector("[data-hero]"), c = batchCounts(b), n = b.list.length, bad = c.fail + c.none + c.error;
  if (c.wait) {
    hero.className = "card hero";
    hero.innerHTML = `<div class="spin"></div><h2>${esc(t("{a} von {b} geprüft", {a: b.done, b: n}))}</h2><p>${esc(t("Das dauert ein paar Sekunden pro Datei."))}</p><div class="prog"><i style="width:${Math.round(b.done / n * 100)}%"></i></div>`;
    return;
  }
  const verdict = bad ? "fail" : c.warn ? "warn" : "ok";
  const head = !bad ? t("Alle {n} Rechnungen gültig", {n}) : t("{a} von {b} nicht in Ordnung", {a: bad, b: n});
  const parts = [];
  if (c.ok + c.warn) parts.push(c.warn ? t("{a} gültig ({b} mit Hinweisen)", {a: c.ok + c.warn, b: c.warn}) : t("{a} gültig", {a: c.ok}));
  if (c.fail) parts.push(t("{a} nicht gültig", {a: c.fail}));
  if (c.none) parts.push(t("{a} keine E-Rechnung", {a: c.none}));
  if (c.error) parts.push(t("{a} nicht prüfbar", {a: c.error}));
  const when = b.date.toLocaleString(lang === "de" ? "de-DE" : "en-GB", {dateStyle: "medium", timeStyle: "short"});
  hero.className = `card hero ${verdict}`;
  hero.innerHTML = `${{ok: SVG.ok, warn: SVG.warn, fail: SVG.bad}[verdict]}<h2>${verdict === "fail" ? `<span class="badge">${esc(head)}</span>` : esc(head)}</h2><p>${esc(parts.join(" · "))}</p><div class="file">${esc(t("Geprüft am {d}", {d: when}))}</div>`;
}

function folderName(b, e) {
  const w = Math.max(2, String(b.list.length).length);
  const base = safeName(e.file.name.replace(/\.(pdf|xml)$/i, "")).slice(0, 80) || "invoice";
  return `${String(e.index + 1).padStart(w, "0")}_${base}`;
}

async function downloadBatch(b, btn) {
  btn.disabled = true;
  const label = btn.textContent;
  try {
    const entriesOut = [];
    if (b.withViews) {
      const todo = b.list.filter(e => e.res && e.res.xml && !e.views[lang]);
      let done = 0, next = 0;
      const worker = async () => {
        while (next < todo.length) {
          const e = todo[next++];
          e.views[lang] = await loadView(e.file, lang);
          btn.textContent = t("Ansichten: {a} von {b}", {a: ++done, b: todo.length});
        }
      };
      await Promise.all(Array.from({length: config.parallel}, worker));
    }
    btn.textContent = t("ZIP wird erstellt …");
    entriesOut.push({name: t("Pruefbericht.xlsx"), data: await xlsx(batchSheets(b))});
    const enc = new TextEncoder();
    for (const e of [...b.list].sort((x, y) => x.index - y.index)) {
      const dir = folderName(b, e);
      entriesOut.push({name: `${dir}/${safeName(e.file.name) || "invoice"}`, data: new Uint8Array(await e.file.arrayBuffer())});
      if (e.res && e.res.xml && e.res.xml.embedded) entriesOut.push({name: `${dir}/${xmlName(e)}`, data: xmlBytes(e)});
      const v = e.views[lang];
      if (b.withViews && v && v.html) {
        const {css} = marksFor(e, v.html);
        entriesOut.push({name: `${dir}/${t("Rechnungsansicht.html")}`, data: enc.encode(css ? v.html.replace("</head>", `<style>${css}</style></head>`) : v.html)});
      }
    }
    const p = n => String(n).padStart(2, "0"), d = b.date;
    saveBlob(zip(entriesOut, "application/zip"), `${t("E-Rechnung-Pruefung")}_${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}.zip`);
    toast(t("ZIP heruntergeladen"));
  } catch (err) {
    toast(t("Das ZIP konnte nicht erstellt werden."), true);
  } finally {
    btn.disabled = false;
    btn.textContent = label;
  }
}

// Tabellen für den Excel-Bericht: Übersicht und Befunde
const STEP_COLS = () => [["pdfa", "PDF/A-3"], ["embed", t("Daten eingebettet")], ["meta", t("Kennzeichnung")], ["schema", t("Aufbau")],
  ["rules", t("Regeln EN 16931")], ["math", t("Beträge")], ["kosit", "KoSIT"], ["xr", t("XRechnung-tauglich")]];
const STYLE = {ok: 3, warn: 5, fail: 4, none: 6, error: 4};

function batchSheets(b) {
  const over = [], finds = [], cols = STEP_COLS();
  [...b.list].sort((x, y) => x.index - y.index).forEach(e => {
    const d = rep(e) || {}, inv = d.invoice || {}, st = statusOf(e), nr = e.index + 1;
    const err = e.res && e.res.error ? pick(e.res.error) : "";
    const steps = Object.fromEntries((d.steps || []).map(s => [s.key, s]));
    over.push([nr, e.file.name, folderName(b, e), {v: STATUS()[st].label, s: STYLE[st]}, err || d.headline || "",
      (d.errors || []).length, (d.warnings || []).length, (d.xrechnung || []).length,
      inv.number, inv.type, inv.date, inv.seller, inv.buyer, inv.net, inv.total, inv.due, inv.leitweg,
      inv.profile ? (inv.syntax === "UBL" ? "UBL · " : "") + inv.profile : "", e.res && e.res.xml ? e.res.xml.embedded || "XML" : "",
      ...cols.map(([key]) => {
        const s = steps[key];
        if (!s) return "";
        return {v: stepState(s) + (s.detail ? ` (${s.detail})` : ""), s: s.ok === true ? 3 : s.ok === false ? (key === "xr" ? 5 : 4) : 6};
      }),
      (d.errors || []).map(p => p.title).join("\n"), d.conflict || "", d.lead || "", d.duration ?? ""]);
    if (d.legal) finds.push([nr, e.file.name, inv.number, {v: t("Hinweis zum Profil"), s: 5}, t("Wichtiger Hinweis zum Profil"), d.legal]);
    if (d.conflict) finds.push([nr, e.file.name, inv.number, {v: t("Hinweis"), s: 5}, t("Prüf-Engines uneinig"), d.conflict]);
    for (const [key, label, s] of [["errors", t("Fehler"), 4], ["warnings", t("Hinweis"), 5], ["xrechnung", t("XRechnung (Behörden)"), 6], ["france", t("Frankreich"), 6]]) {
      for (const p of d[key] || []) {
        finds.push([nr, e.file.name, inv.number, {v: label, s}, p.title, p.text, p.fix, p.count || 1, (p.fields || []).join("\n"),
          (p.values || []).join("\n"), p.sums || "", (p.bullets || []).join("\n"), p.id, (p.sources || []).join(", "), p.tech]);
      }
    }
  });
  return [{
    name: t("Übersicht"),
    cols: [[t("Nr"), 5], [t("Datei"), 32], [t("Ordner im ZIP"), 32], [t("Ergebnis"), 20], [t("Kurzfassung"), 30], [t("Fehler"), 8], [t("Hinweise"), 9], [t("XRechnung-Punkte"), 10],
           [t("Rechnungsnummer"), 18], [t("Art"), 14], [t("Datum"), 11], [t("Verkäufer"), 26], [t("Käufer"), 26], [t("Netto"), 14], [t("Brutto"), 14], [t("Zahlbetrag"), 14],
           [t("Leitweg-ID / Käuferreferenz"), 20], [t("Format"), 18], [t("Eingebettete Datei"), 18],
           ...cols.map(([, l]) => [l, 16]), [t("Fehler (Titel)"), 40, true], [t("Engines uneinig"), 40, true], [t("Bewertung"), 50, true], [t("Prüfdauer (s)"), 9]],
    rows: over,
  }, {
    name: t("Befunde"),
    cols: [[t("Nr"), 5], [t("Datei"), 28], [t("Rechnungsnummer"), 18], [t("Bereich"), 18], [t("Titel"), 32, true], [t("Erklärung"), 60, true], [t("Lösung"), 50, true],
           [t("Anzahl"), 8], [t("Betrifft"), 36, true], [t("Gefundene Werte"), 24, true], [t("Beträge"), 40, true], [t("Details"), 40, true], [t("Regel"), 16], [t("Engine"), 14], [t("Technische Meldung"), 60, true]],
    rows: finds,
  }];
}

// ---------------------------------------------------------------- ZIP (ohne Kompression) und XLSX

const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) { let c = n; for (let j = 0; j < 8; j++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; }
  return t;
})();
function crc32(buf) {
  let c = ~0;
  for (let i = 0; i < buf.length; i++) c = CRC_TABLE[(c ^ buf[i]) & 255] ^ (c >>> 8);
  return ~c >>> 0;
}

// entries: [{name, data: Uint8Array}] → Blob
function zip(entries, type) {
  const enc = new TextEncoder(), now = new Date(), local = [], central = [];
  const time = (now.getHours() << 11) | (now.getMinutes() << 5) | (now.getSeconds() >> 1);
  const date = ((now.getFullYear() - 1980) << 9) | ((now.getMonth() + 1) << 5) | now.getDate();
  let offset = 0;
  for (const e of entries) {
    const name = enc.encode(e.name), crc = crc32(e.data), size = e.data.length;
    const h = new DataView(new ArrayBuffer(30));
    h.setUint32(0, 0x04034b50, true); h.setUint16(4, 20, true); h.setUint16(6, 0x0800, true); // UTF-8-Dateinamen
    h.setUint16(10, time, true); h.setUint16(12, date, true); h.setUint32(14, crc, true);
    h.setUint32(18, size, true); h.setUint32(22, size, true); h.setUint16(26, name.length, true);
    local.push(h, name, e.data);
    const c = new DataView(new ArrayBuffer(46));
    c.setUint32(0, 0x02014b50, true); c.setUint16(4, 20, true); c.setUint16(6, 20, true); c.setUint16(8, 0x0800, true);
    c.setUint16(12, time, true); c.setUint16(14, date, true); c.setUint32(16, crc, true);
    c.setUint32(20, size, true); c.setUint32(24, size, true); c.setUint16(28, name.length, true); c.setUint32(42, offset, true);
    central.push(c, name);
    offset += 30 + name.length + size;
  }
  const cdSize = central.reduce((n, x) => n + x.byteLength, 0);
  const end = new DataView(new ArrayBuffer(22));
  end.setUint32(0, 0x06054b50, true); end.setUint16(8, entries.length, true); end.setUint16(10, entries.length, true);
  end.setUint32(12, cdSize, true); end.setUint32(16, offset, true);
  return new Blob([...local, ...central, end], {type});
}

const xmlEsc = s => String(s ?? "").replace(/[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]/g, "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const colName = n => { let s = ""; for (n++; n; n = Math.floor((n - 1) / 26)) s = String.fromCharCode(65 + (n - 1) % 26) + s; return s; };

// sheets: [{name, cols: [[Überschrift, Breite, Zeilenumbruch]], rows: [[Wert | {v, s}]]}] → Uint8Array
// Stile: 0 normal, 1 Kopfzeile, 2 Umbruch, 3 grün, 4 rot, 5 orange, 6 grau
async function xlsx(sheets) {
  const NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"';
  const R = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"';
  const cell = (ref, v, s) => {
    if (v === "" || v == null) return s ? `<c r="${ref}" s="${s}"/>` : "";
    if (typeof v === "number") return `<c r="${ref}" s="${s}"><v>${v}</v></c>`;
    return `<c r="${ref}" s="${s}" t="inlineStr"><is><t xml:space="preserve">${xmlEsc(String(v).slice(0, 32000))}</t></is></c>`;
  };
  const sheetXML = sh => {
    const last = colName(sh.cols.length - 1) + (sh.rows.length + 1);
    const head = `<row r="1">${sh.cols.map(([h], j) => cell(colName(j) + 1, h, 1)).join("")}</row>`;
    const body = sh.rows.map((r, i) => `<row r="${i + 2}">${r.map((x, j) => {
      const o = x && typeof x === "object" ? x : {v: x};
      return cell(colName(j) + (i + 2), o.v, o.s ?? (sh.cols[j][2] ? 2 : 0));
    }).join("")}</row>`).join("");
    return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet ${NS} ${R}>` +
      `<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>` +
      `<sheetFormatPr defaultRowHeight="15"/><cols>${sh.cols.map(([, w], j) => `<col min="${j + 1}" max="${j + 1}" width="${w}" customWidth="1"/>`).join("")}</cols>` +
      `<sheetData>${head}${body}</sheetData><autoFilter ref="A1:${last}"/></worksheet>`;
  };
  const font = (b, color) => `<font>${b ? "<b/>" : ""}<sz val="11"/>${color ? `<color rgb="FF${color}"/>` : ""}<name val="Calibri"/></font>`;
  const xf = (font, fill, wrap) => `<xf numFmtId="0" fontId="${font}" fillId="${fill}" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment vertical="top"${wrap ? ' wrapText="1"' : ""}/></xf>`;
  const styles = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet ${NS}>` +
    `<fonts count="6">${font(0)}${font(1)}${font(1, "248A3D")}${font(1, "D70015")}${font(1, "C93400")}${font(0, "8E8E93")}</fonts>` +
    `<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFE5E5EA"/><bgColor indexed="64"/></patternFill></fill></fills>` +
    `<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>` +
    `<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>` +
    `<cellXfs count="7">${xf(0, 0)}${xf(1, 2, 1)}${xf(0, 0, 1)}${xf(2, 0)}${xf(3, 0)}${xf(4, 0)}${xf(5, 0)}</cellXfs>` +
    `<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>`;
  const sheetName = s => xmlEsc(s.replace(/[\\/?*[\]:]/g, "_").slice(0, 31));
  const workbook = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook ${NS} ${R}><sheets>` +
    sheets.map((s, i) => `<sheet name="${sheetName(s.name)}" sheetId="${i + 1}" r:id="rId${i + 1}"/>`).join("") + `</sheets><definedNames>` +
    sheets.map((s, i) => `<definedName name="_xlnm._FilterDatabase" localSheetId="${i}" hidden="1">'${sheetName(s.name)}'!$A$1:$${colName(s.cols.length - 1)}$${s.rows.length + 1}</definedName>`).join("") +
    `</definedNames></workbook>`;
  const PR = "http://schemas.openxmlformats.org/package/2006/relationships", OR = "http://schemas.openxmlformats.org/officeDocument/2006/relationships";
  const wbRels = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="${PR}">` +
    sheets.map((s, i) => `<Relationship Id="rId${i + 1}" Type="${OR}/worksheet" Target="worksheets/sheet${i + 1}.xml"/>`).join("") +
    `<Relationship Id="rId${sheets.length + 1}" Type="${OR}/styles" Target="styles.xml"/></Relationships>`;
  const CT = "application/vnd.openxmlformats-officedocument.spreadsheetml";
  const types = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">` +
    `<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>` +
    `<Override PartName="/xl/workbook.xml" ContentType="${CT}.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="${CT}.styles+xml"/>` +
    sheets.map((s, i) => `<Override PartName="/xl/worksheets/sheet${i + 1}.xml" ContentType="${CT}.worksheet+xml"/>`).join("") + `</Types>`;
  const rels = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="${PR}"><Relationship Id="rId1" Type="${OR}/officeDocument" Target="xl/workbook.xml"/></Relationships>`;
  const enc = new TextEncoder();
  const files = [["[Content_Types].xml", types], ["_rels/.rels", rels], ["xl/workbook.xml", workbook],
                 ["xl/_rels/workbook.xml.rels", wbRels], ["xl/styles.xml", styles],
                 ...sheets.map((s, i) => [`xl/worksheets/sheet${i + 1}.xml`, sheetXML(s)])];
  return new Uint8Array(await zip(files.map(([name, s]) => ({name, data: enc.encode(s)}))).arrayBuffer());
}

// ---------------------------------------------------------------- Start

applyStatic();
fetch("/api/config", {cache: "no-store"}).then(r => r.json()).then(c => { config = c; applyStatic(); }).catch(() => {});
