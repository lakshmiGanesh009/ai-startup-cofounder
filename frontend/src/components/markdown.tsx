// The agents' markdown, rendered safely: raw HTML in it is shown as text,
// figures they marked as assumptions are highlighted, and what the agents cite
// in square brackets is set as tags: an agent ("[finance]") in its colour, a
// passage of the founder's documents ("[D1 · page 3]") or a whole one ("[R1]")
// naming it, several at once ("[D1 · page 3; finance]") side by side.

import ReactMarkdown, { type Components, type Options } from "react-markdown";
import remarkGfm from "remark-gfm";

import { type DocumentRef, useDocumentNames } from "@/components/documents";
import { Passage, usePassages } from "@/components/reports/passages";
import { AGENTS, type AgentKey } from "@/lib/agents";

const ASSUMPTION = /\((?:assumption|assumed|estimate|estimated)s?\)/gi;
const CITED = /\[([^[\]\n]{1,240})\]/g;
const AGENT_CITED = /^(marketing|finance|technical|risk|research|chief(?: of staff)?)$/i;
const DOCUMENT_CITED = /^([DR]\d{1,2}(?:–[DR]?\d{1,2})?)(?: · (.{1,160}))?$/;
// Citations side by side: "D1 · page 3; R1", "D1–D3, R1" (a comma only before a document's mark,
// as one may be inside a place: "sheet Revenue, rows 2–7").
const SEPARATOR = /;\s*|,\s*(?=[DR]\d)/;

type Node = { type: string; value?: string; depth?: number; children?: Node[]; data?: Record<string, unknown> };

function textOf(node: Node): string {
  return node.value ?? (node.children ?? []).map(textOf).join("");
}

function trimColon(node: Node) {
  const last = node.children?.at(-1);
  if (last?.type === "text" && last.value) last.value = last.value.replace(/\s*:\s*$/, "");
  else if (last) trimColon(last);
}

// A remark plugin for the agents' section labels: a short line on its own
// before a list or table ("Key facts driving the decision", "**Next steps:**")
// is a heading in all but syntax, so it is set as one: at `level`, or a level
// below the document's own headings.
function remarkLabels({ level }: { level: number }) {
  return (tree: Node) => {
    const blocks = tree.children ?? [];
    const levels = blocks.filter((node) => node.type === "heading").map((node) => (node.depth ?? 2) + 1);
    const depth = Math.min(4, Math.max(level, ...levels));
    blocks.forEach((node, index) => {
      const next = blocks[index + 1];
      if (node.type !== "paragraph" || !next || (next.type !== "list" && next.type !== "table")) return;
      const children = node.children ?? [];
      const bold = children.length === 1 && children[0].type === "strong";
      const text = textOf(node).trim();
      if (!text || text.length > 80 || text.includes("\n")) return;
      // A bare label has no closing punctuation; a bold one may end in a colon.
      if (bold ? /[.!?;,]$/.test(text) : /[.!?;,:]$/.test(text)) return;
      node.type = "heading";
      node.depth = depth;
      node.children = bold ? children[0].children : children;
      trimColon(node);
    });
  };
}

// A remark plugin that sets each match of `pattern` in the text as the node
// `wrap` makes of it, or leaves it as it is when `wrap` makes none.
function remarkMatches(pattern: RegExp, wrap: (match: RegExpMatchArray) => Node | null) {
  function split(node: Node) {
    if (!node.children) return;
    node.children = node.children.flatMap((child): Node[] => {
      if (child.type !== "text" || !child.value) {
        split(child);
        return [child];
      }
      const parts: Node[] = [];
      let last = 0;
      for (const match of child.value.matchAll(pattern)) {
        const at = match.index ?? 0;
        if (at > last) parts.push({ type: "text", value: child.value.slice(last, at) });
        parts.push(wrap(match) ?? { type: "text", value: match[0] });
        last = at + match[0].length;
      }
      if (!parts.length) return [child];
      if (last < child.value.length) parts.push({ type: "text", value: child.value.slice(last) });
      return parts;
    });
  }
  return () => (tree: Node) => split(tree);
}

