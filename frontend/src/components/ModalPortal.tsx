import type { ReactNode } from "react";
import { createPortal } from "react-dom";

/**
 * Renders modal content as a direct child of <body>, escaping any ancestor that
 * establishes a containing block for `position: fixed` (e.g. the animated
 * `.app-page-content` element, which carries a transform via `animation-fill-mode: both`).
 * This guarantees overlays center on the viewport, matching the modals that are
 * already rendered outside the app shell.
 */
export function ModalPortal({ children }: { children: ReactNode }) {
  if (typeof document === "undefined") {
    return null;
  }
  return createPortal(children, document.body);
}
