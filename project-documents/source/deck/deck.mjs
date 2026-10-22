// Builds ../../01-Project-Highlights.pptx: ten slides in the app's colours, with
// real screenshots, a contents slide whose cards are links, a row of links on
// every slide, fade transitions, the pipeline built up click by click, and
// speaker notes.
//
//   cd project-documents/source && npm run deck
//
// The figures on the slides are the deep dive's (pdf/dd/*.html), which takes
// them from the code, both test suites and the recorded run of 22 October 2026.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import pptxgen from "pptxgenjs";
import sharp from "sharp";
import JSZip from "jszip";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SOURCE = path.resolve(HERE, "..");
const OUT = path.resolve(SOURCE, "..", "01-Project-Highlights.pptx");
const BUILD = path.join(SOURCE, ".build", "deck");
const SHOTS = path.join(SOURCE, "assets", "screenshots");
const ICONS = path.join(SOURCE, "assets", "icons");

// The app's palette (frontend design tokens), one agent to each accent.
const THEME = {
  name: "Co-Founder",
  headFontFace: "Georgia",
  bodyFontFace: "Arial",
  colors: {
    dk1: "1C1B18", // ink
    lt1: "FDFCF9", // surface
    dk2: "163C6B", // primary navy
    lt2: "F6F4EE", // paper
    accent1: "4A3AA7", // Chief of Staff
    accent2: "EB6834", // Marketing
    accent3: "1BAF7A", // Finance
    accent4: "2A78D6", // Technical
    accent5: "E87BA4", // Risk & Compliance
    accent6: "6B7889", // web research
    hlink: "1D58AD",
    folHlink: "3B2E8A",
  },
};
const SLOTS = ["dk1", "lt1", "dk2", "lt2", "accent1", "accent2", "accent3", "accent4", "accent5", "accent6", "hlink", "folHlink"];

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5 in
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = "The AI Startup Co-Founder Team: project highlights";
pres.subject = "Ten highlights of the capstone project, with links between them";
pres.author = "AI Startup Co-Founder Team";
pres.company = "AI Startup Co-Founder Team";

const C = pres.SchemeColor;
const INK = C.text1;
const NAVY = C.text2;
const WHITE = C.background1;
const PAPER = C.background2;
const HEAD = "+mj-lt"; // the theme's heading font
const MONO = "Courier New";

// Each agent's colour; `deep` is the darker shade its icons are drawn in.
const AGENT = {
  chief: { scheme: C.accent1, deep: "3B2E8A", icon: "chief", name: "Chief of Staff" },
  marketing: { scheme: C.accent2, deep: "B4461B", icon: "megaphone", name: "Marketing Strategy" },
  finance: { scheme: C.accent3, deep: "0D7651", icon: "chart", name: "Financial Planning" },
  technical: { scheme: C.accent4, deep: "1C5CAB", icon: "chip", name: "Technical Feasibility" },
  risk: { scheme: C.accent5, deep: "B03C6F", icon: "shield", name: "Risk & Compliance" },
  research: { scheme: C.accent6, deep: "48525F", icon: "globe", name: "Web research" },
  primary: { scheme: C.text2, deep: "163C6B" },
};

// The page grid, in inches.
const X0 = 0.6;
const XR = 12.733;
const CW = XR - X0;
const TOP = 1.95; // where content starts under a one-line title
const BOTTOM = 6.6; // where it ends, above the footer row
const FOOT = 6.99;

const TITLES = [
  "",
  "The AI Startup Co-Founder Team",
  "Contents",
  "Built to the brief",
  "A founding team",
  "Plan, act, check",
  "Watch it work",
  "Grounded in evidence",
  "Safe by design",
  "Strategy to proposal",
  "Production-ready",
];
const COUNT = TITLES.length - 1;

// pptxgenjs writes its relationship id into a hyperlink object, so each object
// gets a fresh one.
const link = (n) => ({ slide: n, tooltip: `${n} · ${TITLES[n]}` });
const shadow = (opacity = 0.1) => ({ type: "outer", color: "1C1B18", opacity, blur: 9, offset: 2, angle: 90 });
const hairline = () => ({ color: INK, transparency: 85, width: 0.75 });

// ---------------------------------------------------------------- assets

const icons = new Map();
async function icon(name, hex) {
  const key = `${name}-${hex}`;
  if (!icons.has(key)) {
    const svg = fs
      .readFileSync(path.join(ICONS, `${name}.svg`), "utf8")
      .replace(/currentColor/g, `#${hex}`)
      .replace("<svg ", '<svg width="256" height="256" ');
    const png = await sharp(Buffer.from(svg)).png().toBuffer();
    icons.set(key, "image/png;base64," + png.toString("base64"));
  }
  return icons.get(key);
}

// A screenshot cut to the part a slide shows, at about 300 dpi for its size.
async function shot(name, file, crop, inches) {
  const out = path.join(BUILD, `${name}.jpg`);
  await sharp(path.join(SHOTS, file))
    .extract(crop)
    .resize({ width: Math.min(crop.width, Math.round(inches * 300)) })
    .jpeg({ quality: 86, mozjpeg: true })
    .toFile(out);
  return { path: out, aspect: crop.width / crop.height };
}

// ---------------------------------------------------------------- helpers

function text(slide, runs, opts) {
  slide.addText(runs, { isTextBox: true, margin: 0, valign: "top", ...opts });
}

// An icon in a filled circle. `solid` circles take a white icon; soft ones a
// tint of the colour with the icon in its deep shade.
async function disc(slide, { x, y, d, agent, iconName, solid = true, name, dashed = false }) {
  const a = AGENT[agent];
  slide.addShape(pres.shapes.OVAL, {
    x,
    y,
    w: d,
    h: d,
    fill: { color: a.scheme, transparency: solid ? 0 : 84 },
    line: dashed ? { color: a.scheme, width: 1.25, dashType: "dash" } : undefined,
    objectName: `${name} circle`,
  });
  const s = d * 0.54;
  slide.addImage({
    data: await icon(iconName ?? a.icon, solid ? "FFFFFF" : a.deep),
    x: x + (d - s) / 2,
    y: y + (d - s) / 2,
    w: s,
    h: s,
    altText: `${name} icon`,
    objectName: `${name} icon`,
  });
}

// A screenshot on a white card with rounded corners and a soft shadow.
function framed(slide, img, { x, y, w, pad = 0.07, name, alt, dark = false }) {
  const iw = w - 2 * pad;
  const ih = iw / img.aspect;
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x,
    y,
    w,
    h: ih + 2 * pad,
    rectRadius: 0.09,
    fill: { color: WHITE },
    line: dark ? undefined : hairline(),
    shadow: shadow(dark ? 0.35 : 0.12),
    objectName: `${name} frame`,
  });
  slide.addImage({ path: img.path, x: x + pad, y: y + pad, w: iw, h: ih, altText: alt, objectName: name });
  return ih + 2 * pad;
}

// A transparent shape over a card or button that carries its link, so the
// whole area can be clicked and the text keeps its colours. (pptxgenjs gives
// linked text an underline, and a link on runs of text no relationship.)
function hotspot(slide, { x, y, w, h, hyperlink, name }) {
  slide.addShape(pres.shapes.RECTANGLE, { x, y, w, h, fill: { color: WHITE, transparency: 100 }, hyperlink, objectName: name });
}

