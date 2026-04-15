// Auto stride picker for the replay view. Downsamples server-side via the
// /runs/{id}/events?stride=N query param so long runs stay responsive.

export const RESOLUTION_CHOICES = ["auto", "1", "5", "10", "20"] as const;
export type ResolutionChoice = (typeof RESOLUTION_CHOICES)[number];

/** Choose a stride so that each product's displayed count is ≤ target. */
export function pickStride(
  totalEvents: number,
  numProducts: number,
  target = 5000
): number {
  if (numProducts <= 0) return 1;
  if (totalEvents <= 0) return 1;
  const perProduct = Math.ceil(totalEvents / numProducts);
  if (perProduct <= target) return 1;
  return Math.ceil(perProduct / target);
}

/** Resolve a user-facing choice to a concrete stride. `auto` defers to pickStride. */
export function resolveStride(
  choice: ResolutionChoice,
  totalEvents: number,
  numProducts: number
): number {
  if (choice === "auto") return pickStride(totalEvents, numProducts);
  const parsed = parseInt(choice, 10);
  return Number.isFinite(parsed) && parsed >= 1 ? parsed : 1;
}
