"use client";
import { useEffect } from "react";

const EVENT_NAME = "portfolio:invalidate";

export function emitPortfolioInvalidate() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(EVENT_NAME));
  }
}

export function usePortfolioInvalidate(cb: () => void) {
  useEffect(() => {
    const h = () => cb();
    window.addEventListener(EVENT_NAME, h);
    return () => window.removeEventListener(EVENT_NAME, h);
  }, [cb]);
}
