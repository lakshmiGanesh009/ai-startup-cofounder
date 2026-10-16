import { BackendStatus } from "@/components/backend-status";

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-6 px-4 py-16">
      <h1 className="text-3xl font-semibold tracking-tight">AI Startup Co-Founder Team</h1>
      <p className="text-zinc-600 dark:text-zinc-400">
        This is the scaffold for the Next.js frontend. Until it is built out, use the Streamlit
        UI (<code>streamlit_app.py</code>) to run the founding team.
      </p>
      <BackendStatus />
    </main>
  );
}
