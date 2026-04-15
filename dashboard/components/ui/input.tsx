import * as React from "react";
import { cn } from "@/lib/utils";

const CONTROL_CLASSES = [
  "h-8 w-full rounded-control border border-border bg-bg px-2.5 text-sm text-fg",
  "placeholder:text-muted-fg/70",
  "transition-colors duration-fast",
  "hover:border-border-strong",
  "focus-visible:outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-ring/50",
  "disabled:cursor-not-allowed disabled:opacity-50",
].join(" ");

export interface InputProps extends React.ComponentPropsWithoutRef<"input"> {
  mono?: boolean;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  function Input({ className, mono = false, type = "text", ...rest }, ref) {
    return (
      <input
        ref={ref}
        type={type}
        className={cn(CONTROL_CLASSES, mono && "font-mono", className)}
        {...rest}
      />
    );
  }
);

export { CONTROL_CLASSES };
