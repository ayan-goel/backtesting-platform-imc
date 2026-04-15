import * as React from "react";
import { cn } from "@/lib/utils";

export type LabelProps = React.ComponentPropsWithoutRef<"label">;

export const Label = React.forwardRef<HTMLLabelElement, LabelProps>(
  function Label({ className, children, ...rest }, ref) {
    return (
      <label
        ref={ref}
        className={cn(
          "text-[10px] font-medium uppercase tracking-[0.08em] text-muted-fg",
          className
        )}
        {...rest}
      >
        {children}
      </label>
    );
  }
);
