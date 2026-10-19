"use client";

// A form for one part of the proposal, built from a description of its fields:
// text, numbers, choices, a market size, or an editable table. The API
// validates what is saved and says what is wrong.

import { useState } from "react";

import type { PartKey } from "@/lib/api";

type Kind = "text" | "long" | "number" | "choice";
export type Column = { key: string; label: string; kind: Kind; options?: readonly string[] };
export type FieldSpec =
  | { key: string; label: string; kind: Kind; options?: readonly string[] }
  | { key: string; label: string; kind: "size" }
  | { key: string; label: string; kind: "table"; columns: Column[] };

const LEVELS = ["Low", "Medium", "High"] as const;

export const PART_FIELDS: Record<PartKey, FieldSpec[]> = {
  executive: [
    { key: "project_name", label: "Project name", kind: "text" },
    { key: "verdict", label: "Verdict", kind: "choice", options: ["Go", "Go with conditions", "Not yet"] },
    { key: "recommendation", label: "Recommendation", kind: "long" },
    { key: "overview", label: "Project overview", kind: "long" },
    { key: "opportunity", label: "The opportunity", kind: "long" },
    { key: "strategic_alignment", label: "Strategic alignment", kind: "long" },
    { key: "financial_case", label: "What the numbers say", kind: "long" },
    {
      key: "kpis",
      label: "Success metrics (KPIs)",
      kind: "table",
      columns: [
        { key: "category", label: "Category", kind: "choice", options: ["Financial", "Technical", "Marketing"] },
        { key: "metric", label: "Metric", kind: "text" },
        { key: "target", label: "Target", kind: "text" },
      ],
    },
  ],
  market: [
    { key: "personas", label: "Buyer personas", kind: "long" },
    { key: "tam", label: "TAM (total addressable market)", kind: "size" },
    { key: "sam", label: "SAM (serviceable addressable market)", kind: "size" },
    { key: "som", label: "SOM (serviceable obtainable market)", kind: "size" },
    {
      key: "competitors",
      label: "Competitors",
      kind: "table",
      columns: [
        { key: "name", label: "Name", kind: "text" },
        { key: "kind", label: "Type", kind: "choice", options: ["Direct", "Indirect"] },
        { key: "market_share", label: "Est. share", kind: "text" },
        { key: "strengths", label: "Strengths", kind: "text" },
        { key: "weaknesses", label: "Weaknesses", kind: "text" },
      ],
    },
    { key: "value_proposition", label: "Value proposition", kind: "long" },
    {
      key: "channels",
      label: "Channels",
      kind: "table",
      columns: [
        { key: "channel", label: "Channel", kind: "text" },
        { key: "approach", label: "How it is used", kind: "text" },
        { key: "monthly_budget_usd", label: "Monthly budget ($)", kind: "number" },
      ],
    },
    { key: "pricing_strategy", label: "Pricing strategy", kind: "long" },
    {
      key: "funnel",
      label: "Sales funnel",
      kind: "table",
      columns: [
        { key: "stage", label: "Stage", kind: "text" },
        { key: "monthly_volume", label: "Monthly volume", kind: "number" },
      ],
    },
  ],
  technical: [
    { key: "infrastructure", label: "Infrastructure", kind: "long" },
    { key: "stack", label: "Technology stack", kind: "long" },
    { key: "scalability", label: "Scalability and performance", kind: "long" },
    {
      key: "roadmap",
      label: "Roadmap",
      kind: "table",
      columns: [
        { key: "name", label: "Phase", kind: "text" },
        { key: "start_month", label: "Start month", kind: "number" },
        { key: "duration_months", label: "Months", kind: "number" },
        { key: "deliverables", label: "Deliverables", kind: "text" },
      ],
    },
    {
      key: "staffing",
      label: "Staffing",
      kind: "table",
      columns: [
        { key: "role", label: "Role", kind: "text" },
        { key: "count", label: "FTE", kind: "number" },
        { key: "timing", label: "When", kind: "text" },
      ],
    },
  ],
  risk: [
    { key: "data_protection", label: "Data protection", kind: "long" },
    { key: "compliance", label: "Compliance", kind: "long" },
    {
      key: "risks",
      label: "Risks",
      kind: "table",
      columns: [
        {
          key: "category",
          label: "Category",
          kind: "choice",
          options: ["Technical", "Financial", "Marketing", "Regulatory", "Operational"],
        },
        { key: "description", label: "Risk", kind: "text" },
        { key: "probability", label: "Probability", kind: "choice", options: LEVELS },
        { key: "impact", label: "Impact", kind: "choice", options: LEVELS },
        { key: "mitigation", label: "Mitigation", kind: "text" },
      ],
    },
  ],
  financial: [
    {
      key: "capex",
      label: "CapEx: one-off costs before launch",
      kind: "table",
      columns: [
        { key: "item", label: "Item", kind: "text" },
        { key: "amount_usd", label: "Amount ($)", kind: "number" },
      ],
    },
    {
      key: "monthly_opex",
      label: "OpEx: monthly costs at launch",
      kind: "table",
      columns: [
        { key: "item", label: "Item", kind: "text" },
        { key: "amount_usd", label: "Amount ($)", kind: "number" },
      ],
    },
    {
      key: "projections",
      label: "Drivers for each year",
      kind: "table",
      columns: [
        { key: "year", label: "Year", kind: "number" },
        { key: "customers", label: "Customers (year end)", kind: "number" },
        { key: "average_customers", label: "Average customers", kind: "number" },
        { key: "one_off_revenue_usd", label: "One-off revenue ($)", kind: "number" },
        { key: "fixed_costs_month_usd", label: "Fixed costs ($ a month)", kind: "number" },
        { key: "cac_usd", label: "CAC ($)", kind: "number" },
      ],
    },
    { key: "price_per_customer_month_usd", label: "Price per customer ($ a month)", kind: "number" },
    { key: "variable_cost_per_customer_month_usd", label: "Cost to serve a customer ($ a month)", kind: "number" },
    { key: "discount_rate", label: "Discount rate (0.30 = 30%)", kind: "number" },
    { key: "assumptions", label: "Assumptions", kind: "long" },
  ],
};

