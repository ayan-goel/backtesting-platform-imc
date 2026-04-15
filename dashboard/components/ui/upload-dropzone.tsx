"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export type UploadStatus = "idle" | "uploading" | "ok" | "error";

export interface UploadDropzoneProps {
  title: React.ReactNode;
  accept: string;
  multiple?: boolean;
  chooseLabel?: string;
  onFiles: (files: File[]) => void;
  onDrop?: (e: React.DragEvent) => void;
  status: UploadStatus;
  message: string | null;
  children: React.ReactNode;
}

/**
 * Shared drag-and-drop dropzone shell. Callers own the upload logic — this
 * component only renders the dashed border, chooser button, hint slot, and
 * feedback line.
 *
 * When `onDrop` is provided it replaces the default file-extraction behavior
 * (e.g. dataset upload walks DataTransferItem.webkitGetAsEntry).
 */
export function UploadDropzone({
  title,
  accept,
  multiple = false,
  chooseLabel,
  onFiles,
  onDrop,
  status,
  message,
  children,
}: UploadDropzoneProps) {
  const [dragOver, setDragOver] = React.useState(false);

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    if (onDrop) {
      onDrop(e);
      return;
    }
    const files = Array.from(e.dataTransfer.files ?? []);
    if (files.length > 0) onFiles(files);
  }

  function handlePick(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    if (files.length > 0) onFiles(files);
    e.target.value = "";
  }

  return (
    <div>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        className={cn(
          "group relative rounded-card border border-dashed border-border bg-surface-1/40 p-10 text-center",
          "transition-colors duration-fast",
          "hover:border-border-strong hover:bg-surface-1/60",
          dragOver && "border-accent bg-accent/5",
          status === "uploading" && "opacity-70"
        )}
      >
        <div className="mx-auto flex max-w-md flex-col items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full border border-border bg-surface-2 text-muted-fg">
            <svg
              viewBox="0 0 24 24"
              className="h-5 w-5"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M12 3v12" />
              <path d="m7 8 5-5 5 5" />
              <path d="M5 15v4a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4" />
            </svg>
          </div>
          <div className="text-sm font-medium text-fg">{title}</div>
          <label className="inline-flex cursor-pointer items-center gap-2 rounded-control border border-border bg-surface-2 px-3 py-1.5 text-xs font-medium text-fg transition-colors duration-fast hover:border-accent hover:text-accent">
            {chooseLabel ?? (multiple ? "choose files" : "choose file")}
            <input
              type="file"
              accept={accept}
              multiple={multiple}
              onChange={handlePick}
              className="hidden"
            />
          </label>
          <div className="text-xs leading-relaxed text-muted-fg">{children}</div>
        </div>
      </div>

      {message && (
        <div
          role={status === "error" ? "alert" : "status"}
          aria-live="polite"
          className={cn(
            "mt-3 text-xs",
            status === "ok" && "text-buy",
            status === "error" && "text-sell",
            status === "uploading" && "text-muted-fg"
          )}
        >
          {status === "uploading" ? "uploading…" : message}
        </div>
      )}
    </div>
  );
}
