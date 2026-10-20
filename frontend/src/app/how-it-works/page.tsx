import type { Metadata } from "next";

import { HowItWorks } from "@/components/how/how-app";

export const metadata: Metadata = { title: "How it works · AI Startup Co-Founder Team" };

export default function HowItWorksPage() {
  return <HowItWorks />;
}
