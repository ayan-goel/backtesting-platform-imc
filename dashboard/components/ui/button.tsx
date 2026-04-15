import * as React from "react";
import { cn } from "@/lib/utils";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md";

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary:
    "border border-fg/90 bg-fg text-bg font-semibold hover:bg-fg/90 active:bg-fg/80",
  secondary:
    "border border-border bg-surface-1 text-fg hover:border-border-strong hover:bg-surface-2 active:bg-surface-1",
  ghost:
    "border border-transparent text-muted-fg hover:text-fg hover:bg-surface-1 active:bg-surface-2",
  danger:
    "border border-sell/70 bg-sell/15 text-sell hover:bg-sell/25 active:bg-sell/30",
};

const SIZE_CLASSES: Record<ButtonSize, string> = {
  sm: "h-7 px-2.5 text-xs gap-1.5",
  md: "h-8 px-3 text-sm gap-2",
};

export interface ButtonProps extends React.ComponentPropsWithoutRef<"button"> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  function Button(
    {
      className,
      variant = "secondary",
      size = "md",
      loading = false,
      disabled,
      children,
      type,
      ...rest
    },
    ref
  ) {
    return (
      <button
        ref={ref}
        type={type ?? "button"}
        disabled={disabled ?? loading}
        aria-busy={loading || undefined}
        className={cn(
          "inline-flex items-center justify-center whitespace-nowrap rounded-control font-medium tabular-nums",
          "transition-colors duration-fast",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-bg",
          "disabled:cursor-not-allowed disabled:opacity-50",
          VARIANT_CLASSES[variant],
          SIZE_CLASSES[size],
          className
        )}
        {...rest}
      >
        {loading && <Spinner />}
        {children}
      </button>
    );
  }
);

/**
 * Shared class list for Button-styled anchors / Next.js <Link>s.
 * Apply via className so we don't have to duplicate focus/hover states.
 */
export function buttonClasses({
  variant = "secondary",
  size = "md",
  className,
}: { variant?: ButtonVariant; size?: ButtonSize; className?: string } = {}): string {
  return cn(
    "inline-flex items-center justify-center whitespace-nowrap rounded-control font-medium tabular-nums",
    "transition-colors duration-fast",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-bg",
    VARIANT_CLASSES[variant],
    SIZE_CLASSES[size],
    className
  );
}

function Spinner() {
  return (
    <svg
      className="h-3 w-3 animate-spin"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="3"
        strokeOpacity="0.25"
      />
      <path
        d="M22 12a10 10 0 0 0-10-10"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  );
}
