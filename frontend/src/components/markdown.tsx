// The agents' markdown, rendered safely: raw HTML in it is shown as text, and
// figures they marked as assumptions are highlighted.

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const ASSUMPTION = /\((?:assumption|assumed|estimate|estimated)s?\)/gi;

type Node = { type: string; value?: string; children?: Node[]; data?: Record<string, unknown> };

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

export function Markdown({ children }: { children: string }) {
  return (
    <div className="prose prose-sm prose-zinc max-w-none dark:prose-invert prose-headings:font-semibold prose-table:text-sm">
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkAssumptions]}>{children}</ReactMarkdown>
    </div>
  );
}
