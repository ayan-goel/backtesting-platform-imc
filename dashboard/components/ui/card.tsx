import * as React from "react";
import { cn } from "@/lib/utils";

type CardTone = "default" | "subtle" | "elevated";

const TONE_CLASSES: Record<CardTone, string> = {
  default: "border border-border bg-surface-1",
  subtle: "border border-border bg-surface-1/60",
  elevated: "border border-border bg-surface-1 shadow-elevated",
};

export interface CardProps extends React.ComponentPropsWithoutRef<"div"> {
  tone?: CardTone;
  padded?: boolean;
}

export function Card({
  className,
  tone = "default",
  padded = true,
  children,
  ...rest
}: CardProps) {
  return (
    <div
      className={cn(
        "rounded-card",
        TONE_CLASSES[tone],
        padded && "p-5",
        className
      )}
      {...rest}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "mb-3 text-[10px] font-medium uppercase tracking-[0.08em] text-muted-fg",
        className
      )}
    >
      {children}
    </div>
  );
}
