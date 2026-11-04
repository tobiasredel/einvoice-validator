// Browser-Test: Breiten-Sweep, DE/EN, hell/dunkel, CSP, externe Requests, XSS, Tabs. Aufruf: BASE=... node tests/ui.mjs <fixtures> <out>
import { createRequire } from "module";
import fs from "fs";
import path from "path";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const BASE = process.env.BASE || "http://127.0.0.1:18147";
const [FIX, OUT] = process.argv.slice(2);
fs.mkdirSync(OUT, { recursive: true });
const WIDTHS = [360, 390, 600, 768, 1024, 1280, 1920];
const results = [];
const record = (name, ok, detail = "") => { results.push({ name, ok, detail }); console.log(`${ok ? "OK  " : "FAIL"} ${name}${!ok && detail ? " — " + String(detail).slice(0, 220) : ""}`); };
const f = n => path.join(FIX, n);

const browser = await chromium.launch();
async function newPage(opts = {}) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, locale: "de-DE", ...opts });
  const page = await ctx.newPage();
  const log = { csp: [], external: [], dialogs: [], errors: [] };
  page.on("console", m => { if (/Content.Security.Policy|Refused to/i.test(m.text())) log.csp.push(m.text()); });
  page.on("pageerror", e => log.errors.push(e.message));
  page.on("request", r => { const u = r.url(); if (!u.startsWith(BASE) && !/^(blob|data|about):/.test(u)) log.external.push(u); });
  page.on("dialog", d => { log.dialogs.push(d.message()); d.dismiss(); });
  await page.goto(BASE + "/");
  return { ctx, page, log };
}
async function upload(page, files) { await page.setInputFiles("#file", files.map(f)); }
const overflow = page => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

// Einzelprüfung und Tabs
{
  const { ctx, page, log } = await newPage();
  await upload(page, ["en16931-cii-valid.xml"]);
  await page.waitForSelector(".hero h2", { timeout: 60000 });
  record("Einzelprüfung zeigt Ergebnis", await page.locator(".hero h2").count() > 0, await page.locator(".hero h2").first().innerText());
  record("KoSIT-Schritt sichtbar", (await page.locator(".pane").innerText()).includes("KoSIT"));
  await page.click('[data-tab="view"]');
  await page.waitForSelector("iframe.frame", { timeout: 60000 });
  const frame = page.frameLocator("iframe.frame");
  await frame.locator("#uebersicht").waitFor({ timeout: 10000 });
  record("Rechnungsansicht rendert", (await frame.locator("#uebersicht").innerText()).length > 100);
  record("iframe ohne allow-scripts", (await page.getAttribute("iframe.frame", "sandbox")) === "allow-downloads");
  const scripts = await frame.locator("script").count();
  record("Ansicht enthält keine Skripte", scripts === 0, scripts);
  await frame.locator('label[for="t-details"]').click();
  await page.waitForTimeout(300);
  record("Tab Details funktioniert ohne JavaScript", await frame.locator("#details").isVisible() && !(await frame.locator("#uebersicht").isVisible()));
  await frame.locator('label[for="t-laufzettel"]').click();
  await page.waitForTimeout(300);
  record("Tab Laufzettel funktioniert", await frame.locator("#laufzettel").isVisible());
  const links = await frame.locator("a[href]:not([download])").count();
  record("Ansicht enthält keine Navigationslinks", links === 0, links);
  await page.screenshot({ path: `${OUT}/view-de.png` });
  await page.click('[data-tab="xml"]');
  await page.waitForSelector("pre.xml");
  record("XML-Ansicht", (await page.locator("pre.xml").innerText()).includes("CrossIndustryInvoice"));
  await page.click('[data-tab="report"]');
  await page.click('.lang [data-lang="en"]');
  const txt = await page.locator(".pane").innerText();
  record("Sprachwechsel ohne neue Prüfung", /Checks|Report|Invoice/.test(txt) && !/Prüfschritte/.test(txt), txt.slice(0, 120));
  const german = (await page.locator("body").innerText()).match(/[äöüß]\w+/g);
  record("Englische Seite ohne deutsche Wörter", !german, german && german.slice(0, 8));
  await page.click('[data-tab="view"]');
  await page.waitForSelector("iframe.frame", { timeout: 60000 });
  await page.waitForTimeout(400);
  const viewEn = await page.frameLocator("iframe.frame").locator("body").innerText();
  record("Ansicht in Englisch", /Overview/.test(viewEn), viewEn.slice(0, 80));
  record("keine CSP-Verstöße", log.csp.length === 0, log.csp[0]);
  record("keine externen Requests", log.external.length === 0, log.external[0]);
  record("keine JS-Fehler", log.errors.length === 0, log.errors[0]);
  const keys = await page.evaluate(() => Object.keys(localStorage));
  record("localStorage nur Spracheinstellung", keys.every(k => k === "ev-lang"), keys);
  await ctx.close();
}

