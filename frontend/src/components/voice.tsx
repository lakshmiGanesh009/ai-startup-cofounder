"use client";

// Dictation in the app's input boxes: a mic in each, the same everywhere, in
// the team's colours (a ring of the five agents' colours, and while it records
// five bars, one an agent, that follow the voice). Press it and speak, in any
// language; press it again, or Enter, and the API has Azure OpenAI's Whisper
// write the recording down in English, and the words go in where the cursor
// was, as if typed. Escape throws the recording away. Nothing of it is kept.

import { useEffect, useRef, useState } from "react";

import { CheckIcon, MicIcon } from "@/components/ui/icons";
import { ApiError, transcribe } from "@/lib/api";
import { useHealth } from "@/lib/backend";

// The longest recording, in seconds, before it stops by itself, and the least
// that can hold a word.
const LONGEST = 120;
const SHORTEST_BYTES = 1_000;
const BARS = ["chief", "marketing", "finance", "technical", "risk"] as const;
// What to record in, the first a browser can: Opus in WebM (Chrome, Firefox, Edge), else MP4 (Safari).
const RECORDINGS = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];

type Field = HTMLInputElement | HTMLTextAreaElement;
type Phase = "idle" | "starting" | "recording" | "writing" | "done";

function fieldIn(box: HTMLElement | null): Field | null {
  return box?.querySelector<Field>(":scope > input, :scope > textarea") ?? null;
}

// `text` put in `field` where its selection was (else at the end), a space
// from the words either side, as if typed, so React's onChange sees it.
export function insertInto(field: Field, text: string, selection: [number, number] | null) {
  const value = field.value;
  const [start, end] = selection ?? [value.length, value.length];
  const before = value.slice(0, start);
  const after = value.slice(end);
  const lead = before && !/\s$/.test(before) ? " " : "";
  const trail = after && !/^\s/.test(after) ? " " : "";
  let next = `${before}${lead}${text}${trail}${after}`;
  if (field.maxLength > 0) next = next.slice(0, field.maxLength);
  Object.getOwnPropertyDescriptor(Object.getPrototypeOf(field), "value")?.set?.call(field, next);
  field.dispatchEvent(new Event("input", { bubbles: true }));
  field.focus();
  const caret = Math.min(next.length, `${before}${lead}${text}`.length);
  try {
    field.setSelectionRange(caret, caret);
  } catch {
    // A field without a caret to place.
  }
}

