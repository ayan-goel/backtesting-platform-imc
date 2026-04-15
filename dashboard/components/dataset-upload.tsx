"use client";

import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import { UploadDropzone, type UploadStatus } from "@/components/ui/upload-dropzone";

interface UploadResult {
  uploaded: Array<{ _id: string; round: number; day: number }>;
  skipped: Array<{ filename: string; reason: string }>;
}

async function collectFiles(dt: DataTransfer): Promise<File[]> {
  const items = dt.items ? Array.from(dt.items) : [];
  if (items.length === 0) return Array.from(dt.files ?? []);

  const out: File[] = [];

  async function walkEntry(entry: FileSystemEntry): Promise<void> {
    if (entry.isFile) {
      const file = await new Promise<File>((resolve, reject) =>
        (entry as FileSystemFileEntry).file(resolve, reject)
      );
      out.push(file);
      return;
    }
    if (entry.isDirectory) {
      const dirReader = (entry as FileSystemDirectoryEntry).createReader();
      const readBatch = (): Promise<FileSystemEntry[]> =>
        new Promise((resolve, reject) => dirReader.readEntries(resolve, reject));
      // Directory readers return entries in batches; keep reading until empty.
      for (;;) {
        const batch = await readBatch();
        if (batch.length === 0) break;
        for (const child of batch) await walkEntry(child);
      }
    }
  }

  const roots: FileSystemEntry[] = [];
  for (const item of items) {
    if (item.kind !== "file") continue;
    const entry = item.webkitGetAsEntry?.();
    if (entry) roots.push(entry);
    else {
      const f = item.getAsFile();
      if (f) out.push(f);
    }
  }
  for (const root of roots) await walkEntry(root);

  return out;
}

export function DatasetUpload() {
  const router = useRouter();
  const [status, setStatus] = useState<UploadStatus>("idle");
  const [message, setMessage] = useState<string | null>(null);

  const upload = useCallback(
    async (files: File[]) => {
      const csvs = files.filter((f) => f.name.toLowerCase().endsWith(".csv"));
      if (csvs.length === 0) {
        setStatus("error");
        setMessage("no .csv files found in selection");
        return;
      }

      setStatus("uploading");
      setMessage(null);

      const fd = new FormData();
      for (const f of csvs) fd.append("files", f, f.name);

      try {
        const res = await fetch("/api/datasets", { method: "POST", body: fd });
        if (!res.ok) {
          const detail = await res.text();
          throw new Error(`upload failed (${res.status}): ${detail}`);
        }
        const result = (await res.json()) as UploadResult;
        const uploadedCount = result.uploaded.length;
        const skippedCount = result.skipped.length;
        setStatus("ok");
        setMessage(
          skippedCount > 0
            ? `uploaded ${uploadedCount} dataset${uploadedCount === 1 ? "" : "s"}, skipped ${skippedCount}`
            : `uploaded ${uploadedCount} dataset${uploadedCount === 1 ? "" : "s"}`
        );
        router.refresh();
      } catch (err) {
        setStatus("error");
        setMessage((err as Error).message);
      }
    },
    [router]
  );

  async function onDrop(e: React.DragEvent) {
    const files = await collectFiles(e.dataTransfer);
    if (files.length > 0) upload(files);
  }

  return (
    <UploadDropzone
      title={
        <>
          drop a data folder (or <code className="font-mono">.csv</code> files) here
        </>
      }
      accept=".csv,text/csv"
      multiple
      chooseLabel="choose files"
      onFiles={upload}
      onDrop={onDrop}
      status={status}
      message={message}
    >
      expected filenames:{" "}
      <code className="font-mono">prices_round_&lt;N&gt;_day_&lt;M&gt;.csv</code> and{" "}
      <code className="font-mono">trades_round_&lt;N&gt;_day_&lt;M&gt;.csv</code>. the
      server pairs them by (round, day) and validates with the loader.
    </UploadDropzone>
  );
}
