import * as React from "react";
import { cn } from "@/lib/utils";
import { CONTROL_CLASSES } from "@/components/ui/input";

export interface SelectProps extends React.ComponentPropsWithoutRef<"select"> {
  mono?: boolean;
}

export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  function Select({ className, mono = false, children, ...rest }, ref) {
    return (
      <select
        ref={ref}
        className={cn(
          CONTROL_CLASSES,
          "appearance-none bg-no-repeat pr-8",
          mono && "font-mono",
          className
        )}
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' fill='none' stroke='%23999' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'><path d='M4 6l4 4 4-4'/></svg>\")",
          backgroundPosition: "right 0.5rem center",
          backgroundSize: "1rem",
        }}
        {...rest}
      >
        {children}
      </select>
    );
  }
);
