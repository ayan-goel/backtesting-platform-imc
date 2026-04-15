"use client";

import { Pause, Play } from "lucide-react";
import { Select } from "@/components/ui/select";
import { cn } from "@/lib/utils";

const SPEEDS = [1, 4, 16, 64] as const;

export function PlaybackControls({
  isPlaying,
  onPlayPause,
  speed,
  onSpeedChange,
}: {
  isPlaying: boolean;
  onPlayPause: () => void;
  speed: number;
  onSpeedChange: (s: number) => void;
}) {
  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        onClick={onPlayPause}
        aria-label={isPlaying ? "pause playback" : "play playback"}
        className={cn(
          "flex h-8 w-8 items-center justify-center rounded-control border border-border bg-surface-1 text-fg",
          "transition-colors duration-fast",
          "hover:border-accent hover:text-accent",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-bg"
        )}
      >
        {isPlaying ? <Pause size={14} /> : <Play size={14} />}
      </button>
      <Select
        mono
        value={speed}
        onChange={(e) => onSpeedChange(Number(e.target.value))}
        aria-label="playback speed"
        className="w-auto min-w-[4.5rem] text-xs"
      >
        {SPEEDS.map((s) => (
          <option key={s} value={s}>
            {s}×
          </option>
        ))}
      </Select>
      <div className="hidden text-[10px] font-medium uppercase tracking-[0.08em] text-muted-fg sm:block">
        space · ← → · home/end
      </div>
    </div>
  );
}
