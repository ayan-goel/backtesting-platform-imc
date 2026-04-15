import * as React from "react";
import { cn } from "@/lib/utils";

type BadgeVariant = "default" | "buy" | "sell" | "accent" | "warn" | "muted";

const VARIANT_CLASSES: Record<BadgeVariant, string> = {
  default: "bg-surface-2 text-fg border-border",
  buy: "bg-buy/10 text-buy border-buy/30",
  sell: "bg-sell/10 text-sell border-sell/30",
  accent: "bg-accent/10 text-accent border-accent/30",
  warn: "bg-warn/10 text-warn border-warn/30",
  muted: "bg-surface-1 text-muted-fg border-border",
};

export interface BadgeProps extends React.ComponentPropsWithoutRef<"span"> {
  variant?: BadgeVariant;
}

export function Badge({ className, variant = "default", children, ...rest }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-[3px]",
        "text-[10px] font-semibold uppercase tracking-[0.06em] tabular-nums",
        VARIANT_CLASSES[variant],
        className
      )}
      {...rest}
    >
      {children}
    </span>
  );
}

/** Convenience mapping for status strings used across the app. */
export function statusVariant(
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled" | string
): BadgeVariant {
  if (status === "succeeded") return "buy";
  if (status === "failed") return "sell";
  if (status === "running") return "accent";
  if (status === "cancelled") return "muted";
  return "default";
}

export function StatusBadge({
  status,
  className,
}: {
  status: string;
  className?: string;
}) {
  return (
    <Badge variant={statusVariant(status)} className={className} role="status">
      {status}
    </Badge>
  );
}