type Data = Record<string, unknown>;
type Row = Record<string, unknown>;

const control =
  "w-full rounded-md border border-zinc-300 bg-surface px-2.5 py-1.5 text-sm focus:border-accent focus:ring-2 focus:ring-accent/30 focus:outline-none dark:border-zinc-700";

function toNumber(text: string): number {
  return text.trim() === "" ? Number.NaN : Number(text);
}

function Input({
  id,
  label,
  kind,
  options,
  value,
  onChange,
  labelHidden = false,
}: {
  id: string;
  label: string;
  kind: Kind;
  options?: readonly string[];
  value: unknown;
  onChange: (value: unknown) => void;
  labelHidden?: boolean;
}) {
  const text = value === null || value === undefined || Number.isNaN(value) ? "" : String(value);
  const labelElement = (
    <label htmlFor={id} className={labelHidden ? "sr-only" : "mb-1 block text-sm font-medium"}>
      {label}
    </label>
  );
  if (kind === "choice") {
    return (
      <div>
        {labelElement}
        <select id={id} value={text} onChange={(event) => onChange(event.target.value)} className={control}>
          {options?.map((option) => (
            <option key={option}>{option}</option>
          ))}
        </select>
      </div>
    );
  }
  if (kind === "long") {
    const lines = text.split("\n").reduce((sum, line) => sum + 1 + Math.floor(line.length / 100), 0);
    return (
      <div>
        {labelElement}
        <textarea id={id} rows={Math.min(14, Math.max(3, lines))} value={text} onChange={(event) => onChange(event.target.value)} className={control} />
      </div>
    );
  }
  return (
    <div>
      {labelElement}
      <input
        id={id}
        type={kind === "number" ? "number" : "text"}
        step="any"
        value={text}
        onChange={(event) => onChange(kind === "number" ? toNumber(event.target.value) : event.target.value)}
        className={control}
      />
    </div>
  );
}

function blank(columns: Column[]): Row {
  return Object.fromEntries(columns.map((column) => [column.key, column.kind === "number" ? 0 : column.kind === "choice" ? column.options?.[0] : ""]));
}

