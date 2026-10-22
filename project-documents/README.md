# Project documents

Four documents about the AI Startup Co-Founder Team, for the capstone review and for anyone new to the project.

| File | What it is |
| --- | --- |
| [01-Project-Highlights.pptx](01-Project-Highlights.pptx) | Ten slides on the project's highlights, with speaker notes. In Slide Show, the contents slide's cards are links, every slide has numbered links along the bottom, the workflow slide builds up click by click, and the last slide opens the two PDFs. |
| [02-Project-Brief-Architecture-and-User-Flow.pdf](02-Project-Brief-Architecture-and-User-Flow.pdf) | 7 A4 pages: the capstone brief, word for word from the top of the repository's README.md, then the system architecture, the agent workflow and the founder's journey through the app. |
| [03-Deep-Dive.pdf](03-Deep-Dive.pdf) | 44 pages, presentation style: how the whole project works, the technologies the brief named and those added beyond it, the Pydantic audit of every model call (part 6), production readiness, and the design trade-offs. Its contents page and bookmarks link to every section. |
| [04-Presenter-Readiness.pdf](04-Presenter-Readiness.pdf) | 8 pages for the presenters: likely questions with short answers, how the project was built and verified, a sign-off checklist for Steps 31 to 35, what is verified before it reaches the LLM, then, in pictures, how the technologies work together, one evaluation traced through the stack, every technology on a card, and the numbers to remember. |

The figures in them come from the main branch on 22 October 2026: the code, both test suites (run that day) and a recorded run of the app on Azure OpenAI gpt-5-mini. The screenshots are from that run.

The deck uses Georgia and Arial, which come with PowerPoint. Its links and builds work in PowerPoint's Slide Show; other viewers show the slides but may ignore them.

## Rebuilding them

The documents are built from `source/`, so a change to the project can be carried into them.

Needs Node.js 20 or later and Google Chrome. Chrome is expected at the usual macOS path; elsewhere, set `CHROME_PATH` to its executable.

```bash
cd project-documents/source
npm install
npm run build        # the PDFs, then the deck
npm run pdfs         # only the PDFs
npm run deck         # only the deck
```

The PDF build stops with a list of problems if a page's content overflows, if text spills out of a diagram's box, or if an image or a font fails to load (`ALLOW_PROBLEMS=1` writes the PDF anyway, to look at).

| In `source/` | What it holds |
| --- | --- |
| `build-pdfs.mjs` | Assembles each PDF's HTML, lays it out in Chrome and prints it; adds the metadata and the bookmarks |
| `pdf/` | The pages: `brief-architecture.html`, `deep-dive.html` with its parts in `dd/`, the shared `theme.css`, and the diagrams in `diagrams/` |
| `deck/deck.mjs` | The deck, written with pptxgenjs, then given the app's colours, the transitions and the builds |
| `assets/` | The screenshots, the fonts (Newsreader and Geist, under the SIL Open Font License, licences beside them) and the app's icons |
| `extract-icons.mjs` | `npm run icons` copies the icons again from `frontend/src/components/ui/icons.tsx` |

The brief is not copied into the HTML: each build renders it from README.md, everything above its first `---` rule, so document 02 always matches the README.
