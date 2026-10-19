"use client";

// The backend as the whole app sees it: whether it answers, and the reasoning
// efforts every request sends. The efforts start at the backend's configured
// defaults and are remembered in this browser once changed.

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { type Effort, EFFORTS, getHealth, type Health, type Reasoning } from "@/lib/api";

const STORAGE_KEY = "cofounder-reasoning";

type Role = "specialist" | "chief";

export type BackendState = {
  status: "checking" | "up" | "down";
  error: string | null;
  health: Health | null;
  // The efforts to send, or null when the provider takes none (only Azure does).
  reasoning: Reasoning | null;
  setEffort: (role: Role, effort: Effort) => void;
};

const BackendContext = createContext<BackendState | null>(null);

function remembered(): Reasoning {
  try {
    return JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "{}") as Reasoning;
  } catch {
    return {};
  }
}

function valid(effort: unknown): effort is Effort {
  return EFFORTS.includes(effort as Effort);
}

export function BackendProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<BackendState["status"]>("checking");
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [chosen, setChosen] = useState<Reasoning>({});

  useEffect(() => {
    let cancelled = false;
    getHealth()
      .then((answer) => {
        if (cancelled) return;
        const saved = remembered();
        const pick = (role: Role): Effort => {
          const mine = saved[role];
          if (valid(mine)) return mine;
          const configured = answer.reasoning[role];
          return valid(configured) ? configured : "minimal";
        };
        setHealth(answer);
        setChosen({ specialist: pick("specialist"), chief: pick("chief") });
        setStatus("up");
      })
      .catch((reason: Error) => {
        if (cancelled) return;
        setError(reason.message);
        setStatus("down");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const setEffort = useCallback((role: Role, effort: Effort) => {
    setChosen((current) => {
      const next = { ...current, [role]: effort };
      try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      } catch {
        // Storage can be unavailable (a private window); the choice still applies.
      }
      return next;
    });
  }, []);

  const value = useMemo<BackendState>(
    () => ({
      status,
      error,
      health,
      reasoning: health?.reasoning.adjustable ? chosen : null,
      setEffort,
    }),
    [status, error, health, chosen, setEffort],
  );

  return <BackendContext value={value}>{children}</BackendContext>;
}

export function useBackend(): BackendState {
  const state = useContext(BackendContext);
  if (!state) throw new Error("useBackend must be used inside <BackendProvider>.");
  return state;
}
