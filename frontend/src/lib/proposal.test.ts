import { describe, expect, test } from "vitest";

import type { InvestmentMetrics } from "@/lib/api";
import { describeBreakEven, describeIrr, describePayback, full, money, percent, severity } from "@/lib/proposal";

function metrics(changes: Partial<InvestmentMetrics>): InvestmentMetrics {
  return {
    capex: 10_000,
    monthly_fixed_costs: 1_000,
    revenue: [],
    opex: [],
    net_cash_flow: [-10_000, -3_200, 7_200, 24_000],
    net_margin: [],
    npv: 0,
    irr: 0.5,
    payback_months: 27,
    break_even_customers: 13,
    ...changes,
  };
}

describe("the proposal's figures in words (as proposal.py says them)", () => {
  test("money is compact or full", () => {
    expect(money(750)).toBe("$750");
    expect(money(12_000)).toBe("$12k");
    expect(money(2_500)).toBe("$2.5k");
    expect(money(216_000_000)).toBe("$216M");
    expect(money(1_200_000_000)).toBe("$1.2B");
    expect(money(-72_398)).toBe("-$72.4k");
    expect(full(-6_000)).toBe("-$6,000");
    expect(full(149)).toBe("$149");
    expect(percent(0.3)).toBe("30%");
  });

  test("money is in the document's currency, as the PDF shows it", () => {
    expect(money(12_500, "EUR")).toBe("€12.5k");
    expect(full(-6_000, "GBP")).toBe("-£6,000");
    expect(full(1_500, "CHF")).toBe("CHF 1,500");
    expect(money(1_234_000, "INR")).toBe("₹1.2M");
    // A code the table lacks is still shown, by its code.
    expect(full(10, "XYZ")).toBe("XYZ 10");
  });

  test("the IRR, or why there is none", () => {
    expect(describeIrr(metrics({}))).toEqual(["50%", "on the three-year cash flows"]);
    expect(describeIrr(metrics({ irr: 21.35 }))[0]).toBe("> 1,000%");
    expect(describeIrr(metrics({ irr: null, net_cash_flow: [0, 5, 5, 5] }))[1]).toBe("nothing is invested up front");
    expect(describeIrr(metrics({ irr: null, net_cash_flow: [-5, -5, -5, 0] }))[1]).toBe("the cash flows never turn positive");
    expect(describeIrr(metrics({ irr: null, net_cash_flow: [-5, 10, -10, 0] }))[1]).toBe("not defined for these cash flows");
  });

  test("payback and break-even", () => {
    expect(describePayback(metrics({}))).toBe("27 months");
    expect(describePayback(metrics({ payback_months: 0.6 }))).toBe("Under a month");
    expect(describePayback(metrics({ payback_months: 1.2 }))).toBe("1 month");
    expect(describePayback(metrics({ payback_months: null }))).toBe("After year 3");
    expect(describeBreakEven(metrics({}))).toBe("13 customers");
    expect(describeBreakEven(metrics({ break_even_customers: 1 }))).toBe("1 customer");
    expect(describeBreakEven(metrics({ break_even_customers: null }))).toBe("Never");
  });

  test("a risk's severity follows its probability and impact", () => {
    expect(severity("Low", "Low")).toBe("Low");
    expect(severity("Low", "Medium")).toBe("Low");
    expect(severity("Medium", "Medium")).toBe("Moderate");
    expect(severity("Medium", "High")).toBe("High");
    expect(severity("High", "High")).toBe("Critical");
  });
});
