"use client";

// Light, dark, or as the system says: the founder's choice, remembered in this
// browser (lib/theme.ts).

import { MonitorIcon, MoonIcon, SunIcon } from "@/components/ui/icons";
import { setTheme, type Theme, THEMES } from "@/lib/theme";
import { useTheme } from "@/lib/use-theme";

const CHOICES: Record<Theme, { label: string; Icon: (props: { className?: string }) => React.ReactNode }> = {
  system: { label: "System", Icon: MonitorIcon },
  light: { label: "Light", Icon: SunIcon },
  dark: { label: "Dark", Icon: MoonIcon },
};

export function ThemeSwitch() {
  const theme = useTheme();
  return (
    <fieldset>
      <legend className="kicker">Appearance</legend>
      <div className="mt-3 grid grid-cols-3 gap-0.5 rounded-md border border-rule-strong bg-sunken p-0.5">
        {THEMES.map((choice) => {
          const { label, Icon } = CHOICES[choice];
          return (
            <label
              key={choice}
              className="flex cursor-pointer items-center justify-center gap-1.5 rounded-[5px] px-1 py-1.5 text-[12.5px] whitespace-nowrap text-ink-2 transition-colors hover:text-ink has-[:checked]:bg-surface has-[:checked]:font-medium has-[:checked]:text-ink has-[:checked]:shadow-[0_1px_2px_rgb(0_0_0/0.08)] has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-focus"
            >
              <input
                type="radio"
                name="theme"
                value={choice}
                checked={theme === choice}
                onChange={() => setTheme(choice)}
                className="sr-only"
              />
              <Icon className="size-3.5" />
              {label}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
