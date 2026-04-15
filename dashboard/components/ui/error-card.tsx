import * as React from "react";
import { cn } from "@/lib/utils";

export interface ErrorCardProps
  extends Omit<React.ComponentPropsWithoutRef<"div">, "title"> {
  title?: React.ReactNode;
}

export function ErrorCard({
  className,
  title = "something went wrong",
  children,
  ...rest
}: ErrorCardProps) {
  return (
    <div
      role="alert"
      className={cn(
        "rounded-card border border-sell/40 bg-sell/5 p-4 text-sm text-sell",
        className
      )}
      {...rest}
    >
      <div className="text-xs font-semibold uppercase tracking-[0.06em] text-sell/80">
        {title}
      </div>
      <div className="mt-1">{children}</div>
    </div>
  );
}
