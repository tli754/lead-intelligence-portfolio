/**
 * Shared color-tone vocabulary for status/confidence indicators.
 *
 * Tone hues come from the fixed status palette (good/warning/serious/
 * critical), plus `active` (categorical slot 1, blue) for in-progress
 * pipeline stages and `milestone` (categorical slot 7, violet) as a
 * one-off accent for the "customer" workflow outcome — see the CSS
 * custom properties defined in `src/index.css`. Per the palette's
 * accessibility rule, a tone is always paired with a text label; nothing
 * here is presented as color alone.
 */

export type StatusTone = "neutral" | "active" | "good" | "warning" | "serious" | "critical" | "milestone";

export const TONE_DOT_CLASS: Record<StatusTone, string> = {
  neutral: "bg-muted-foreground",
  active: "bg-status-active",
  good: "bg-status-good",
  warning: "bg-status-warning",
  serious: "bg-status-serious",
  critical: "bg-status-critical",
  milestone: "bg-status-milestone",
};
