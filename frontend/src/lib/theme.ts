// Light or dark: the system's choice, unless the founder picks one, which this
// browser remembers. The choice is a data-theme attribute on <html>, which the
// colour tokens in globals.css follow; THEME_SCRIPT sets it before the page
// first paints, so a remembered theme shows without a flash of the other.
// No React here: the root layout, a server component, reads THEME_SCRIPT;
// the hooks are in lib/use-theme.ts.

export type Theme = "system" | "light" | "dark";

export const THEMES: Theme[] = ["system", "light", "dark"];

const KEY = "cofounder-theme";
const CHANGED = "cofounder-theme-change";
const DARK = "(prefers-color-scheme: dark)";

export const THEME_SCRIPT = `try{var t=localStorage.getItem("${KEY}");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}catch(e){}`;

export function storedTheme(): Theme {
  try {
    const theme = window.localStorage.getItem(KEY);
    return theme === "light" || theme === "dark" ? theme : "system";
  } catch {
    return "system";
  }
}

export function setTheme(theme: Theme) {
  try {
    if (theme === "system") window.localStorage.removeItem(KEY);
    else window.localStorage.setItem(KEY, theme);
  } catch {
    // A browser that keeps nothing still switches, for this page.
  }
  if (theme === "system") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = theme;
  window.dispatchEvent(new Event(CHANGED));
}

function systemDark(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia(DARK).matches;
}

// Whether the page is dark now: the founder's choice, else the system's.
export function isDark(): boolean {
  const chosen = document.documentElement.dataset.theme;
  return chosen === "dark" || (chosen !== "light" && systemDark());
}

// Calls `change` when the theme or the system's scheme changes.
export function subscribe(change: () => void): () => void {
  window.addEventListener(CHANGED, change);
  const query = typeof window.matchMedia === "function" ? window.matchMedia(DARK) : null;
  query?.addEventListener("change", change);
  return () => {
    window.removeEventListener(CHANGED, change);
    query?.removeEventListener("change", change);
  };
}