// The links along the bottom of a slide: back, every slide by number, next.
function nav(slide, n, dark = false) {
  const d = 0.24;
  const gap = 0.07;
  const arrow = 0.36;
  const dots = COUNT * d + (COUNT - 1) * gap;
  let x = XR - (arrow + 0.08 + dots + 0.08 + arrow);
  const fg = dark ? PAPER : INK;
  const button = (label, target, at, tip) => {
    text(slide, label, {
      shape: pres.shapes.ROUNDED_RECTANGLE,
      x: at,
      y: FOOT - 0.02,
      w: arrow,
      h: d + 0.04,
      rectRadius: 0.14,
      fill: { color: dark ? NAVY : PAPER },
      line: { color: fg, transparency: target ? 70 : 88, width: 0.75 },
      color: fg,
      transparency: target ? 20 : 75,
      fontSize: 11,
      bold: true,
      align: "center",
      valign: "middle",
      objectName: target ? `${tip} slide button` : `No ${tip.toLowerCase()} slide`,
    });
    if (target) hotspot(slide, { x: at, y: FOOT - 0.02, w: arrow, h: d + 0.04, hyperlink: { slide: target, tooltip: `${tip}: ${target} · ${TITLES[target]}` }, name: `${tip} slide` });
  };
  button("←", n > 1 ? n - 1 : null, x, "Previous");
  x += arrow + 0.08;
  for (let k = 1; k <= COUNT; k++) {
    const here = k === n;
    text(slide, String(k), {
      shape: pres.shapes.OVAL,
      x,
      y: FOOT,
      w: d,
      h: d,
      fill: { color: here ? (dark ? WHITE : NAVY) : dark ? NAVY : PAPER },
      line: here ? undefined : { color: fg, transparency: 72, width: 0.75 },
      color: here ? (dark ? NAVY : WHITE) : fg,
      transparency: here ? 0 : 30,
      fontSize: 8,
      bold: here,
      align: "center",
      valign: "middle",
      objectName: here ? `Slide ${k}, this slide` : `Slide ${k} button`,
    });
    if (!here) hotspot(slide, { x, y: FOOT, w: d, h: d, hyperlink: link(k), name: `Go to slide ${k}` });
    x += d + gap;
  }
  button("→", n < COUNT ? n + 1 : null, x - gap + 0.08, "Next");
}

// Where the slide's subject is covered in depth.
function more(slide, where, dark = false) {
  text(slide, `More in the deep dive: ${where}`, {
    x: 4.55,
    y: FOOT,
    w: 3.9,
    h: 0.24,
    fontSize: 9.5,
    color: dark ? PAPER : INK,
    transparency: dark ? 35 : 45,
    valign: "middle",
    objectName: "Deep dive reference",
  });
}

function heading(slide, kicker, title) {
  slide.addText([{ text: kicker, options: { charSpacing: 1.5 } }], { placeholder: "kicker" });
  slide.addText(title, { placeholder: "title" });
}

// A small label in capitals, used over a group of content.
function label(slide, words, { x, y, w, dark = false, color }) {
  text(slide, [{ text: words, options: { charSpacing: 1 } }], {
    x,
    y,
    w,
    h: 0.26,
    fontSize: 10.5,
    bold: true,
    color: color ?? (dark ? PAPER : NAVY),
    objectName: `Label: ${words}`,
  });
}

// ---------------------------------------------------------------- layouts

const brandMark = (y) =>
  ["accent1", "accent2", "accent3", "accent4", "accent5"].map((k, i) => ({
    rect: { x: X0 + i * 0.25, y, w: 0.2, h: 0.045, fill: { color: C[k] } },
  }));

pres.defineSlideMaster({
  title: "COVER",
  background: { color: NAVY },
  objects: [
    ...brandMark(0.62),
    {
      placeholder: {
        options: { name: "kicker", type: "body", x: X0, y: 0.84, w: 6.4, h: 0.3, fontSize: 12, bold: true, color: PAPER, margin: 0, valign: "top" },
        text: "",
      },
    },
    {
      placeholder: {
        options: { name: "title", type: "title", x: X0, y: 1.3, w: 6.6, h: 1.95, fontSize: 46, color: WHITE, align: "left", valign: "top", margin: 0 },
        text: "",
      },
    },
    {
      placeholder: {
        options: { name: "subtitle", type: "body", x: X0, y: 3.42, w: 5.95, h: 1.3, fontSize: 16, color: PAPER, margin: 0, valign: "top", lineSpacingMultiple: 1.08 },
        text: "",
      },
    },
  ],
});

for (const dark of [false, true]) {
  pres.defineSlideMaster({
    title: dark ? "CONTENT_DARK" : "CONTENT",
    background: { color: dark ? NAVY : PAPER },
    objects: [
      ...brandMark(0.44),
      {
        placeholder: {
          options: { name: "kicker", type: "body", x: X0, y: 0.58, w: 9, h: 0.28, fontSize: 11, bold: true, color: dark ? PAPER : NAVY, margin: 0, valign: "top" },
          text: "",
        },
      },
      {
        placeholder: {
          options: { name: "title", type: "title", x: X0, y: 0.88, w: CW, h: 0.8, fontSize: 32, color: dark ? WHITE : INK, align: "left", valign: "top", margin: 0 },
          text: "",
        },
      },
      {
        text: {
          text: "The AI Startup Co-Founder Team  ·  Project highlights",
          options: { x: X0, y: FOOT, w: 3.8, h: 0.24, fontSize: 9.5, color: dark ? PAPER : INK, transparency: dark ? 35 : 45, valign: "middle", margin: 0 },
        },
      },
    ],
  });
}

// ---------------------------------------------------------------- slides

