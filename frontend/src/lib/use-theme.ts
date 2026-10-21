// The theme as React state, for the components that follow it (lib/theme.ts).

import { useSyncExternalStore } from "react";

import { isDark, storedTheme, subscribe, type Theme } from "@/lib/theme";

export function useTheme(): Theme {
  return useSyncExternalStore(subscribe, storedTheme, () => "system");
}

// For what is drawn with fixed colours, such as a diagram, to draw again.
export function useDark(): boolean {
  return useSyncExternalStore(subscribe, isDark, () => false);
}
