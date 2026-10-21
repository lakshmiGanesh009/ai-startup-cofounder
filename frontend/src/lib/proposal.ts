// What the UI says about an investment proposal: its parts, who wrote each,
// and the calculated metrics in words. The wording mirrors proposal.py's
// describe_* functions, so the page and the PDF say the same.

import { createContext, useContext } from "react";

import type { InvestmentMetrics, Level, PartKey } from "@/lib/api";

export const PART_TITLES: Record<PartKey, string> = {
  executive: "Executive Summary and Success Metrics",
  market: "Market & Marketing Strategy",
  technical: "Technical & Operational Architecture",
  risk: "Security, Compliance & Risk",
  financial: "Financial Plan & Projections",
};

export const PART_AGENTS: Record<PartKey, string> = {
  executive: "Chief of Staff",
  market: "Marketing Strategy Agent",
  technical: "Technical Feasibility Agent",
  risk: "Risk & Compliance Agent",
  financial: "Financial Planning Agent",
};

// The agent behind each section of the team's report, by its key.
export const SECTION_AGENTS: Record<string, string> = {
  strategy: "Written by the Chief of Staff",
  decisions: "Decided by the Chief of Staff",
  marketing: "Written by the Marketing Strategy Agent",
  finance: "Written by the Financial Planning Agent",
  technical: "Written by the Technical Feasibility Agent",
  risk: "Written by the Risk & Compliance Agent",
  research: "Found on the web",
  documents: "Your files and earlier reports",
  economic: "Looked up on FRED",
};

// The currencies a document can be in, with the symbol each amount is shown
// with, as currency.py has them; the PDF uses the same.
export const CURRENCIES: Record<string, { symbol: string; name: string }> = {
  USD: { symbol: "$", name: "US dollar" },
  EUR: { symbol: "€", name: "Euro" },
  GBP: { symbol: "£", name: "Pound sterling" },
  INR: { symbol: "₹", name: "Indian rupee" },
  JPY: { symbol: "¥", name: "Japanese yen" },
  CNY: { symbol: "CN¥", name: "Chinese yuan" },
  CAD: { symbol: "CA$", name: "Canadian dollar" },
  AUD: { symbol: "A$", name: "Australian dollar" },
  NZD: { symbol: "NZ$", name: "New Zealand dollar" },
  SGD: { symbol: "S$", name: "Singapore dollar" },
  HKD: { symbol: "HK$", name: "Hong Kong dollar" },
  CHF: { symbol: "CHF ", name: "Swiss franc" },
  SEK: { symbol: "SEK ", name: "Swedish krona" },
  NOK: { symbol: "NOK ", name: "Norwegian krone" },
  DKK: { symbol: "DKK ", name: "Danish krone" },
  PLN: { symbol: "PLN ", name: "Polish złoty" },
  ZAR: { symbol: "R ", name: "South African rand" },
  BRL: { symbol: "R$", name: "Brazilian real" },
  MXN: { symbol: "MX$", name: "Mexican peso" },
  AED: { symbol: "AED ", name: "UAE dirham" },
  SAR: { symbol: "SAR ", name: "Saudi riyal" },
  KRW: { symbol: "₩", name: "South Korean won" },
};

// The currency of the report on show, for every amount inside it.
export const CurrencyContext = createContext("USD");

export function useCurrency(): string {
  return useContext(CurrencyContext);
}

function symbol(code: string): string {
  return CURRENCIES[code]?.symbol ?? `${code} `;
}

// A compact amount: $750, €12k, £1.2M.
export function money(value: number, code = "USD"): string {
  const sign = value < 0 ? "-" : "";
  const size = Math.abs(value);
  for (const [unit, suffix] of [
    [1e9, "B"],
    [1e6, "M"],
    [1e3, "k"],
  ] as const) {
    if (size >= unit) {
      const number = size / unit;
      const text = number >= 100 ? number.toFixed(0) : number.toFixed(1).replace(/\.0$/, "");
      return `${sign}${symbol(code)}${text}${suffix}`;
    }
  }
  return `${sign}${symbol(code)}${Math.round(size).toLocaleString("en-US")}`;
}

// A whole amount: $12,000, -€6,000, CHF 1,500.
export function full(value: number, code = "USD"): string {
  return `${value < 0 ? "-" : ""}${symbol(code)}${Math.round(Math.abs(value)).toLocaleString("en-US")}`;
}

export function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

// One figure as a share of another, with the precision a small share needs:
// "47.9%", "0.04%".
export function share(part: number, whole: number): string {
  const value = (part / whole) * 100;
  const text = value === 0 || value >= 1 ? value.toFixed(1).replace(/\.0$/, "") : String(Number(value.toPrecision(1)));
  return `${text}%`;
}

// The months a roadmap phase spans, counting the project's start as month 1:
// "1–4", or "1" for a phase of a month or less.
export function monthRange(start: number, duration: number): string {
  const end = start + Math.max(Math.ceil(duration), 1) - 1;
  return end > start ? `${start}–${end}` : `${start}`;
}

export function describeIrr(metrics: InvestmentMetrics): [string, string] {
  const { irr, net_cash_flow: flows } = metrics;
  if (irr === null) {
    if (flows.every((cash) => cash >= 0)) return ["None", "nothing is invested up front"];
    if (flows.every((cash) => cash <= 0)) return ["None", "the cash flows never turn positive"];
    return ["None", "not defined for these cash flows"];
  }
  return [irr > 10 ? "> 1,000%" : percent(irr), "on the three-year cash flows"];
}

export function describePayback(metrics: InvestmentMetrics): string {
  const months = metrics.payback_months;
  if (months === null) return "After year 3";
  if (months < 1) return "Under a month";
  const rounded = Math.round(months);
  return `${rounded} month${rounded === 1 ? "" : "s"}`;
}

export function describeBreakEven(metrics: InvestmentMetrics): string {
  const customers = metrics.break_even_customers;
  if (customers === null) return "Never";
  return `${customers.toLocaleString("en-US")} customer${customers === 1 ? "" : "s"}`;
}

export const LEVELS: Level[] = ["Low", "Medium", "High"];
export type Severity = "Low" | "Moderate" | "High" | "Critical";

// A risk's severity, from its probability and impact (as report_charts.py).
export function severity(probability: Level, impact: Level): Severity {
  const names: Severity[] = ["Low", "Low", "Moderate", "High", "Critical"];
  return names[LEVELS.indexOf(probability) + LEVELS.indexOf(impact)];
}