async function build() {
  fs.mkdirSync(BUILD, { recursive: true });
  const liveCrop = { left: 56, top: 44, width: 2290, height: 1266 };
  const img = {
    live: await shot("live-graph", "live-graph-specialists.jpg", liveCrop, 8.2),
    finished: await shot("live-graph-finished", "live-graph-finished.jpg", liveCrop, 5.5),
    strategy: await shot("strategy", "result-strategy-c.jpg", { left: 60, top: 440, width: 2270, height: 1186 }, 4.9),
    fred: await shot("fred", "result-fred-c.jpg", { left: 70, top: 285, width: 1580, height: 1030 }, 5.7),
    studio: await shot("studio", "document-studio-c.jpg", { left: 0, top: 0, width: 2341, height: 1626 }, 6.5),
    monitor: await shot("monitor", "monitor-c.jpg", { left: 70, top: 600, width: 2250, height: 1026 }, 5.5),
  };

  // 1 · Cover ------------------------------------------------------------
  pres.addSection({ title: "Opening" });
  {
    const s = pres.addSlide({ masterName: "COVER", sectionTitle: "Opening" });
    s.addText([{ text: "CAPSTONE PROJECT  ·  OCTOBER 2026", options: { charSpacing: 2 } }], { placeholder: "kicker" });
    s.addText([{ text: "The AI Startup", options: { breakLine: true } }, { text: "Co-Founder Team" }], { placeholder: "title" });
    s.addText(
      "A Chief of Staff and four specialist agents turn a founder's brief into a launch strategy, checking each other's work and settling their disagreements on the way.",
      { placeholder: "subtitle" }
    );
    const team = [
      ["chief", "Chief of Staff"],
      ["marketing", "Marketing"],
      ["finance", "Finance"],
      ["technical", "Technical"],
      ["risk", "Risk & Compliance"],
    ];
    for (const [i, [agent, name]] of team.entries()) {
      const x = X0 + i * 1.2;
      await disc(s, { x, y: 4.95, d: 0.62, agent, name });
      text(s, name, { x, y: 5.66, w: 1.12, h: 0.4, fontSize: 10.5, color: PAPER, objectName: `${name} name` });
    }
    text(s, [{ text: "Explore the highlights   →", options: { bold: true } }], {
      shape: pres.shapes.ROUNDED_RECTANGLE,
      x: X0,
      y: 6.2,
      w: 3.05,
      h: 0.5,
      rectRadius: 0.25,
      fill: { color: WHITE },
      color: NAVY,
      fontSize: 13,
      align: "center",
      valign: "middle",
      objectName: "Explore the highlights button",
    });
    hotspot(s, { x: X0, y: 6.2, w: 3.05, h: 0.5, hyperlink: { slide: 2, tooltip: "2 · Contents" }, name: "Explore the highlights" });
    text(s, "In Slide Show, every card, number and arrow is a link.", {
      x: 3.9,
      y: 6.2,
      w: 3.1,
      h: 0.5,
      fontSize: 11,
      color: PAPER,
      transparency: 25,
      valign: "middle",
      objectName: "How to navigate",
    });
    text(s, "Python 3.12  ·  LangGraph  ·  FastAPI  ·  Next.js 16  ·  Azure OpenAI gpt-5-mini", {
      x: X0,
      y: 6.99,
      w: 6.4,
      h: 0.24,
      fontSize: 9.5,
      color: PAPER,
      transparency: 35,
      valign: "middle",
      objectName: "Built with",
    });
    framed(s, img.finished, { x: 7.2, y: 0.78, w: 5.53, name: "The live graph, finished", alt: "The live graph at the end of a run: every step done in 2 minutes 30 seconds, with the steps listed beside it", dark: true });
    framed(s, img.strategy, { x: XR - 4.9, y: 3.55, w: 4.9, name: "The launch strategy", alt: "The launch strategy from the recorded run: Go with conditions, each claim tagged with its agent, the reviews beside it", dark: true });
    s.addNotes(
      "The AI Startup Co-Founder Team is our capstone: a founding team made of AI agents. A Chief of Staff and four specialists, for marketing, finance, technical feasibility and risk, take a founder's brief and return a launch strategy. They do not just answer once: the Chief of Staff reviews every report and sends weak ones back, the specialists check each other's work, and the Chief of Staff settles their disagreements before writing one strategy.\n\n" +
        "On the right is the real app: the live graph at the end of a run, and the strategy it produced.\n\n" +
        "This deck is interactive. In Slide Show, the button takes you to the contents, and every slide has numbered links along the bottom."
    );
  }

  // 2 · Contents ---------------------------------------------------------
  {
    const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Opening" });
    heading(s, "CONTENTS", "Eight highlights, one click away");
    text(s, "Click a card to open it. On every slide, the numbers at the bottom right jump anywhere and the arrows step through.", {
      x: X0,
      y: 1.62,
      w: 10,
      h: 0.32,
      fontSize: 13,
      color: INK,
      transparency: 30,
      objectName: "How to use this slide",
    });
    const cards = [
      [3, "Built to the brief", "Every requirement met, then a product built around it", "primary", "check"],
      [4, "A founding team", "Four specialists, and a Chief of Staff who decides", "chief", "team"],
      [5, "Plan, act, check", "A LangGraph state machine whose every loop is bounded", "technical", "flow"],
      [6, "Watch it work", "The live graph: a full decision in 2 minutes 30 seconds", "marketing", "pulse"],
      [7, "Grounded in evidence", "Web research, figures over MCP, the founder's own files", "research", "globe"],
      [8, "Safe by design", "Typed decisions, fenced inputs and hard limits", "risk", "shield"],
      [9, "Strategy to proposal", "An investment proposal, its money worked out in code", "finance", "chart"],
      [10, "Production-ready", "578 tests, PostgreSQL, Langfuse, Docker and CI", "primary", "server"],
    ];
    const w = (CW - 3 * 0.2) / 4;
    const h = 2.05;
    for (const [i, [n, title, teaser, agent, iconName]] of cards.entries()) {
      const x = X0 + (i % 4) * (w + 0.2);
      const y = 2.3 + Math.floor(i / 4) * (h + 0.2);
      text(
        s,
        [
          { text: title, options: { fontFace: HEAD, fontSize: 17, color: INK, breakLine: true } },
          { text: teaser, options: { fontSize: 12, color: INK, transparency: 30, paraSpaceBefore: 5 } },
        ],
        {
          shape: pres.shapes.ROUNDED_RECTANGLE,
          x,
          y,
          w,
          h,
          rectRadius: 0.1,
          fill: { color: WHITE },
          line: hairline(),
          shadow: shadow(0.08),
          margin: [16, 16, 10, 62],
          objectName: `Card: ${title}`,
        }
      );
      text(s, String(n).padStart(2, "0"), {
        x: x + 0.22,
        y: y + 0.22,
        w: 0.7,
        h: 0.32,
        fontFace: HEAD,
        fontSize: 15,
        color: INK,
        transparency: 45,
        objectName: `Card ${n} number`,
      });
      await disc(s, { x: x + w - 0.22 - 0.56, y: y + 0.18, d: 0.56, agent, iconName, solid: false, name: `Card ${n}` });
      hotspot(s, { x, y, w, h, hyperlink: link(n), name: `Open slide ${n}: ${title}` });
    }
    nav(s, 2);
    s.addNotes(
      "Here are the eight highlights. Each card is a link: click one to go straight to it, and use the numbers at the bottom of any slide to jump around or come back here.\n\n" +
        "The order follows the system: what the brief asked for, the team, how its workflow runs, what it looks like live, how it stays grounded and safe, the document it produces, and how it is run in production."
    );
  }

  // 3 · Built to the brief -----------------------------------------------
  pres.addSection({ title: "The team and its workflow" });
  {
    const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "The team and its workflow" });
    heading(s, "THE BRIEF", "The brief, met in full, then taken further");
    label(s, "WHAT THE BRIEF ASKED FOR", { x: X0, y: TOP, w: 6 });
    const asked = [
      ["Role-based agents", "Marketing, Finance, Technical and Risk & Compliance, each with its own remit"],
      ["Manager-led delegation", "The Chief of Staff states the decision and assigns only the specialists it needs"],
      ["Plan–Act–Check, with reflection", "Every report scored 1 to 5 against a rubric; below 4, it is rewritten once"],
      ["Critique and conflict resolution", "Specialists cross-check each other; the Chief of Staff settles every clash"],
      ["One unified launch strategy", "A memo that leads with go, go with conditions, or not yet"],
      ["Optimised for cost, latency and structure", "Specialists in parallel, follow-ups rerun only what changed, typed outputs"],
    ];
    for (const [i, [need, how]] of asked.entries()) {
      const y = 2.32 + i * 0.64;
      await disc(s, { x: X0, y: y + 0.03, d: 0.34, agent: "finance", iconName: "check", solid: false, name: need });
      text(
        s,
        [
          { text: need, options: { bold: true, fontSize: 14, color: INK, breakLine: true } },
          { text: how, options: { fontSize: 12, color: INK, transparency: 30 } },
        ],
        { x: 1.08, y, w: 5.95, h: 0.6, objectName: `Requirement: ${need}` }
      );
    }
    text(s, "Built on the libraries the brief named: LangGraph, LangChain, OpenAI, Pydantic, FastAPI, uvicorn and python-dotenv.", {
      x: X0,
      y: 6.25,
      w: 6.45,
      h: 0.36,
      fontSize: 11,
      italic: true,
      color: INK,
      transparency: 30,
      objectName: "Libraries",
    });

    const px = 7.35;
    const pw = XR - px;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: px,
      y: TOP,
      w: pw,
      h: BOTTOM - TOP,
      rectRadius: 0.12,
      fill: { color: NAVY, transparency: 93 },
      objectName: "Added beyond the brief panel",
    });
    label(s, "WHAT WE ADDED BEYOND IT", { x: px + 0.28, y: TOP + 0.2, w: 4.5 });
    const added = [
      ["Web research first", "Facts, sources and questions before the team starts", "research", "search"],
      ["Our own MCP server", "Official figures from FRED, exact and cited", "technical", "globe"],
      ["The founder's files", "PDF, Office and more, cited by page or sheet", "marketing", "paperclip"],
      ["A live graph", "Each step lit up as it runs", "chief", "pulse"],
      ["Investment proposal", "NPV, IRR and payback worked out in code", "finance", "chart"],
      ["Document control", "Drafts, versions, currencies, units, redaction", "chief", "document"],
      ["Guardrails, limits", "Fenced inputs, rate limits, no key in the browser", "risk", "shield"],
      ["Production", "PostgreSQL, Docker, GitLab CI and Langfuse", "primary", "server"],
    ];
    const colW = (pw - 0.56 - 0.2) / 2;
    for (const [i, [title, body, agent, iconName]] of added.entries()) {
      const x = px + 0.28 + (i % 2) * (colW + 0.2);
      const y = 2.6 + Math.floor(i / 2) * 0.98;
      await disc(s, { x, y, d: 0.4, agent, iconName, solid: true, name: title });
      text(s, title, { x: x + 0.52, y, w: colW - 0.52, h: 0.4, fontSize: 12.5, bold: true, color: INK, valign: "middle", objectName: `Added: ${title}` });
      text(s, body, { x, y: y + 0.46, w: colW, h: 0.44, fontSize: 11, color: INK, transparency: 30, objectName: `Added: ${title}, detail` });
    }
    nav(s, 3);
    more(s, "part 2, the brief and how it was met");
    s.addNotes(
      "The brief asked for role-based agents, a Chief of Staff who delegates, Plan-Act-Check loops with reflection, critique and conflict resolution between the agents, one unified strategy, and attention to cost, latency and structured output. Every one of those is in the system, and the deep dive traces each requirement to the code.\n\n" +
        "We then built a product around it. Before the team starts, it can research the brief on the web and ask the founder what only they know. It reads official economic figures through our own MCP server, and the founder's own documents. Afterwards it writes an investment proposal whose money is worked out in code, under full document control. And it runs like a production service: guardrails, limits, PostgreSQL, Docker, CI and Langfuse."
    );
  }

  // 4 · The team ---------------------------------------------------------
  {
    const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "The team and its workflow" });
    heading(s, "THE TEAM", "A founding team that debates, then decides");
    const lw = 6.25;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: X0,
      y: TOP,
      w: lw,
      h: 1.3,
      rectRadius: 0.1,
      fill: { color: C.accent1, transparency: 88 },
      objectName: "Chief of Staff card",
    });
    await disc(s, { x: X0 + 0.24, y: TOP + 0.29, d: 0.72, agent: "chief", name: "Chief of Staff" });
    text(s, "Chief of Staff", { x: X0 + 1.2, y: TOP + 0.16, w: 4.8, h: 0.4, fontFace: HEAD, fontSize: 20, color: INK, objectName: "Chief of Staff title" });
    text(s, "Works out the decision, delegates, reviews every report against a rubric, settles each conflict and writes the strategy.", {
      x: X0 + 1.2,
      y: TOP + 0.56,
      w: 4.85,
      h: 0.66,
      fontSize: 12.5,
      color: INK,
      transparency: 25,
      objectName: "Chief of Staff remit",
    });
    const specialists = [
      ["marketing", "Marketing Strategy", "One niche to win first, and a cheap test of demand"],
      ["finance", "Financial Planning", "A price, a first-phase budget, margin, break-even and runway"],
      ["technical", "Technical Feasibility", "The thinnest first demo, build or buy, and the effort in weeks"],
      ["risk", "Risk & Compliance", "Risks that could stop the launch, their safeguards, the law"],
    ];
    const cw = (lw - 0.2) / 2;
    const ch = 1.45;
    for (const [i, [agent, name, remit]] of specialists.entries()) {
      const x = X0 + (i % 2) * (cw + 0.2);
      const y = 3.45 + Math.floor(i / 2) * (ch + 0.2);
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
        x,
        y,
        w: cw,
        h: ch,
        rectRadius: 0.1,
        fill: { color: WHITE },
        line: hairline(),
        shadow: shadow(0.07),
        objectName: `${name} card`,
      });
      await disc(s, { x: x + 0.2, y: y + 0.2, d: 0.5, agent, name });
      text(s, name, { x: x + 0.82, y: y + 0.17, w: cw - 0.95, h: 0.56, fontFace: HEAD, fontSize: 15, color: INK, valign: "middle", objectName: `${name} title` });
      text(s, remit, { x: x + 0.2, y: y + 0.82, w: cw - 0.4, h: 0.6, fontSize: 12, color: INK, transparency: 25, objectName: `${name} remit` });
    }

    const rx = 7.2;
    const rw = XR - rx;
    label(s, "THEY DISAGREE, AND THE CHIEF OF STAFF DECIDES", { x: rx, y: TOP, w: rw });
    text(s, "A real conflict from the recorded run, 22 October 2026", { x: rx, y: TOP + 0.28, w: rw, h: 0.26, fontSize: 11, color: INK, transparency: 35, objectName: "Source of the example" });
    const cy = 2.62;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: rx,
      y: cy,
      w: rw,
      h: BOTTOM - cy,
      rectRadius: 0.1,
      fill: { color: WHITE },
      line: hairline(),
      shadow: shadow(0.09),
      objectName: "Conflict card",
    });
    await disc(s, { x: rx + 0.25, y: cy + 0.22, d: 0.34, agent: "marketing", solid: false, name: "Marketing Strategy, in the conflict" });
    text(
      s,
      [
        { text: "Marketing Strategy", options: { bold: true } },
        { text: "  questioned  ", options: { color: INK, transparency: 40 } },
        { text: "Financial Planning", options: { bold: true } },
      ],
      { x: rx + 0.7, y: cy + 0.22, w: rw - 0.95, h: 0.34, fontSize: 13, color: INK, valign: "middle", objectName: "Who questioned whom" }
    );
    text(
      s,
      "“Marketing recommends a $45k–$65k 6-week Executive Launch Pack while Finance wants a $25k 4-week Brand Sprint — these flagship offers conflict on price, scope and timing.”",
      { x: rx + 0.25, y: cy + 0.7, w: rw - 0.5, h: 0.95, fontSize: 13, color: INK, objectName: "The conflict" }
    );
    const dy = cy + 1.72;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: rx + 0.25,
      y: dy,
      w: rw - 0.5,
      h: 1.5,
      rectRadius: 0.07,
      fill: { color: C.accent1, transparency: 89 },
      objectName: "Decision box",
    });
    await disc(s, { x: rx + 0.42, y: dy + 0.16, d: 0.3, agent: "chief", solid: false, name: "Chief of Staff, deciding" });
    label(s, "THE CHIEF OF STAFF'S DECISION", { x: rx + 0.82, y: dy + 0.18, w: 3.5, color: INK });
    text(
      s,
      "“Do not launch a $55k flagship first; instead run a $4,000 paid pilot (5–10 business days) to prove demand and cashflow, with a follow-on $12,500 10-day full package as the standard offering …”",
      { x: rx + 0.42, y: dy + 0.52, w: rw - 0.84, h: 0.92, fontSize: 12.5, color: INK, objectName: "The decision" }
    );
    text(s, "Financial Planning revised its report to match. All eight conflicts in the run were settled in one call, in 25\u00A0seconds.", {
      x: rx + 0.25,
      y: dy + 1.6,
      w: rw - 0.5,
      h: 0.5,
      fontSize: 11.5,
      color: INK,
      transparency: 30,
      objectName: "What happened next",
    });
    nav(s, 4);
    more(s, "4.1 and 4.5");
    s.addNotes(
      "The team is five agents on one model, each with its own remit and point of view. The Chief of Staff leads: it works out the decision the founder faces, delegates, reviews every report, settles conflicts and writes the strategy. The four specialists each stay in their own lane: marketing, finance, technical feasibility, and risk and compliance.\n\n" +
        "What makes it a team is that they disagree. On the right is a real conflict from our recorded run: Marketing wanted a large flagship package, Finance a smaller sprint. The Chief of Staff decided on a paid pilot with a follow-on package, and Finance revised its report to match. In that run the cross-check raised eight conflicts, and all eight were settled in one call."
    );
  }

  // 5 · The workflow ------------------------------------------------------
  {
    const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "The team and its workflow" });
    heading(s, "HOW IT WORKS", "Plan, act, check, with every loop bounded");
    // The nine steps of the How it works page (frontend/src/lib/how.ts).
    const steps = [
      { key: "Brief", who: "You", makes: "brief, context", agent: "primary", icon: "user", build: 0 },
      { key: "Prepare", who: "Chief of Staff, on the web", makes: "facts [n], questions", agent: "chief", icon: "search", build: 0, optional: true },
      { key: "Plan", who: "Chief of Staff", makes: "objective, tasks", agent: "chief", icon: "compass", build: 0 },
      { key: "Research", who: "FRED; Azure OpenAI or Tavily", makes: "figures, reports, competitors", agent: "research", icon: "globe", build: 1, optional: true },
      { key: "Reports", who: "4 specialists at once", makes: "four reports", build: 1 },
      { key: "Review", who: "Chief of Staff", makes: "scores, revisions", agent: "chief", icon: "scale", build: 2 },
      { key: "Cross-check", who: "The specialists", makes: "conflicts", agent: "primary", icon: "swap", build: 3 },
      { key: "Resolve", who: "Chief of Staff", makes: "decisions", agent: "chief", icon: "gavel", build: 3 },
      { key: "Strategy", who: "Chief of Staff, then you", makes: "memo, report, PDF", agent: "chief", icon: "document", build: 4 },
    ];
    const slot = CW / steps.length;
    const d = 0.74;
    const cyMid = 2.05 + d / 2;
    const centre = (i) => X0 + slot * (i + 0.5);
    const edges = []; // [left, right] of each step's mark, for the arrows
    const arrowLine = () => ({ color: INK, transparency: 50, width: 1.25, endArrowType: "triangle" });
    for (const [i, st] of steps.entries()) {
      const b = `b${st.build}`;
      const cx = centre(i);
      if (st.key === "Reports") {
        const sd = 0.42;
        const overlap = 0.13;
        const total = 4 * sd - 3 * overlap;
        const x0 = cx - total / 2;
        for (const [j, agent] of ["marketing", "finance", "technical", "risk"].entries()) {
          await disc(s, { x: x0 + j * (sd - overlap), y: cyMid - sd / 2, d: sd, agent, name: `${b}: Reports, ${AGENT[agent].name}` });
        }
        edges.push([x0, x0 + total]);
      } else if (st.agent === "primary") {
        s.addShape(pres.shapes.OVAL, {
          x: cx - d / 2,
          y: 2.05,
          w: d,
          h: d,
          fill: { color: WHITE },
          line: { color: NAVY, width: 1.5 },
          objectName: `${b}: ${st.key} circle`,
        });
        s.addImage({
          data: await icon(st.icon, "163C6B"),
          x: cx - d * 0.27,
          y: cyMid - d * 0.27,
          w: d * 0.54,
          h: d * 0.54,
          altText: `${st.key} icon`,
          objectName: `${b}: ${st.key} icon`,
        });
        edges.push([cx - d / 2, cx + d / 2]);
      } else {
        await disc(s, { x: cx - d / 2, y: 2.05, d, agent: st.agent, iconName: st.icon, name: `${b}: ${st.key}`, dashed: st.optional, solid: !st.optional });
        edges.push([cx - d / 2, cx + d / 2]);
      }
      text(s, st.key, { x: cx - slot / 2, y: 2.9, w: slot, h: 0.32, fontFace: HEAD, fontSize: 15, color: INK, align: "center", objectName: `${b}: ${st.key} title` });
      text(s, st.who, {
        x: cx - slot / 2 + 0.04,
        y: 3.23,
        w: slot - 0.08,
        h: 0.44,
        fontSize: 10.5,
        color: INK,
        transparency: 30,
        align: "center",
        objectName: `${b}: ${st.key} who`,
      });
      text(s, st.makes, { x: cx - slot / 2 + 0.04, y: 3.69, w: slot - 0.08, h: 0.4, fontSize: 10, color: NAVY, align: "center", objectName: `${b}: ${st.key} makes` });
    }
    for (let i = 0; i < steps.length - 1; i++) {
      const x1 = edges[i][1] + 0.07;
      const x2 = edges[i + 1][0] - 0.07;
      s.addShape(pres.shapes.LINE, { x: x1, y: cyMid, w: x2 - x1, h: 0, line: arrowLine(), objectName: `b${steps[i + 1].build}: arrow to ${steps[i + 1].key}` });
    }
    // The two loops back to the reports, each allowed once.
    const loop = (from, to, low, build, name) => {
      const top = 4.15;
      const line = () => ({ color: C.accent1, width: 1.5 });
      s.addShape(pres.shapes.LINE, { x: from, y: top, w: 0, h: low - top, line: line(), objectName: `b${build}: ${name} down` });
      s.addShape(pres.shapes.LINE, { x: to, y: low, w: from - to, h: 0, line: line(), objectName: `b${build}: ${name} across` });
      s.addShape(pres.shapes.LINE, { x: to, y: top, w: 0, h: low - top, flipV: true, line: { ...line(), endArrowType: "triangle" }, objectName: `b${build}: ${name} up` });
    };
    loop(centre(5), centre(4) + 0.28, 4.5, 2, "Rewrite loop");
    text(
      s,
      [
        { text: "Below 4 of 5: rewritten once", options: { bold: true, fontSize: 11, color: INK, breakLine: true } },
        { text: "MAX_ITERATIONS = 1", options: { fontFace: MONO, fontSize: 10, color: C.accent1 } },
      ],
      { x: centre(5) + 0.12, y: 4.2, w: 2.45, h: 0.48, objectName: "b2: Rewrite loop label" }
    );
    loop(centre(7), centre(4) - 0.28, 5.0, 3, "Revision loop");
    text(
      s,
      [
        { text: "After the decisions, the named specialists revise once, then the strategy", options: { bold: true, fontSize: 11, color: INK, breakLine: true } },
        { text: "MAX_CRITIQUE_ROUNDS = 1", options: { fontFace: MONO, fontSize: 10, color: C.accent1 } },
      ],
      { x: (centre(4) - 0.28 + centre(7)) / 2 - 2.9, y: 5.06, w: 5.8, h: 0.48, align: "center", objectName: "b3: Revision loop label" }
    );
    const facts = [
      ["11 nodes, 40 edges", "One LangGraph state machine; 37 of its edges are chosen from the state"],
      ["Four at once", "The assigned specialists work in parallel; the others make no call"],
      ["Bounded loops", "One rewrite per report and one critique round: no runaway agents"],
      ["Kept per session", "A checkpointer saves the state, so a follow-up reruns only what changed"],
    ];
    const fw = (CW - 3 * 0.2) / 4;
    for (const [i, [big, small]] of facts.entries()) {
      const x = X0 + i * (fw + 0.2);
      text(s, big, { x, y: 5.72, w: fw, h: 0.36, fontFace: HEAD, fontSize: 19, color: NAVY, objectName: `b4: Fact ${i + 1}` });
      text(s, small, { x, y: 6.09, w: fw - 0.1, h: 0.5, fontSize: 11, color: INK, transparency: 30, objectName: `b4: Fact ${i + 1}, detail` });
    }
    text(s, "Dashed: optional steps", { x: XR - 3, y: 1.67, w: 3, h: 0.24, align: "right", fontSize: 9.5, color: INK, transparency: 45, objectName: "Legend" });
    nav(s, 5);
    more(s, "4.2 to 4.6");
    s.addNotes(
      "This is the workflow, as the app's How it works page shows it; each click adds the next steps.\n\n" +
        "The founder writes a brief. The Chief of Staff can research it on the web first and ask the founder questions, then plans: it states the decision and gives each specialist it needs one task.\n\n" +
        "Click. Research and official figures are looked up at the same time, then the assigned specialists write their reports in parallel.\n\n" +
        "Click. The Chief of Staff scores each report from 1 to 5; anything below 4 goes back with feedback and is rewritten, once.\n\n" +
        "Click. The specialists cross-check each other's reports for real contradictions, and the Chief of Staff settles all of them in one call, naming who must revise. Those specialists revise once, and their reports go straight on to the strategy.\n\n" +
        "Click. Finally the Chief of Staff writes one strategy. All of this is one LangGraph state machine, 11 nodes and 40 edges, and every loop has a hard limit, so the agents cannot run away."
    );
  }

  // 6 · Watch it work -----------------------------------------------------
  {
    const s = pres.addSlide({ masterName: "CONTENT_DARK", sectionTitle: "The team and its workflow" });
    heading(s, "LIVE", "Watch the team work, live, on the graph it runs");
    framed(s, img.live, {
      x: X0,
      y: TOP,
      w: 8.3,
      name: "The live graph",
      alt: "The live graph 44 seconds into the recorded run: Marketing and Technical are writing, Finance and Risk have finished, and the steps are listed on the right",
      dark: true,
    });
    const stats = [
      ["2:30", "for a full evaluation, plan to strategy"],
      ["24 calls", "to the model, about 101k tokens in all"],
      ["91.6 s", "for its follow-up: 11 calls, as only Finance and Marketing rerun"],
      ["Every step", "streamed to the browser as it happens, and timed in the Monitor"],
    ];
    for (const [i, [big, small]] of stats.entries()) {
      const y = TOP + i * 1.17;
      text(s, big, { x: 9.3, y, w: XR - 9.3, h: 0.56, fontFace: HEAD, fontSize: 32, color: WHITE, objectName: `Stat ${i + 1}` });
      text(s, small, { x: 9.3, y: y + 0.56, w: XR - 9.3, h: 0.5, fontSize: 12, color: PAPER, transparency: 20, objectName: `Stat ${i + 1}, detail` });
    }
    nav(s, 6, true);
    more(s, "4.7 and 7.1", true);
    s.addNotes(
      "This is the team at work in the real app. The Live graph button opens the graph LangGraph actually runs, drawn by Mermaid from the compiled graph, and lights up each node and edge from the stream of steps as they happen. Here, 44 seconds in, Marketing and Technical are still writing while Finance and Risk have finished.\n\n" +
        "Our recorded run, on 22 October on Azure OpenAI gpt-5-mini, took two and a half minutes from plan to strategy, with 24 model calls. Its follow-up, refining the pricing, took about a minute and a half and 11 calls, because only Finance and Marketing had to work again; Technical and Risk kept their reports."
    );
  }

  // 7 · Grounded in evidence ---------------------------------------------
  pres.addSection({ title: "Evidence and safety" });
  {
    const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Evidence and safety" });
    heading(s, "EVIDENCE", "Grounded in evidence, with every claim cited");
    const rows = [
      ["Research the brief, then ask", "The Chief of Staff searches the web, keeps up to eight cited facts, and asks up to three questions only the founder can answer.", "chief", "search"],
      ["Deep research, per specialist", "A cited report for each specialist's area, and profiles of up to three competitors, from Azure OpenAI's Bing search or Tavily.", "research", "globe"],
      ["Official figures, through MCP", "The app's own MCP server reads FRED; code works out each series' latest value and its change over the year.", "finance", "chart"],
      ["The founder's own documents", "PDF, Word, PowerPoint, Excel and more, split into passages; BM25 gives each agent the passages that bear on its work.", "marketing", "paperclip"],
    ];
    for (const [i, [title, body, agent, iconName]] of rows.entries()) {
      const y = TOP + i * 0.95;
      await disc(s, { x: X0, y: y + 0.02, d: 0.52, agent, iconName, name: title });
      text(s, title, { x: X0 + 0.72, y, w: 5.3, h: 0.32, fontSize: 15, bold: true, color: INK, objectName: `Source: ${title}` });
      text(s, body, { x: X0 + 0.72, y: y + 0.33, w: 5.3, h: 0.6, fontSize: 12, color: INK, transparency: 28, objectName: `Source: ${title}, detail` });
    }
    const fh = framed(s, img.fred, {
      x: 7.0,
      y: TOP,
      w: XR - 7.0,
      name: "Official figures from FRED",
      alt: "The Research tab of the recorded run: official figures from FRED, such as the 10-year Treasury yield at 5.12%, each with its latest value and change over the year",
    });
    text(s, "The recorded run's figures, as the specialists read them", {
      x: 7.0,
      y: TOP + fh + 0.08,
      w: XR - 7.0,
      h: 0.26,
      fontSize: 10.5,
      italic: true,
      color: INK,
      transparency: 40,
      objectName: "Screenshot caption",
    });
    label(s, "FIVE KINDS OF CITATION, ONE LOOK", { x: X0, y: 5.86, w: 5 });
    const chips = [
      ["[4]", "web page", "primary"],
      ["[FRED · DGS10]", "figure", "research"],
      ["[D1 · page 3]", "upload", "primary"],
      ["[R1 · Launch Strategy]", "report", "chief"],
      ["[finance]", "agent", "finance"],
    ];
    let cx = X0;
    for (const [tag, kind, agent] of chips) {
      const words = `${tag}  ${kind}`;
      const w = words.length * 0.074 + 0.3;
      text(s, [{ text: tag, options: { bold: true } }, { text: `  ${kind}`, options: { color: INK, transparency: 30 } }], {
        shape: pres.shapes.ROUNDED_RECTANGLE,
        x: cx,
        y: 6.17,
        w,
        h: 0.36,
        rectRadius: 0.18,
        fill: { color: AGENT[agent].scheme, transparency: 86 },
        fontSize: 11,
        color: INK,
        align: "center",
        valign: "middle",
        objectName: `Citation: ${words}`,
      });
      cx += w + 0.12;
    }
    nav(s, 7);
    more(s, "part 5, grounding the work");
    s.addNotes(
      "A strategy is only as good as its evidence, so the team works from four kinds of it.\n\n" +
        "Before the team starts, the Chief of Staff searches the web, keeps the facts that matter with their sources, and asks the founder only what the founder alone knows, such as budget and traction. With deep research on, each specialist gets a cited report on its area, and up to three competitors are profiled. Our own MCP server reads official figures from the Federal Reserve's FRED, and code does the arithmetic. And the founder can upload their own files, which are split into passages and ranked for each agent.\n\n" +
        "Whatever the source, every claim carries a citation, and the page shows each one the same way."
    );
  }

  // 8 · Safe by design ---------------------------------------------------
  {
    const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Evidence and safety" });
    heading(s, "SAFETY", "Safe by design: typed, fenced and bounded");
    const lw = 5.45;
    text(s, "17 of 22", { x: X0, y: TOP - 0.05, w: lw, h: 0.85, fontFace: HEAD, fontSize: 52, color: NAVY, objectName: "Typed prompts" });
    text(s, "prompts answer as a Pydantic model that the LLM was constrained to produce: every plan, review, conflict, decision, look-up, proposal part, answer and score.", {
      x: X0,
      y: 2.82,
      w: lw,
      h: 0.78,
      fontSize: 13,
      color: INK,
      objectName: "Typed prompts, detail",
    });
    const code = [
      ["# chief/plan: what the client sends", 40],
      ["response_format: json_schema, strict: true", 0],
      ['specialist: "marketing" | "finance"', 0],
      ['          | "technical" | "risk"', 0],
      ["", 0],
      ['reply: {"specialist": "sales"}', 0],
      ["-> rejected by Pydantic: Input should be", "risk"],
      ["   'marketing', 'finance', 'technical' or 'risk'", "risk"],
    ];
    text(
      s,
      code.map(([line, tone], i) => ({
        text: line || " ",
        options: {
          breakLine: i < code.length - 1,
          color: tone === "risk" ? C.accent5 : PAPER,
          transparency: tone === 40 ? 40 : 0,
        },
      })),
      {
        shape: pres.shapes.ROUNDED_RECTANGLE,
        x: X0,
        y: 3.7,
        w: lw,
        h: 1.95,
        rectRadius: 0.08,
        fill: { color: INK },
        fontFace: MONO,
        fontSize: 11,
        margin: [14, 10, 10, 12],
        objectName: "Checked on the wire",
      }
    );
    text(s, "The other 5 are prose by design: the four reports and the strategy, scored by the review and the judge. The audit, call by call, and its two open gaps with their fixes are in the deep dive.", {
      x: X0,
      y: 5.78,
      w: lw,
      h: 0.8,
      fontSize: 11.5,
      color: INK,
      transparency: 30,
      objectName: "The rest of the audit",
    });

    const rx = 6.4;
    const cw = (XR - rx - 0.2) / 2;
    const ch = (BOTTOM - TOP - 0.2) / 2;
    const cards = [
      ["Data, never orders", "The brief, web pages and uploads are fenced as data and scanned. In the recorded run a web page hid words in invisible characters; it was cut out and the founder was told.", "risk", "shield"],
      ["No runaway agents", "One rewrite per report, one critique round, a time limit on every model call, at most four runs at once and 30 an hour per caller.", "chief", "clock"],
      ["Every request checked", "Each request is a Pydantic model with limits: a brief of up to 8,000 characters, 10 answers, 50 sources. Anything else is refused with 422 before a model is called.", "technical", "check"],
      ["No key in the browser", "The Next.js server adds the API key and forwards only the routes the pages use. Bodies are capped at 1\u00A0MB (an upload at 10\u00A0MB), requests at 300 a minute.", "primary", "window"],
    ];
    for (const [i, [title, body, agent, iconName]] of cards.entries()) {
      const x = rx + (i % 2) * (cw + 0.2);
      const y = TOP + Math.floor(i / 2) * (ch + 0.2);
      s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: cw, h: ch, rectRadius: 0.1, fill: { color: WHITE }, line: hairline(), shadow: shadow(0.07), objectName: `${title} card` });
      await disc(s, { x: x + 0.22, y: y + 0.22, d: 0.48, agent, iconName, solid: false, name: title });
      text(s, title, { x: x + 0.22, y: y + 0.82, w: cw - 0.44, h: 0.32, fontSize: 14, bold: true, color: INK, objectName: `${title} title` });
      text(s, body, { x: x + 0.22, y: y + 1.14, w: cw - 0.4, h: ch - 1.24, fontSize: 11.5, color: INK, transparency: 25, objectName: `${title} detail` });
    }
    nav(s, 8);
    more(s, "part 6, correctness and safety");
    s.addNotes(
      "We asked ourselves whether Pydantic guards every model call, and audited all of them. Seventeen of the app's 22 prompts answer as a Pydantic model: every plan, review, conflict, decision, look-up, proposal part, answer and score. The schema is sent to Azure OpenAI in strict mode, so the model can only produce that shape, and the reply is validated again. We checked this on the wire: a reply naming a fifth specialist, sales, is rejected. The other five prompts, the four reports and the strategy, are prose by design, and are scored by the review and an optional judge. The deep dive lists two gaps the audit found and how to close them.\n\n" +
        "Around that: everything the founder or the web supplies is fenced as material, never orders; in our run a web page tried to hide words in invisible characters and was cut out. Every loop and call is bounded, every request is validated before a model sees it, and the API key never reaches the browser."
    );
  }

  // 9 · Strategy to proposal ----------------------------------------------
  pres.addSection({ title: "The product in production" });
  {
    const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "The product in production" });
    heading(s, "THE DOCUMENT", "From a strategy to an investment proposal");
    const lw = 5.2;
    label(s, "THREE WAVES, SO THE FIGURES AGREE", { x: X0, y: TOP, w: lw });
    const waves = [
      [["marketing", "Marketing"], ["technical", "Technical"], ["risk", "Risk"], "write their parts at the same time"],
      [["finance", "Finance"], "writes the financial plan to cover the market and technical costs"],
      [["chief", "Chief of Staff"], "writes the executive summary, the KPIs and the verdict"],
    ];
    for (const [i, wave] of waves.entries()) {
      const y = 2.3 + i * 0.72;
      text(s, String(i + 1), {
        shape: pres.shapes.OVAL,
        x: X0,
        y,
        w: 0.36,
        h: 0.36,
        fill: { color: PAPER },
        line: { color: NAVY, width: 1.25 },
        fontFace: HEAD,
        fontSize: 13,
        color: NAVY,
        align: "center",
        valign: "middle",
        objectName: `Wave ${i + 1}`,
      });
      if (i < waves.length - 1) {
        s.addShape(pres.shapes.LINE, { x: X0 + 0.18, y: y + 0.41, w: 0, h: 0.26, line: { color: NAVY, width: 1, endArrowType: "triangle" }, objectName: `Wave ${i + 1} to ${i + 2}` });
      }
      let x = X0 + 0.52;
      for (const part of wave) {
        if (typeof part === "string") {
          text(s, part, { x: X0 + 0.52, y: y + 0.38, w: lw - 0.52, h: 0.26, fontSize: 11.5, color: INK, transparency: 30, objectName: `Wave ${i + 1}, what it does` });
          continue;
        }
        const [agent, name] = part;
        const w = name.length * 0.085 + 0.52;
        s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h: 0.36, rectRadius: 0.18, fill: { color: AGENT[agent].scheme, transparency: 84 }, objectName: `${name} chip` });
        s.addImage({ data: await icon(AGENT[agent].icon, AGENT[agent].deep), x: x + 0.1, y: y + 0.07, w: 0.22, h: 0.22, altText: `${name} icon`, objectName: `${name} chip icon` });
        text(s, name, { x: x + 0.38, y, w: w - 0.42, h: 0.36, fontSize: 11.5, bold: true, color: INK, valign: "middle", objectName: `${name} chip name` });
        x += w + 0.1;
      }
    }
    text(
      s,
      [
        { text: "Money in code, not prose", options: { bold: true, fontSize: 14.5, color: INK, breakLine: true } },
        {
          text: "Finance gives the drivers; code works out revenue, costs, NPV, IRR, payback and break-even, and checks them. The PDF, 26 pages in the recorded run, is drawn on the server.",
          options: { fontSize: 12, color: INK, transparency: 25, paraSpaceBefore: 4 },
        },
      ],
      { x: X0, y: 4.45, w: lw, h: 0.95, objectName: "Money in code" }
    );
    label(s, "DOCUMENT CONTROL, WITH DRAFTS TO ACCEPT", { x: X0, y: 5.5, w: lw });
    const controls = ["Changes marked", "The last 30 versions", "22 currencies, ECB rate", "Units", "Find, replace, redact"];
    let x = X0;
    let y = 5.82;
    for (const words of controls) {
      const w = words.length * 0.073 + 0.32;
      if (x + w > X0 + lw) {
        x = X0;
        y += 0.42;
      }
      text(s, words, {
        shape: pres.shapes.ROUNDED_RECTANGLE,
        x,
        y,
        w,
        h: 0.34,
        rectRadius: 0.17,
        fill: { color: WHITE },
        line: hairline(),
        fontSize: 10.5,
        color: INK,
        align: "center",
        valign: "middle",
        objectName: `Control: ${words}`,
      });
      x += w + 0.1;
    }
    const fx = 6.15;
    framed(s, img.studio, {
      x: fx,
      y: TOP,
      w: XR - fx,
      name: "The document studio",
      alt: "The document studio: the Revise tool, with each part of the proposal and its agent, beside the 26-page PDF",
    });
    nav(s, 9);
    more(s, "7.2 and 7.3");
    s.addNotes(
      "On demand, the agents write the strategy up as an investment proposal, each part by the agent who owns it. They work in three waves so that the figures agree: Marketing, Technical and Risk first, then Finance, with the market and technical parts in front of it and their costs summed, then the Chief of Staff's summary, KPIs and verdict.\n\n" +
        "The money is never left to the model's arithmetic. Finance supplies the drivers, and code works out the revenue, costs, NPV, IRR, payback and break-even, and checks them; a failing check sends Finance back once.\n\n" +
        "On the right is the document studio, with the PDF beside its tools. The founder can ask any agent to revise its part, convert the currency at today's European Central Bank rate, change units, find and replace or redact. Every change the team or the tools make comes back as a draft, marked before and after, and nothing is saved until the founder accepts it."
    );
  }

  // 10 · Production --------------------------------------------------------
  {
    const s = pres.addSlide({ masterName: "CONTENT_DARK", sectionTitle: "The product in production" });
    heading(s, "PRODUCTION", "Production-ready, tested and measured");
    const stats = [
      ["578", "automated tests, 398 backend and 180 frontend, with no model calls"],
      ["96.8%", "backend coverage; the frontend's is 96.2% of lines. The gate is 80%"],
      ["34", "live checks against the real model, recorded in the development plan"],
      ["58–64%", "fewer model calls on a follow-up after optimisation, in two scenarios"],
    ];
    const sw = (6.3 - 0.25) / 2;
    for (const [i, [big, small]] of stats.entries()) {
      const x = X0 + (i % 2) * (sw + 0.25);
      const y = TOP + Math.floor(i / 2) * 1.62;
      text(s, big, { x, y, w: sw, h: 0.72, fontFace: HEAD, fontSize: 44, color: WHITE, objectName: `Stat ${i + 1}` });
      text(s, small, { x, y: y + 0.74, w: sw - 0.1, h: 0.72, fontSize: 12, color: PAPER, transparency: 20, objectName: `Stat ${i + 1}, detail` });
    }
    const mx = 7.25;
    const mh = framed(s, img.monitor, {
      x: mx,
      y: TOP,
      w: XR - mx,
      name: "The Monitor",
      alt: "The Monitor: two evaluations, a median of 2:01 to a decision, no server errors, 35 model calls and the time each step takes",
      dark: true,
    });
    text(s, "The Monitor: what the API has done since it started", {
      x: mx,
      y: TOP + mh + 0.1,
      w: XR - mx,
      h: 0.26,
      fontSize: 10.5,
      italic: true,
      color: PAPER,
      transparency: 30,
      objectName: "Monitor caption",
    });
    const stack = ["PostgreSQL", "Docker Compose", "GitLab CI", "Langfuse", "Prometheus", "Structured logs", "Rate limits"];
    let x = X0;
    for (const words of stack) {
      const w = words.length * 0.078 + 0.36;
      text(s, words, {
        shape: pres.shapes.ROUNDED_RECTANGLE,
        x,
        y: 5.33,
        w,
        h: 0.36,
        rectRadius: 0.18,
        fill: { color: NAVY },
        line: { color: PAPER, transparency: 55, width: 0.75 },
        fontSize: 11,
        color: PAPER,
        align: "center",
        valign: "middle",
        objectName: `Stack: ${words}`,
      });
      x += w + 0.12;
    }
    const docs = [
      ["Open the brief and architecture", "02-Project-Brief-Architecture-and-User-Flow.pdf", 3.45],
      ["Open the deep dive", "03-Deep-Dive.pdf", 2.35],
    ];
    x = X0;
    for (const [words, file, w] of docs) {
      text(s, [{ text: words + "   →", options: { bold: true } }], {
        shape: pres.shapes.ROUNDED_RECTANGLE,
        x,
        y: 6.0,
        w,
        h: 0.46,
        rectRadius: 0.23,
        fill: { color: WHITE },
        color: NAVY,
        fontSize: 12,
        align: "center",
        valign: "middle",
        objectName: `${words} button`,
      });
      hotspot(s, { x, y: 6.0, w, h: 0.46, hyperlink: { url: file, tooltip: `${file}, in the same folder as this deck` }, name: words });
      x += w + 0.2;
    }
    text(s, "Built in 36 steps, each reviewable on its own", { x: x + 0.1, y: 6.0, w: XR - x - 0.1, h: 0.46, fontSize: 11, color: PAPER, transparency: 30, valign: "middle", align: "right", objectName: "How it was built" });
    nav(s, 10, true);
    more(s, "part 8, production readiness", true);
    s.addNotes(
      "Finally, it is built to be run, not just demonstrated. Sessions, reports and LangGraph's checkpoints live in PostgreSQL; the stack runs in Docker Compose; GitLab CI tests every push; every model call is traced in Langfuse; the API records what it does for the Monitor on the How it works page and as Prometheus metrics; and it has a key, rate limits and size limits.\n\n" +
        "It is tested: 578 automated tests with fake models, so no credentials and no model calls, covering 96.8% of the backend and 96.2% of the frontend's lines, plus 34 live checks against the real model. And it was optimised and measured: a follow-up now makes 58 to 64% fewer model calls.\n\n" +
        "The other two documents in this folder go further: the brief with the architecture and user flow, and the 44-page deep dive. Thank you."
    );
  }

  await pres.writeFile({ fileName: OUT });
  await finish(OUT);
  console.log(`${path.relative(process.cwd(), OUT)}: ${COUNT} slides`);
}