// "(assumption)" in the text, as a <mark>.
const remarkAssumptions = remarkMatches(ASSUMPTION, (match) => ({
  type: "assumption",
  data: { hName: "mark", hProperties: { className: "assumption" } },
  children: [{ type: "text", value: match[0] }],
}));

// "[finance]", as a tag in the agent's colour that names it.
function agentTag(cited: string): Node | null {
  const found = cited.match(AGENT_CITED);
  if (!found) return null;
  const key = (found[1].toLowerCase().startsWith("chief") ? "chief" : found[1].toLowerCase()) as AgentKey;
  return {
    type: "citation",
    data: { hName: "span", hProperties: { className: `cite agent-${key}`, title: `From ${AGENTS[key].name}` } },
    children: [{ type: "text", value: AGENTS[key].short }],
  };
}

// "[D1 · page 3]", as a tag: the document's mark, then where in it; its name on hover.
function documentTag(cited: string, names: DocumentRef[]): Node | null {
  const found = cited.match(DOCUMENT_CITED);
  if (!found) return null;
  const [, ref, where] = found;
  const name = names.find((document) => document.ref === ref)?.name ?? `Document ${ref}`;
  return {
    type: "documentMark",
    data: { hName: "span", hProperties: { className: "doc-cite", title: where ? `${name}, ${where}` : name } },
    children: [
      { type: "ref", data: { hName: "b" }, children: [{ type: "text", value: ref }] },
      ...(where ? [{ type: "text", value: where }] : []),
    ],
  };
}

// What the agents cite, as tags; brackets holding nothing they cite stay as written.
function remarkCitations({ names }: { names: DocumentRef[] }) {
  return remarkMatches(CITED, (match) => {
    const parts = match[1].split(SEPARATOR).map((part) => part.trim());
    const tags = parts.map((part) => agentTag(part) ?? documentTag(part, names));
    if (!tags.some(Boolean)) return null;
    return {
      type: "citations",
      data: { hName: "span" },
      children: tags.map((tag, index) => tag ?? { type: "text", value: ` ${parts[index]} ` }),
    };
  })();
}

type Positioned = { position?: { start: { offset?: number }; end: { offset?: number } } };

// A block's own markdown, from where the parser found it in `source`: what
// the API matches when the founder revises or removes it. A list item drops
// its marker.
function slice(source: string, node: Positioned | undefined, item: boolean): string | null {
  const start = node?.position?.start.offset;
  const end = node?.position?.end.offset;
  if (start === undefined || end === undefined) return null;
  const text = source.slice(start, end).trim();
  return item ? text.replace(/^(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s+)?/, "") : text;
}

// The agents' text set as a document (globals.css, `.doc`); `compact` for a
// report shown inside another view, and `labels` to set a whole report's
// section labels as headings (of level 3, or the level given). With `path`
// (where the text is in the report) on a page that handles passages, each
// paragraph and list item can be revised or removed on its own.
export function Markdown({
  children,
  compact = false,
  labels = false,
  path,
}: {
  children: string;
  compact?: boolean;
  labels?: boolean | 3 | 4;
  path?: string;
}) {
  const passages = usePassages();
  const names = useDocumentNames();
  const level = labels === true ? 3 : labels;
  const citations: [typeof remarkCitations, { names: DocumentRef[] }] = [remarkCitations, { names }];
  const plugins: Options["remarkPlugins"] = level
    ? [remarkGfm, [remarkLabels, { level }], remarkAssumptions, citations]
    : [remarkGfm, remarkAssumptions, citations];
  const components: Components | undefined =
    path && passages
      ? {
          p: ({ node, children: inside, ...props }) => {
            const passage = slice(children, node as Positioned, false);
            return passage ? (
              <Passage Tag="p" path={path} passage={passage} {...props}>
                {inside}
              </Passage>
            ) : (
              <p {...props}>{inside}</p>
            );
          },
          li: ({ node, children: inside, ...props }) => {
            const passage = slice(children, node as Positioned, true);
            return passage ? (
              <Passage Tag="li" path={path} passage={passage} {...props}>
                {inside}
              </Passage>
            ) : (
              <li {...props}>{inside}</li>
            );
          },
        }
      : undefined;
  return (
    <div className={compact ? "doc doc-compact" : "doc"}>
      <ReactMarkdown remarkPlugins={plugins} components={components}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
