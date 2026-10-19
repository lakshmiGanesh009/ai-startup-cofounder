import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// jsdom has no modal dialogs or object URLs; these stand in for them.
if (!HTMLDialogElement.prototype.showModal) {
  // As in a browser, opening it moves focus to its first control.
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    this.setAttribute("open", "");
    this.querySelector<HTMLElement>("button, [href], input, select, textarea")?.focus();
  };
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    if (!this.hasAttribute("open")) return;
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
}
URL.createObjectURL = vi.fn(() => "blob:report-pdf");
URL.revokeObjectURL = vi.fn();

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
  window.localStorage.clear();
  window.sessionStorage.clear();
});