// ---------------------------------------------------------------- after pptxgenjs

// The click-by-click build of the workflow slide: objects named "b1: …" appear
// on the first click, "b2: …" on the second, and so on; "b0: …" are there from
// the start.
function timing(xml) {
  const groups = new Map();
  for (const m of xml.matchAll(/<p:(sp|pic)>\s*<p:nv(?:Sp|Pic)Pr>\s*<p:cNvPr id="(\d+)" name="b(\d): [^"]*"/g)) {
    const build = Number(m[3]);
    if (build === 0) continue;
    if (!groups.has(build)) groups.set(build, []);
    groups.get(build).push({ id: m[2], kind: m[1] });
  }
  let id = 2;
  const next = () => ++id;
  let clicks = "";
  for (const build of [...groups.keys()].sort((a, b) => a - b)) {
    const outer = next();
    const inner = next();
    let effects = "";
    groups.get(build).forEach((t, i) => {
      const effect = next();
      const set = next();
      const anim = next();
      effects +=
        `<p:par><p:cTn id="${effect}" presetID="10" presetClass="entr" presetSubtype="0" fill="hold"${t.kind === "sp" ? ' grpId="0"' : ""} nodeType="${i === 0 ? "clickEffect" : "withEffect"}">` +
        `<p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst>` +
        `<p:set><p:cBhvr><p:cTn id="${set}" dur="1" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst></p:cTn><p:tgtEl><p:spTgt spid="${t.id}"/></p:tgtEl><p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst></p:cBhvr><p:to><p:strVal val="visible"/></p:to></p:set>` +
        `<p:animEffect transition="in" filter="fade"><p:cBhvr><p:cTn id="${anim}" dur="400"/><p:tgtEl><p:spTgt spid="${t.id}"/></p:tgtEl></p:cBhvr></p:animEffect>` +
        `</p:childTnLst></p:cTn></p:par>`;
    });
    clicks +=
      `<p:par><p:cTn id="${outer}" fill="hold"><p:stCondLst><p:cond delay="indefinite"/></p:stCondLst><p:childTnLst>` +
      `<p:par><p:cTn id="${inner}" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst>${effects}</p:childTnLst></p:cTn></p:par>` +
      `</p:childTnLst></p:cTn></p:par>`;
  }
  if (!clicks) return "";
  const shapes = [...groups.values()].flat().filter((t) => t.kind === "sp");
  const builds = shapes.map((t) => `<p:bldP spid="${t.id}" grpId="0" animBg="1"/>`).join("");
  return (
    `<p:timing><p:tnLst><p:par><p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot"><p:childTnLst>` +
    `<p:seq concurrent="1" nextAc="seek"><p:cTn id="2" dur="indefinite" nodeType="mainSeq"><p:childTnLst>${clicks}</p:childTnLst></p:cTn>` +
    `<p:prevCondLst><p:cond evt="onPrev" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:prevCondLst>` +
    `<p:nextCondLst><p:cond evt="onNext" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:nextCondLst></p:seq>` +
    `</p:childTnLst></p:cTn></p:par></p:tnLst>${builds ? `<p:bldLst>${builds}</p:bldLst>` : ""}</p:timing>`
  );
}

