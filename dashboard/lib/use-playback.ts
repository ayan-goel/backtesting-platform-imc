import { useEffect, useRef } from "react";
import { snapToNearestTs } from "./replay";
import type { EventRecord } from "./types";

// Speed 1 ≈ ~100s to replay a 10k-ts tutorial day; 64× finishes in ~1.5s.
// Tuned so the eye can follow 4× but still see meaningful motion at 1×.
const BASE_TS_PER_MS = 10;

interface UsePlaybackArgs {
  events: readonly EventRecord[];
  ts: number;
  setTs: (ts: number) => void;
  setPlaybackCursor: (ts: number | null) => void;
  isPlaying: boolean;
  onEnd: () => void;
  speed: number;
}

/**
 * Drive playback forward via `requestAnimationFrame`.
 *
 * Two separate cursor values are maintained:
 * - `playbackCursor` (raw ts) is updated on every frame for smooth visual
 *   motion of the overlay line. It does not trigger data re-renders.
 * - `ts` (committed, snapped to the nearest event) is only updated when the
 *   raw cursor actually crosses an event boundary. Data consumers (book
 *   panel, tapes, totals) only re-render then.
 *
 * Auto-stops at the last event. The caller's `onEnd` is responsible for
 * flipping `isPlaying` back to false.
 */
export function usePlayback(args: UsePlaybackArgs): void {
  const ref = useRef(args);
  ref.current = args;

  useEffect(() => {
    if (!args.isPlaying) {
      // Clear the cursor so idle state reads from `ts` again.
      args.setPlaybackCursor(null);
      return;
    }

    const { events, ts: startTs } = ref.current;
    if (events.length < 2) {
      ref.current.onEnd();
      return;
    }

    let rafId = 0;
    let lastFrame = performance.now();
    let rawCursor = startTs;
    let lastCommittedTs = startTs;

    const tick = (now: number) => {
      const { events: evs, setTs, setPlaybackCursor, onEnd, speed, isPlaying } = ref.current;
      if (!isPlaying) return;
      if (evs.length < 2) {
        onEnd();
        return;
      }

      const dt = now - lastFrame;
      lastFrame = now;

      rawCursor += speed * dt * BASE_TS_PER_MS;

      const last = evs[evs.length - 1].ts;
      if (rawCursor >= last) {
        setPlaybackCursor(last);
        setTs(last);
        onEnd();
        return;
      }

      // Overlay reads playbackCursor — update every frame for smoothness.
      setPlaybackCursor(rawCursor);

      // Data consumers read `ts` — only update when we cross an event
      // boundary, so the book panel / tapes / totals don't re-render 60×
      // per second for no visible difference.
      const snapped = snapToNearestTs(evs, rawCursor);
      if (snapped !== lastCommittedTs) {
        lastCommittedTs = snapped;
        setTs(snapped);
      }

      rafId = requestAnimationFrame(tick);
    };

    rafId = requestAnimationFrame(tick);
    return () => {
      if (rafId !== 0) cancelAnimationFrame(rafId);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [args.isPlaying]);
}
