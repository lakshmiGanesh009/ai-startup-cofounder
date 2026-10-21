// What changed between two versions of a text, word by word, for a draft's
// preview: the lines are matched first, then the words of the lines that
// differ, so a long section with a few changes is quick to compare.

export type Piece = { text: string; kind: "same" | "added" | "removed" };

// The longest common subsequence of two lists, as pairs of indices.
function common<T>(a: T[], b: T[]): [number, number][] {
  const rows = a.length + 1;
  const cols = b.length + 1;
  const table = new Uint32Array(rows * cols);
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      table[i * cols + j] =
        a[i] === b[j] ? table[(i + 1) * cols + j + 1] + 1 : Math.max(table[(i + 1) * cols + j], table[i * cols + j + 1]);
    }
  }
  const pairs: [number, number][] = [];
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      pairs.push([i, j]);
      i++;
      j++;
    } else if (table[(i + 1) * cols + j] >= table[i * cols + j + 1]) i++;
    else j++;
  }
  return pairs;
}

function push(pieces: Piece[], text: string, kind: Piece["kind"]) {
  if (!text) return;
  const last = pieces.at(-1);
  if (last && last.kind === kind) last.text += text;
  else pieces.push({ text, kind });
}

// The words of `before` and `after`, each kept, removed or added.
function words(before: string, after: string, pieces: Piece[]) {
  const a = before.split(/(\s+)/);
  const b = after.split(/(\s+)/);
  // Too long to compare word by word: the whole as removed, then added.
  if (a.length * b.length > 4_000_000) {
    push(pieces, before, "removed");
    push(pieces, after, "added");
    return;
  }
  let i = 0;
  let j = 0;
  for (const [x, y] of common(a, b)) {
    push(pieces, a.slice(i, x).join(""), "removed");
    push(pieces, b.slice(j, y).join(""), "added");
    push(pieces, a[x], "same");
    i = x + 1;
    j = y + 1;
  }
  push(pieces, a.slice(i).join(""), "removed");
  push(pieces, b.slice(j).join(""), "added");
}

export function diffWords(before: string, after: string): Piece[] {
  const a = before.split("\n");
  const b = after.split("\n");
  const pieces: Piece[] = [];
  let i = 0;
  let j = 0;
  const flush = (x: number, y: number) => {
    const gone = a.slice(i, x).join("\n");
    const come = b.slice(j, y).join("\n");
    if (gone || come) words(gone, come, pieces);
    if (x > i || y > j) push(pieces, "\n", "same");
  };
  for (const [x, y] of common(a, b)) {
    flush(x, y);
    push(pieces, a[x] + (x < a.length - 1 ? "\n" : ""), "same");
    i = x + 1;
    j = y + 1;
  }
  if (i < a.length || j < b.length) {
    const gone = a.slice(i).join("\n");
    const come = b.slice(j).join("\n");
    words(gone, come, pieces);
  }
  return pieces;
}
