// Builds the two PDFs in project-documents/ from the HTML in pdf/:
//   02-Project-Brief-Architecture-and-User-Flow.pdf  (pdf/brief-architecture.html)
//   03-Deep-Dive.pdf                                  (pdf/deep-dive.html)
//   04-Presenter-Readiness.pdf                        (pdf/presenter-pack.html)
//
// The HTML is assembled first: diagrams are inlined from pdf/diagrams, the
// app's icons from assets/icons, and the project brief is rendered from the
// top of the repository's README.md, word for word. Chrome then lays it out and
// prints it. The build stops if a page's content overflows its page, if text
// spills out of a diagram's box, or if an image or a font fails to load. The
// PDF's bookmarks follow the document's own contents (its [data-outline]).
//
//   node build-pdfs.mjs                    both PDFs
//   node build-pdfs.mjs deep-dive          one of them
//   node build-pdfs.mjs --preview <file.svg|file.html> <out.png> [width]

import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import MarkdownIt from "markdown-it";
import { chromium } from "playwright-core";
import { PDFDocument, PDFHexString, PDFName, PDFNumber } from "pdf-lib";

const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, "../..");
const outDir = resolve(here, "..");
const pdfDir = join(here, "pdf");
const CHROME = process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

const DOCUMENTS = {
  "brief-architecture": {
    html: "brief-architecture.html",
    pdf: "02-Project-Brief-Architecture-and-User-Flow.pdf",
    title: "The AI Startup Co-Founder Team: Project Brief, Architecture and User Flow",
    subject: "The capstone brief, word for word, with the system architecture, the agent workflow and the user flow.",
    showOutline: false,
  },
  "deep-dive": {
    html: "deep-dive.html",
    pdf: "03-Deep-Dive.pdf",
    title: "The AI Startup Co-Founder Team: Deep Dive",
    subject: "How the whole project works: the agents, the workflow, the technologies, type safety, guardrails and production readiness.",
    showOutline: true,
  },
  "presenter-pack": {
    html: "presenter-pack.html",
    pdf: "04-Presenter-Readiness.pdf",
    title: "The AI Startup Co-Founder Team: Presenter Readiness",
    subject: "Likely questions and answers, how the project was built and verified, the sign-off checklist for Steps 31 to 35, what is verified before it reaches the LLM, how the technologies work together, and the numbers to remember.",
    showOutline: false,
  },
};

// ---------- Assembly ----------

const icons = {};
function icon(name) {
  if (!(name in icons)) {
    const path = join(here, "assets/icons", `${name}.svg`);
    if (!existsSync(path)) throw new Error(`No icon called ${name}`);
    icons[name] = readFileSync(path, "utf8").trim();
  }
  return icons[name];
}