function clock(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function Mic({ box, label }: { box: React.RefObject<HTMLSpanElement | null>; label: string }) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [seconds, setSeconds] = useState(0);
  const [note, setNote] = useState<string | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const chunks = useRef<Blob[]>([]);
  const bars = useRef<(HTMLSpanElement | null)[]>([]);
  const selection = useRef<[number, number] | null>(null);
  const keep = useRef(true);
  const stopListening = useRef<() => void>(() => {});
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      keep.current = false;
      if (recorder.current?.state === "recording") recorder.current.stop();
      stopListening.current();
    };
  }, []);

  // A note goes after a while, or on the next press.
  useEffect(() => {
    if (!note) return;
    const timer = setTimeout(() => setNote(null), 8000);
    return () => clearTimeout(timer);
  }, [note]);

  // While it records, Enter writes it down and Escape throws it away, wherever the focus is.
  useEffect(() => {
    if (phase !== "recording") return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Enter" && event.key !== "Escape") return;
      event.preventDefault();
      event.stopPropagation();
      stop(event.key === "Enter");
    };
    document.addEventListener("keydown", onKey, true);
    return () => document.removeEventListener("keydown", onKey, true);
  }, [phase]);

  // The bars follow the voice: each an agent's colour and a band of its pitch.
  function listen(media: MediaStream) {
    const Context = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Context) return;
    const context = new Context();
    void context.resume();
    const analyser = context.createAnalyser();
    analyser.fftSize = 256;
    context.createMediaStreamSource(media).connect(analyser);
    const levels = new Uint8Array(analyser.frequencyBinCount);
    let frame = 0;
    const draw = () => {
      analyser.getByteFrequencyData(levels);
      bars.current.forEach((bar, index) => {
        if (!bar) return;
        const band = levels.slice(1 + index * 4, 5 + index * 4);
        const level = band.reduce((sum, value) => sum + value, 0) / band.length / 170;
        bar.style.transform = `scaleY(${Math.max(0.22, Math.min(1, level))})`;
      });
      frame = requestAnimationFrame(draw);
    };
    draw();
    stopListening.current = () => {
      cancelAnimationFrame(frame);
      void context.close();
    };
  }

  function release() {
    stopListening.current();
    stopListening.current = () => {};
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
  }

  async function start() {
    setNote(null);
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setNote("This browser cannot record here: dictation needs a browser with a microphone, on https or localhost.");
      return;
    }
    const field = fieldIn(box.current);
    selection.current =
      field && document.activeElement === field
        ? [field.selectionStart ?? field.value.length, field.selectionEnd ?? field.value.length]
        : null;
    setPhase("starting");
    try {
      const media = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.current = media;
      const type = RECORDINGS.find((kind) => MediaRecorder.isTypeSupported?.(kind));
      const made = new MediaRecorder(media, type ? { mimeType: type } : undefined);
      chunks.current = [];
      keep.current = true;
      made.ondataavailable = (event) => {
        if (event.data.size) chunks.current.push(event.data);
      };
      made.onstop = () => void finish(made.mimeType || type || "audio/webm");
      made.start();
      recorder.current = made;
      listen(media);
      setSeconds(0);
      setPhase("recording");
    } catch (error) {
      release();
      setPhase("idle");
      const kind = (error as DOMException).name;
      setNote(
        kind === "NotAllowedError"
          ? "The microphone is blocked: allow it for this site in the browser's settings, then try again."
          : kind === "NotFoundError"
            ? "No microphone was found."
            : `The microphone could not start: ${(error as Error).message}`,
      );
    }
  }

  // The time counts while it records, and the recording stops by itself at the longest.
  useEffect(() => {
    if (phase !== "recording") return;
    const began = Date.now();
    const timer = setInterval(() => {
      const elapsed = Math.floor((Date.now() - began) / 1000);
      setSeconds(elapsed);
      if (elapsed >= LONGEST) stop(true);
    }, 250);
    return () => clearInterval(timer);
  }, [phase]);

  function stop(written: boolean) {
    keep.current = written;
    if (recorder.current?.state === "recording") recorder.current.stop();
  }

  async function finish(type: string) {
    release();
    recorder.current = null;
    if (!mounted.current) return;
    if (!keep.current) {
      setPhase("idle");
      return;
    }
    const audio = new Blob(chunks.current, { type });
    if (audio.size < SHORTEST_BYTES) {
      setPhase("idle");
      setNote("That was too short to hear: hold the recording a moment longer.");
      return;
    }
    setPhase("writing");
    try {
      const { text } = await transcribe(audio);
      if (!mounted.current) return;
      const field = fieldIn(box.current);
      if (!text.trim()) {
        setPhase("idle");
        setNote("No words were heard in that recording.");
        return;
      }
      if (field) insertInto(field, text.trim(), selection.current);
      setPhase("done");
      setTimeout(() => mounted.current && setPhase("idle"), 1200);
    } catch (error) {
      if (!mounted.current) return;
      setPhase("idle");
      setNote(error instanceof ApiError ? error.detail : (error as Error).message);
    }
  }

  // Pressing the mic leaves the focus, and the cursor, in the box.
  const keepFocus = (event: React.MouseEvent) => event.preventDefault();
  const busy = phase === "starting" || phase === "writing";
  return (
    <>
      <button
        type="button"
        data-phase={phase}
        aria-label={
          phase === "recording"
            ? `Stop and write it down (${clock(seconds)} recorded)`
            : phase === "writing"
              ? "Writing it down"
              : `Dictate into ${label}`
        }
        title={phase === "idle" ? "Dictate in any language: Azure OpenAI's Whisper writes it down in English" : undefined}
        aria-disabled={busy || undefined}
        onMouseDown={keepFocus}
        onClick={() => (phase === "recording" ? stop(true) : phase === "idle" || phase === "done" ? void start() : undefined)}
        className="voice-mic"
      >
        {phase === "recording" || phase === "writing" || phase === "starting" ? (
          <>
            <span aria-hidden className="voice-bars">
              {BARS.map((agent, index) => (
                <span
                  key={agent}
                  ref={(bar) => {
                    bars.current[index] = bar;
                  }}
                  style={{ "--i": index } as React.CSSProperties}
                  className={`agent-${agent} bg-agent`}
                />
              ))}
            </span>
            {phase === "recording" && (
              <>
                <span aria-hidden className="voice-time tabular">
                  {clock(seconds)}
                </span>
                <span aria-hidden className="voice-stop" />
              </>
            )}
          </>
        ) : phase === "done" ? (
          <CheckIcon className="size-3.5 text-good" />
        ) : (
          <MicIcon className="size-[15px]" />
        )}
      </button>
      <span aria-live="polite" className="sr-only">
        {phase === "recording" ? "Recording. Press Enter to write it down, Escape to discard it." : phase === "writing" ? "Writing it down." : phase === "done" ? "Written in." : ""}
      </span>
      {note && (
        <span role="status" className="voice-note">
          {note}
          <button type="button" aria-label="Close" onClick={() => setNote(null)} className="ml-2 text-ink-3 hover:text-ink">
            ×
          </button>
        </span>
      )}
    </>
  );
}

// An input box with the mic, which names it after `label` ("Dictate into
// Target market"): `multiline` for a box of several lines, where the mic sits
// in a strip below the text rather than at the end of the line. A block-level
// span, so it may sit wherever a text box may, a paragraph included.
export function Voice({
  children,
  label,
  multiline = false,
  className = "",
}: {
  children: React.ReactNode;
  label: string;
  multiline?: boolean;
  className?: string;
}) {
  const box = useRef<HTMLSpanElement>(null);
  const health = useHealth();
  // No mic while the API says dictation cannot run (no Whisper deployment): the box as it is.
  if (health?.voice && !health.voice.dictation) {
    return <span className={`relative block ${className}`}>{children}</span>;
  }
  return (
    <span ref={box} data-lines={multiline ? "many" : "one"} className={`voice-field relative block ${className}`}>
      {children}
      <Mic box={box} label={label} />
    </span>
  );
}
