import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function fmtUsd(n: number | null | undefined, opts: { sign?: boolean; decimals?: number } = {}) {
  if (typeof n !== "number" || Number.isNaN(n)) return "—";
  const decimals = opts.decimals ?? 2;
  const formatted = n.toLocaleString("en-US", { style: "currency", currency: "USD", minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  if (opts.sign && n > 0) return `+${formatted}`;
  return formatted;
}

export function fmtPct(n: number | null | undefined, opts: { sign?: boolean; decimals?: number } = {}) {
  if (typeof n !== "number" || Number.isNaN(n)) return "—";
  const decimals = opts.decimals ?? 2;
  const formatted = `${n.toFixed(decimals)}%`;
  if (opts.sign && n > 0) return `+${formatted}`;
  return formatted;
}

export function fmtTime(iso: string) {
  return new Date(iso).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
}