// <icon name="globe" x="10" y="20" s="18" c="#163c6b"/> inside an SVG diagram.
function svgIcons(svg) {
  return svg.replace(/<icon\s+([^>]*?)\/>/g, (_, attrs) => {
    const a = Object.fromEntries([...attrs.matchAll(/(\w+)="([^"]*)"/g)].map((m) => [m[1], m[2]]));
    const inner = icon(a.name).replace(/^<svg[^>]*>/, "").replace(/<\/svg>$/, "");
    const size = a.s || "16";
    return `<svg x="${a.x}" y="${a.y}" width="${size}" height="${size}" viewBox="0 0 16 16" fill="none" stroke="${a.c || "currentColor"}" color="${a.c || "currentColor"}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">${inner}</svg>`;
  });
}

// The brief: the top of README.md, everything above its first horizontal rule,
// rendered as it is written. It is split at its level-2 headings so it can be
// laid out over several pages: part 0 is its title, then one part a section.
let briefParts;
function briefHtml(from, to) {
  if (!briefParts) {
    const readme = readFileSync(join(repo, "README.md"), "utf8");
    const cut = readme.indexOf("\n---\n");
    if (cut < 0) throw new Error("README.md has no --- rule after the brief");
    const md = new MarkdownIt({ html: false, linkify: false, typographer: false });
    briefParts = md.render(readme.slice(0, cut)).split(/(?=<h2>)/);
  }
  const last = to ?? briefParts.length - 1;
  if (from < 0 || last >= briefParts.length) throw new Error(`The brief has parts 0 to ${briefParts.length - 1}`);
  return briefParts.slice(from, last + 1).join("");
}

function assemble(name) {
  let html = readFileSync(join(pdfDir, name), "utf8");
  // Includes may include others (a section includes its diagrams).
  for (let depth = 0; /<!--\s*include:/.test(html); depth++) {
    if (depth > 4) throw new Error("Includes nest too deeply");
    html = html.replace(/<!--\s*include:\s*([\w./-]+)\s*-->/g, (_, file) => svgIcons(readFileSync(join(pdfDir, file), "utf8")));
  }
  html = html.replace(/<!--\s*brief(?::\s*(\d+)\s*-\s*(\d+))?\s*-->/g, (_, a, b) => briefHtml(a ? +a : 0, b ? +b : undefined));
  // <i class="icon ..." data-icon="name"></i> becomes the icon's SVG.
  html = html.replace(/<i class="([^"]*)" data-icon="([\w-]+)"><\/i>/g, (_, cls, n) => `<span class="${cls}">${icon(n)}</span>`);
  const base = `<base href="${pathToFileURL(pdfDir).href}/">`;
  return html.replace("<head>", `<head>\n${base}`);
}

// ---------- In the page: numbering and checks ----------

function inPage() {
  const pages = [...document.querySelectorAll(".page")];
  pages.forEach((page, i) => {
    page.dataset.n = String(i + 1);
    page.querySelectorAll(".pn").forEach((el) => (el.textContent = String(i + 1)));
    page.querySelectorAll(".pt").forEach((el) => (el.textContent = String(pages.length)));
  });
  // Contents: each entry's page number, from the page holding its target.
  document.querySelectorAll("[data-page-of]").forEach((el) => {
    const target = document.getElementById(el.dataset.pageOf);
    el.textContent = target ? target.closest(".page").dataset.n : "?";
  });
  const problems = [];
  for (const page of pages) {
    const body = page.querySelector(":scope > .body");
    if (body && body.scrollHeight > body.clientHeight + 1) {
      problems.push(`page ${page.dataset.n}: content overflows by ${body.scrollHeight - body.clientHeight}px (${page.id || page.querySelector(".title")?.textContent?.slice(0, 50)})`);
    }
    for (const el of page.querySelectorAll(".fit")) {
      if (el.scrollHeight > el.clientHeight + 1 || el.scrollWidth > el.clientWidth + 1) {
        problems.push(`page ${page.dataset.n}: .fit element overflows (${el.className})`);
      }
    }
    const pageBox = page.getBoundingClientRect();
    for (const el of page.querySelectorAll(".body *")) {
      const r = el.getBoundingClientRect();
      if (r.width && (r.right > pageBox.right - 2 || r.bottom > pageBox.bottom - 2)) {
        problems.push(`page ${page.dataset.n}: an element runs off the page (${el.tagName.toLowerCase()}.${el.className?.baseVal ?? el.className})`);
        break;
      }
    }
  }
  // Diagrams: every text in a node group stays inside the group's first rect.
  for (const group of document.querySelectorAll("svg g.n")) {
    const rect = group.querySelector("rect");
    if (!rect) continue;
    const box = rect.getBoundingClientRect();
    for (const text of group.querySelectorAll("text")) {
      const t = text.getBoundingClientRect();
      if (t.left < box.left - 1 || t.right > box.right + 1 || t.top < box.top - 1 || t.bottom > box.bottom + 1) {
        const page = group.closest(".page");
        problems.push(`page ${page?.dataset.n}: diagram text spills out of its box: "${text.textContent.trim().slice(0, 60)}"`);
      }
    }
  }
  for (const img of document.images) {
    if (!img.complete || img.naturalWidth === 0) problems.push(`image did not load: ${img.getAttribute("src")}`);
  }
  // Bookmarks, from the contents: its parts, its entries, and for an entry
  // with data-outline-headings, the headings it names (the brief's sections).
  const outline = [];
  const pageOf = (el) => Number(el.closest(".page").dataset.n) - 1;
  const contents = document.querySelector("[data-outline]");
  if (contents) {
    outline.push({ title: "Cover", page: 0, level: 0 });
    if (pageOf(contents) > 0) outline.push({ title: "Contents", page: pageOf(contents), level: 0 });
    const items = [...contents.querySelectorAll(":scope > p.part, :scope > a[href^='#']")];
    let inPart = false;
    items.forEach((el, i) => {
      if (el.matches("p.part")) {
        const first = items.slice(i + 1).find((x) => x.matches("a"));
        outline.push({ title: el.textContent.trim(), page: pageOf(document.getElementById(first.getAttribute("href").slice(1))), level: 0 });
        inPart = true;
        return;
      }
      const target = document.getElementById(el.getAttribute("href").slice(1));
      if (!target) return problems.push(`contents entry with no target: ${el.getAttribute("href")}`);
      const n = el.querySelector(".n")?.textContent.trim();
      const t = el.querySelector(".t")?.textContent.trim() ?? el.textContent.trim();
      outline.push({ title: n && inPart ? `${n} ${t}` : t, page: pageOf(target), level: inPart ? 1 : 0 });
      if (el.dataset.outlineHeadings) {
        for (const h of document.querySelectorAll(el.dataset.outlineHeadings)) {
          outline.push({ title: h.textContent.trim().replace(/^[^\p{L}\p{N}]+/u, ""), page: pageOf(h), level: 1 });
        }
      }
    });
  }
  return { pages: pages.length, problems, outline };
}

