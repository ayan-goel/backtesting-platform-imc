"use client";

import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import { UploadDropzone, type UploadStatus } from "@/components/ui/upload-dropzone";

export function StrategyUpload() {
  const router = useRouter();
  const [status, setStatus] = useState<UploadStatus>("idle");
  const [message, setMessage] = useState<string | null>(null);

  const upload = useCallback(
    async (files: File[]) => {
      const file = files[0];
      if (!file) return;
      setStatus("uploading");
      setMessage(null);

      const fd = new FormData();
      fd.append("file", file);

      try {
        const res = await fetch("/api/strategies", { method: "POST", body: fd });
        if (!res.ok) {
          const detail = await res.text();
          throw new Error(`upload failed (${res.status}): ${detail}`);
        }
        const doc = (await res.json()) as { _id: string };
        setStatus("ok");
        setMessage(`uploaded ${doc._id}`);
        router.refresh();
      } catch (err) {
        setStatus("error");
        setMessage((err as Error).message);
      }
    },
    [router]
  );

  return (
    <UploadDropzone
      title={
        <>
          drop a <code className="font-mono">.py</code> file here
        </>
      }
      accept=".py,text/x-python"
      onFiles={upload}
      status={status}
      message={message}
    >
      must define a <code className="font-mono">Trader</code> class with a{" "}
      <code className="font-mono">run(state)</code> method. the platform validates the
      upload by actually loading it.
    </UploadDropzone>
  );
}