function TableEditor({ id, label, columns, rows, onChange }: { id: string; label: string; columns: Column[]; rows: Row[]; onChange: (rows: Row[]) => void }) {
  return (
    <fieldset>
      <legend className="mb-2 text-sm font-medium">{label}</legend>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-xs text-zinc-500">
            <tr>
              {columns.map((column) => (
                <th key={column.key} className="px-1 pb-1 text-left font-medium">
                  {column.label}
                </th>
              ))}
              <th className="sr-only">Remove</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index}>
                {columns.map((column) => (
                  <td key={column.key} className="px-1 py-0.5 align-top">
                    <Input
                      id={`${id}-${index}-${column.key}`}
                      label={`${label}, row ${index + 1}: ${column.label}`}
                      labelHidden
                      kind={column.kind === "long" ? "text" : column.kind}
                      options={column.options}
                      value={row[column.key]}
                      onChange={(value) => onChange(rows.map((r, i) => (i === index ? { ...r, [column.key]: value } : r)))}
                    />
                  </td>
                ))}
                <td className="px-1 py-0.5 align-top">
                  <button
                    type="button"
                    aria-label={`Remove row ${index + 1} of ${label}`}
                    onClick={() => onChange(rows.filter((_, i) => i !== index))}
                    className="rounded px-2 py-1.5 text-zinc-500 hover:bg-zinc-100 hover:text-red-700 dark:hover:bg-zinc-800"
                  >
                    ✕
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button
        type="button"
        onClick={() => onChange([...rows, blank(columns)])}
        className="mt-2 rounded-md border border-dashed border-zinc-300 px-3 py-1 text-sm text-zinc-600 hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
      >
        Add a row
      </button>
    </fieldset>
  );
}

export function EditForm({
  part,
  value,
  only,
  onSave,
  onCancel,
}: {
  part: PartKey;
  value: Data;
  only?: readonly string[];
  onSave: (edited: Data) => Promise<string | null>;
  onCancel: () => void;
}) {
  const [draft, setDraft] = useState<Data>(() => structuredClone(value));
  const [saving, setSaving] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const fields = PART_FIELDS[part].filter((field) => !only || only.includes(field.key));
  const set = (key: string, next: unknown) => setDraft((current) => ({ ...current, [key]: next }));

  return (
    <form
      aria-label={`Edit ${part}`}
      className="space-y-5"
      onSubmit={async (event) => {
        event.preventDefault();
        setSaving(true);
        setProblem(await onSave(draft));
        setSaving(false);
      }}
    >
      {fields.map((field) => {
        const id = `${part}-${field.key}`;
        if (field.kind === "table") {
          return (
            <TableEditor
              key={field.key}
              id={id}
              label={field.label}
              columns={field.columns}
              rows={(draft[field.key] as Row[]) ?? []}
              onChange={(rows) => set(field.key, rows)}
            />
          );
        }
        if (field.kind === "size") {
          const size = draft[field.key] as Row;
          return (
            <fieldset key={field.key} className="grid gap-3 sm:grid-cols-[12rem_1fr]">
              <legend className="mb-1 text-sm font-medium">{field.label}</legend>
              <Input id={`${id}-value`} label="Value ($ a year)" kind="number" value={size.value_usd} onChange={(next) => set(field.key, { ...size, value_usd: next })} />
              <Input id={`${id}-basis`} label="Basis" kind="text" value={size.basis} onChange={(next) => set(field.key, { ...size, basis: next })} />
            </fieldset>
          );
        }
        return (
          <Input key={field.key} id={id} label={field.label} kind={field.kind} options={field.options} value={draft[field.key]} onChange={(next) => set(field.key, next)} />
        );
      })}
      {problem && (
        <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-800 dark:bg-red-950 dark:text-red-200">
          {problem}
        </p>
      )}
      <div className="flex gap-2">
        <button type="submit" disabled={saving} className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white hover:bg-accent-strong disabled:opacity-50">
          {saving ? "Saving…" : "Save changes"}
        </button>
        <button type="button" onClick={onCancel} className="rounded-md border border-zinc-300 px-4 py-2 text-sm hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800">
          Cancel
        </button>
      </div>
    </form>
  );
}
