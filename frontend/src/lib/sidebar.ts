// Whether the sidebar is folded into a narrow rail of icons on a large screen:
// the founder's choice, which this browser remembers. The choice is a
// data-sidebar attribute on <html>, which globals.css follows (the rail
// variant, and --sidebar-width); SIDEBAR_SCRIPT sets it before the page first
// paints, so a folded sidebar shows folded at once. No React here, as in
// lib/theme.ts.

const KEY = "cofounder-sidebar";
const CHANGED = "cofounder-sidebar-change";

export const SIDEBAR_SCRIPT = `try{if(localStorage.getItem("${KEY}")==="rail")document.documentElement.dataset.sidebar="rail"}catch(e){}`;

export function isFolded(): boolean {
  return document.documentElement.dataset.sidebar === "rail";
}

export function setFolded(folded: boolean) {
  try {
    if (folded) window.localStorage.setItem(KEY, "rail");
    else window.localStorage.removeItem(KEY);
  } catch {
    // A browser that keeps nothing still folds it, for this page.
  }
  if (folded) document.documentElement.dataset.sidebar = "rail";
  else delete document.documentElement.dataset.sidebar;
  window.dispatchEvent(new Event(CHANGED));
}

// Calls `change` when the sidebar folds or unfolds.
export function subscribe(change: () => void): () => void {
  window.addEventListener(CHANGED, change);
  return () => window.removeEventListener(CHANGED, change);
}
