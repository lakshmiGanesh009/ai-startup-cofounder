import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { Sidebar } from "@/components/sidebar";
import { BackendProvider } from "@/lib/backend";

import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "AI Startup Co-Founder Team",
  description: "A multi-agent founding team that evaluates startup ideas",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full">
        <BackendProvider>
          <div className="flex min-h-dvh flex-col lg:flex-row">
            <Sidebar />
            <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8 sm:px-8">{children}</main>
          </div>
        </BackendProvider>
      </body>
    </html>
  );
}
