import type { Metadata } from "next";

import { ReportsApp } from "@/components/reports/reports-app";

export const metadata: Metadata = { title: "Reports · AI Startup Co-Founder Team" };

export default function ReportsPage() {
  return <ReportsApp />;
}