// pptxgenjs writes Office's colours into the theme and has no transitions or
// animations, so those are written into the package here.
async function finish(file) {
  const zip = await JSZip.loadAsync(fs.readFileSync(file));
  const themePart = "ppt/theme/theme1.xml";
  const scheme =
    `<a:clrScheme name="${THEME.name}">` + SLOTS.map((k) => `<a:${k}><a:srgbClr val="${THEME.colors[k]}"/></a:${k}>`).join("") + "</a:clrScheme>";
  const theme = (await zip.file(themePart).async("string"))
    .replace(/<a:clrScheme\b[\s\S]*?<\/a:clrScheme>/, () => scheme)
    .replace(/(<a:(?:theme|fontScheme)\b[^>]*?\bname=")[^"]*"/g, (_, head) => `${head}${THEME.name}"`);
  if (!theme.includes(scheme)) throw new Error(`${themePart} has no colour scheme to replace`);
  zip.file(themePart, theme);

  for (let n = 1; n <= COUNT; n++) {
    const part = `ppt/slides/slide${n}.xml`;
    const xml = await zip.file(part).async("string");
    if (!xml.includes("</p:clrMapOvr>")) throw new Error(`${part} has no colour map to put the transition after`);
    zip.file(part, xml.replace("</p:clrMapOvr>", () => `</p:clrMapOvr><p:transition spd="med"><p:fade/></p:transition>${timing(xml)}`));
  }

  // pptxgenjs writes a slide's notes as one run; give each paragraph its own.
  for (let n = 1; n <= COUNT; n++) {
    const part = `ppt/notesSlides/notesSlide${n}.xml`;
    const xml = await zip.file(part).async("string");
    zip.file(part, xml.replace(/(\r?\n){2}/g, () => '</a:t></a:r></a:p><a:p><a:r><a:rPr lang="en-GB" dirty="0"/><a:t>'));
  }

  // The text is British English, so PowerPoint should check its spelling as such.
  for (const name of Object.keys(zip.files).filter((f) => /^ppt\/.*\.xml$/.test(f))) {
    const xml = await zip.file(name).async("string");
    if (xml.includes('lang="en-US"')) zip.file(name, xml.replace(/lang="en-US"/g, 'lang="en-GB"'));
  }

  // A scheme colour given to a hex-only option comes out as <a:srgbClr val="bg2"/>.
  for (const name of Object.keys(zip.files).filter((f) => f.endsWith(".xml"))) {
    const bad = (await zip.file(name).async("string")).match(/<a:srgbClr val="((?![0-9A-Fa-f]{6}")[^"]*)"/);
    if (bad) throw new Error(`${name} has the colour "${bad[1]}", which is not six hex digits`);
  }
  fs.writeFileSync(file, await zip.generateAsync({ type: "nodebuffer", compression: "DEFLATE" }));
}

await build();
