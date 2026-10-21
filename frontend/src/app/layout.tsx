import type { Metadata } from "next";
import { Geist, Geist_Mono, Newsreader } from "next/font/google";

import { Sidebar } from "@/components/sidebar";
import { BackendProvider } from "@/lib/backend";
import { THEME_SCRIPT } from "@/lib/theme";

import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// The serif for the documents the agents write: strategies, reports, proposals.
const newsreader = Newsreader({
  variable: "--font-newsreader",
  subsets: ["latin"],
  style: ["normal", "italic"],
  axes: ["opsz"],
});

export const metadata: Metadata = {
  title: "Co-Founder · An AI founding team",
  description: "A multi-agent founding team that evaluates startup ideas and writes them up as investment proposals",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    // The theme script sets data-theme on <html> before React hydrates it.
    <html
      lang="en"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} ${newsreader.variable} h-full antialiased`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="min-h-full">
        <BackendProvider>
          <div className="flex min-h-dvh flex-col lg:flex-row">
            <Sidebar />
            <main className="w-full min-w-0 flex-1 px-4 py-8 sm:px-8 lg:px-12 lg:py-10">
              <div className="mx-auto max-w-[76rem]">{children}</div>
            </main>
          </div>
        </BackendProvider>
      </body>
    </html>
  );
}