// Befunde an der Fundstelle markieren
{
  const { ctx, page } = await newPage();
  await upload(page, ["xrechnung-cii-invalid.xml"]);
  await page.waitForSelector(".hero h2", { timeout: 60000 });
  await page.click('[data-tab="view"]');
  await page.waitForSelector("iframe.frame", { timeout: 60000 });
  const note = await page.locator(".pane-note").innerText();
  record("Hinweis zu markierten Feldern", /markiert|Ohne Stelle/.test(note), note);
  const srcdoc = await page.getAttribute("iframe.frame", "srcdoc");
  record("Markierung im Dokument", /outline:2px solid #ff3b30/.test(srcdoc));
  await page.screenshot({ path: `${OUT}/view-marked.png` });
  await ctx.close();
}

// XSS aus der offiziellen Testdatei und eine eigene, präparierte Rechnung
{
  const xml = fs.readFileSync(f("en16931-cii-valid.xml"), "utf8");
  const evil = `<script>alert('xss1')</script><img src=x onerror=alert('xss2')><a href="javascript:alert('xss3')">x</a>`;
  const esc = evil.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const bad = xml.replace(/(<ram:SellerTradeParty>[\s\S]*?<ram:Name>)[^<]*/, `$1${esc}`).replace(/(<ram:IncludedNote>\s*<ram:Content>)[^<]*/, `$1${esc}`);
  fs.writeFileSync(`${OUT}/evil.xml`, bad);
  for (const [label, file] of [["KoSIT-XSS-Testfall", f("viewer-xss_ubl.xml")], ["präparierte Rechnung", `${OUT}/evil.xml`]]) {
    const { ctx, page, log } = await newPage();
    await page.setInputFiles("#file", file);
    await page.waitForSelector(".hero h2", { timeout: 60000 });
    await page.waitForTimeout(300);
    await page.click('[data-tab="view"]');
    await page.waitForSelector("iframe.frame", { timeout: 60000 });
    await page.waitForTimeout(800);
    await page.click('[data-tab="xml"]');
    await page.waitForTimeout(300);
    await page.click('[data-tab="report"]');
    await page.waitForTimeout(300);
    const injected = await page.locator(".pane img[src='x'], .pane script").count();
    record(`XSS (${label}): nichts wird ausgeführt`, log.dialogs.length === 0 && injected === 0, log.dialogs);
    await ctx.close();
  }
}

// Anlagen ohne JavaScript
{
  const { ctx, page } = await newPage();
  await upload(page, ["viewer-attachment_ubl.xml"]);
  await page.waitForSelector(".hero h2", { timeout: 60000 });
  await page.click('[data-tab="view"]');
  await page.waitForSelector("iframe.frame", { timeout: 60000 });
  const fr = page.frameLocator("iframe.frame");
  await fr.locator('label[for="t-anlagen"]').click();
  const link = fr.locator("a[download]").first();
  const hasLink = await link.count() > 0;
  record("Anlage wird Download-Link mit neutralem Typ", hasLink && (await link.getAttribute("href")).startsWith("data:application/octet-stream;base64,"));
  if (hasLink) {
    const dl = await Promise.all([page.waitForEvent("download", { timeout: 8000 }).catch(() => null), link.click()]);
    record("Download aus der abgeschotteten Ansicht klappt", !!dl[0], dl[0] && dl[0].suggestedFilename());
  }
  await ctx.close();
}

// PDF mit Bericht, Tabs, daneben
{
  const { ctx, page, log } = await newPage({ viewport: { width: 1600, height: 950 } });
  await upload(page, ["zugferd-extended.pdf"]);
  await page.waitForSelector(".hero h2", { timeout: 90000 });
  record("PDF-Tab vorhanden", await page.locator('[data-tab="pdf"]').count() === 1);
  await page.click('[data-tab="view"]');
  await page.waitForSelector("iframe.frame", { timeout: 90000 });
  record("EXTENDED-Rechnung wird dargestellt", (await page.frameLocator("iframe.frame").locator("#uebersicht").innerText()).length > 100);
  await page.click('[data-act="split"]');
  await page.waitForSelector(".split iframe:nth-child(2)", { timeout: 20000 });
  record("PDF daneben", await page.locator(".split iframe").count() === 2);
  await page.screenshot({ path: `${OUT}/split.png` });
  record("keine CSP-Verstöße mit PDF", log.csp.length === 0, log.csp[0]);
  await ctx.close();
}

// Mehrere Rechnungen, ZIP, Sweep
{
  const { ctx, page, log } = await newPage({ acceptDownloads: true });
  const all = ["en16931-cii-valid.xml", "xrechnung-cii-valid.xml", "xrechnung-cii-invalid.xml", "xrechnung-ubl-valid.xml"];
  await upload(page, all);
  await page.waitForSelector('[data-act="zip"]', { timeout: 120000 });
  record("Mehrfach-Upload: alle fertig", await page.locator("details[data-entry]").count() === 4);
  await page.locator("details[data-entry] summary").first().click();
  await page.waitForSelector("details[open] .hero h2");
  record("Fehlerfall steht oben", /Nicht gültig|Probleme|Problem/.test(await page.locator("details[open] .hero").innerText()));
  await page.click('details[open] [data-act="go"][data-dir="next"]');
  await page.waitForTimeout(400);
  record("Vor/Zurück", await page.locator("details[open]").count() === 1);
  await page.check("[data-with-views]");
  const [dl] = await Promise.all([page.waitForEvent("download", { timeout: 120000 }), page.click('[data-act="zip"]')]);
  const p = `${OUT}/${dl.suggestedFilename()}`;
  await dl.saveAs(p);
  const zipText = fs.readFileSync(p).toString("latin1");
  record("ZIP enthält Excel, Originale, Ansichten", /Pruefbericht\.xlsx/.test(zipText) && /Rechnungsansicht\.html/.test(zipText) && /en16931-cii-valid\.xml/.test(zipText));
  for (const scheme of ["light", "dark"]) {
    await page.emulateMedia({ colorScheme: scheme });
    for (const w of WIDTHS) {
      await page.setViewportSize({ width: w, height: 850 });
      await page.waitForTimeout(120);
      const o = await overflow(page);
      if (o > 0) record(`Breite ${w} ${scheme}: kein horizontales Scrollen`, false, o);
      if ((w === 390 || w === 1280) && scheme) await page.screenshot({ path: `${OUT}/batch-${w}-${scheme}.png` });
    }
  }
  record("Breiten-Sweep Gesamtübersicht 360–1920", !results.some(r => /^Breite/.test(r.name)));
  record("keine CSP-Verstöße im Mehrfach-Upload", log.csp.length === 0, log.csp[0]);
  record("keine externen Requests im Mehrfach-Upload", log.external.length === 0, log.external[0]);
  await ctx.close();
}

// Sweep Bericht und Ansicht
{
  const { ctx, page } = await newPage();
  await upload(page, ["xrechnung-cii-invalid.xml"]);
  await page.waitForSelector(".hero h2", { timeout: 60000 });
  let bad = [];
  for (const tab of ["report", "view", "xml"]) {
    await page.click(`[data-tab="${tab}"]`);
    if (tab === "view") await page.waitForSelector("iframe.frame", { timeout: 60000 });
    for (const w of WIDTHS) {
      await page.setViewportSize({ width: w, height: 850 });
      await page.waitForTimeout(100);
      const o = await overflow(page);
      if (o > 0) bad.push(`${tab}@${w}:${o}`);
      if (w === 390) await page.screenshot({ path: `${OUT}/${tab}-390.png` });
    }
  }
  record("Breiten-Sweep Einzelansicht 360–1920", bad.length === 0, bad.join(" "));
  await ctx.close();
}

await browser.close();
const failed = results.filter(r => !r.ok);
fs.writeFileSync(`${OUT}/ui-results.json`, JSON.stringify(results, null, 1));
console.log(`\n${results.length - failed.length} von ${results.length} bestanden`);
process.exit(failed.length ? 1 : 0);