// Writes `entries` ({ title, page, level } in order, levels 0 and 1) as the
// PDF's bookmarks, every level open.
function setOutline(pdf, entries, show) {
  if (!entries.length) return;
  const { context } = pdf;
  const pages = pdf.getPages();
  const top = [];
  for (const e of entries) {
    const node = { ...e, ref: context.nextRef(), kids: [] };
    if (e.level === 0 || !top.length) top.push(node);
    else top[top.length - 1].kids.push(node);
  }
  const root = context.nextRef();
  const write = (nodes, parent) =>
    nodes.forEach((n, i) => {
      const dict = context.obj({ Title: PDFHexString.fromText(n.title), Parent: parent, Dest: [pages[n.page].ref, PDFName.of("Fit")] });
      if (i > 0) dict.set(PDFName.of("Prev"), nodes[i - 1].ref);
      if (i < nodes.length - 1) dict.set(PDFName.of("Next"), nodes[i + 1].ref);
      if (n.kids.length) {
        dict.set(PDFName.of("First"), n.kids[0].ref);
        dict.set(PDFName.of("Last"), n.kids[n.kids.length - 1].ref);
        dict.set(PDFName.of("Count"), PDFNumber.of(n.kids.length));
        write(n.kids, n.ref);
      }
      context.assign(n.ref, dict);
    });
  write(top, root);
  context.assign(root, context.obj({ Type: "Outlines", First: top[0].ref, Last: top[top.length - 1].ref, Count: entries.length }));
  pdf.catalog.set(PDFName.of("Outlines"), root);
  if (show) pdf.catalog.set(PDFName.of("PageMode"), PDFName.of("UseOutlines"));
}

async function launch() {
  return chromium.launch({ executablePath: CHROME, headless: true });
}

