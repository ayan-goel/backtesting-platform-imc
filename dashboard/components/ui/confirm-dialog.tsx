"use client";

import * as React from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export interface ConfirmDialogProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void | Promise<void>;
  title: React.ReactNode;
  description?: React.ReactNode;
  /** When set, the confirm button is disabled until the user types this exact string. */
  requireTypedConfirmation?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  loading?: boolean;
  error?: string | null;
  children?: React.ReactNode;
}

export function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  description,
  requireTypedConfirmation,
  confirmLabel = "delete",
  cancelLabel = "cancel",
  loading = false,
  error = null,
  children,
}: ConfirmDialogProps) {
  const [typed, setTyped] = React.useState("");

  // Reset the typed confirmation whenever the dialog reopens.
  React.useEffect(() => {
    if (open) setTyped("");
  }, [open]);

  // Close on Escape.
  React.useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !loading) onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, loading, onClose]);

  if (!open) return null;

  const typedMatches =
    !requireTypedConfirmation || typed === requireTypedConfirmation;
  const canConfirm = typedMatches && !loading;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-dialog-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
    >
      <div
        className="absolute inset-0 bg-bg/80 backdrop-blur-sm"
        onClick={() => {
          if (!loading) onClose();
        }}
      />
      <div
        className={cn(
          "relative w-full max-w-md rounded-card border border-border bg-surface-1 p-5",
          "shadow-elevated"
        )}
      >
        <h2
          id="confirm-dialog-title"
          className="text-lg font-semibold tracking-tight text-fg"
        >
          {title}
        </h2>
        {description && (
          <div className="mt-2 text-sm leading-relaxed text-muted-fg">
            {description}
          </div>
        )}
        {children && <div className="mt-3">{children}</div>}

        {requireTypedConfirmation && (
          <div className="mt-4 flex flex-col gap-1.5">
            <label className="text-[10px] font-medium uppercase tracking-[0.08em] text-muted-fg">
              type{" "}
              <code className="font-mono text-fg">
                {requireTypedConfirmation}
              </code>{" "}
              to confirm
            </label>
            <Input
              mono
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              autoFocus
              placeholder={requireTypedConfirmation}
              disabled={loading}
            />
          </div>
        )}

        {error && (
          <div className="mt-3 rounded-control border border-sell/40 bg-sell/5 p-2 text-xs text-sell">
            {error}
          </div>
        )}

        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose} disabled={loading}>
            {cancelLabel}
          </Button>
          <Button
            variant="danger"
            onClick={() => void onConfirm()}
            disabled={!canConfirm}
            loading={loading}
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
