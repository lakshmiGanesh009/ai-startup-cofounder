// The agents' markdown, rendered safely: raw HTML in it is shown as text, and
// figures they marked as assumptions are highlighted.

import ReactMarkdown, { type Options } from "react-markdown";
import remarkGfm from "remark-gfm";

const ASSUMPTION = /\((?:assumption|assumed|estimate|estimated)s?\)/gi;

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

// A remark plugin that turns "(assumption)" in the text into a <mark>.
function remarkAssumptions() {
  function split(node: Node) {
    if (!node.children) return;
    node.children = node.children.flatMap((child): Node[] => {
      if (child.type !== "text" || !child.value) {
        split(child);
        return [child];
      }
      const parts: Node[] = [];
      let last = 0;
      for (const match of child.value.matchAll(ASSUMPTION)) {
        const at = match.index ?? 0;
        if (at > last) parts.push({ type: "text", value: child.value.slice(last, at) });
        parts.push({
          type: "assumption",
          data: { hName: "mark", hProperties: { className: "assumption" } },
          children: [{ type: "text", value: match[0] }],
        });
        last = at + match[0].length;
      }
      if (!parts.length) return [child];
      if (last < child.value.length) parts.push({ type: "text", value: child.value.slice(last) });
      return parts;
    });
  }
  return (tree: Node) => split(tree);
}

// The agents' text set as a document (globals.css, `.doc`); `compact` for a
// report shown inside another view, and `labels` to set a whole report's
// section labels as headings (of level 3, or the level given).
export function Markdown({
  children,
  compact = false,
  labels = false,
}: {
  children: string;
  compact?: boolean;
  labels?: boolean | 3 | 4;
}) {
  const level = labels === true ? 3 : labels;
  const plugins: Options["remarkPlugins"] = level
    ? [remarkGfm, [remarkLabels, { level }], remarkAssumptions]
    : [remarkGfm, remarkAssumptions];
  return (
    <div className={compact ? "doc doc-compact" : "doc"}>
      <ReactMarkdown remarkPlugins={plugins}>{children}</ReactMarkdown>
    </div>
  );
}