async function render(browser, key) {
  const doc = DOCUMENTS[key];
  const html = assemble(doc.html);
  // Opened from a file, so Chrome lets it load the local fonts, images and styles.
  mkdirSync(join(here, ".build"), { recursive: true });
  const built = join(here, ".build", doc.html);
  writeFileSync(built, html);
  const page = await browser.newPage();
  const failed = [];
  page.on("requestfailed", (r) => failed.push(r.url()));
  page.on("console", (m) => { if (m.type() === "error") failed.push(`console: ${m.text()}`); });
  await page.goto(pathToFileURL(built).href, { waitUntil: "load" });
  await page.evaluate(() => document.fonts.ready);
  const fonts = await page.evaluate(() => [...document.fonts].filter((f) => f.status === "error").map((f) => f.family));
  const { pages, problems, outline } = await page.evaluate(inPage);
  problems.push(...failed.map((u) => `failed to load: ${u}`), ...fonts.map((f) => `font failed: ${f}`));
  if (problems.length) {
    console.error(`\n${key}: ${problems.length} problem(s)\n  - ${problems.join("\n  - ")}`);
    if (!process.env.ALLOW_PROBLEMS) {
      process.exitCode = 1;
      await page.close();
      console.error(`${doc.pdf} was not written (ALLOW_PROBLEMS=1 writes it anyway).`);
      return;
    }
  }
  const bytes = await page.pdf({ preferCSSPageSize: true, printBackground: true, tagged: true });
  await page.close();
  const pdf = await PDFDocument.load(bytes, { updateMetadata: false });
  pdf.setTitle(doc.title, { showInWindowTitleBar: true });
  pdf.setAuthor("AI Startup Co-Founder Team");
  pdf.setSubject(doc.subject);
  pdf.setKeywords(["LangGraph", "multi-agent", "FastAPI", "Next.js", "Azure OpenAI", "capstone"]);
  pdf.setCreator("project-documents/source/build-pdfs.mjs");
  pdf.setProducer("Chrome, pdf-lib");
  pdf.setLanguage("en-GB");
  setOutline(pdf, outline, doc.showOutline);
  const file = join(outDir, doc.pdf);
  writeFileSync(file, await pdf.save());
  console.log(`${doc.pdf}: ${pages} pages`);
}

async function preview(file, out, width = 1600) {
  const browser = await launch();
  const page = await browser.newPage({ viewport: { width: +width, height: 900 }, deviceScaleFactor: 2 });
  const content = file.endsWith(".svg") ? svgIcons(readFileSync(resolve(file), "utf8")) : readFileSync(resolve(file), "utf8");
  const html = `<!doctype html><html><head><base href="${pathToFileURL(pdfDir).href}/"><link rel="stylesheet" href="theme.css"><style>body{background:#f6f4ee;padding:24px}</style></head><body class="diagram">${content}</body></html>`;
  mkdirSync(join(here, ".build"), { recursive: true });
  const built = join(here, ".build", "preview.html");
  writeFileSync(built, html);
  await page.goto(pathToFileURL(built).href, { waitUntil: "load" });
  await page.evaluate(() => document.fonts.ready);
  const problems = await page.evaluate(() => {
    const out = [];
    for (const group of document.querySelectorAll("svg g.n")) {
      const box = group.querySelector("rect")?.getBoundingClientRect();
      if (!box) continue;
      for (const text of group.querySelectorAll("text")) {
        const t = text.getBoundingClientRect();
        if (t.left < box.left - 1 || t.right > box.right + 1 || t.top < box.top - 1 || t.bottom > box.bottom + 1) out.push(text.textContent.trim().slice(0, 60));
      }
    }
    return out;
  });
  await page.screenshot({ path: out, fullPage: true });
  await browser.close();
  console.log(problems.length ? `text out of its box:\n  - ${problems.join("\n  - ")}` : "no text out of its box");
}

const args = process.argv.slice(2);
if (args[0] === "--preview") {
  await preview(args[1], args[2], args[3]);
} else {
  const keys = args.length ? args : Object.keys(DOCUMENTS);
  const browser = await launch();
  for (const key of keys) await render(browser, key);
  await browser.close();
}
