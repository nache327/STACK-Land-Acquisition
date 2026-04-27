"use client";

import { useRef, useState } from "react";
import { api } from "@/lib/api";

interface ImportModalProps {
  onClose: () => void;
}

export function ImportModal({ onClose }: ImportModalProps) {
  const [status, setStatus] = useState<"idle" | "uploading" | "success" | "error">("idle");
  const [result, setResult] = useState<{ inserted: number; skipped: number; message: string } | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const upload = async (file: File) => {
    if (!file.name.toLowerCase().endsWith(".kmz")) {
      setErrorMsg("Please select a .kmz file.");
      setStatus("error");
      return;
    }

    setStatus("uploading");
    setErrorMsg(null);
    setResult(null);

    try {
      const res = await api.importKmz(file);
      setResult(res);
      setStatus("success");
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Upload failed");
      setStatus("error");
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) upload(file);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) upload(file);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="w-[440px] rounded-xl border border-slate-700 bg-slate-900 p-6 shadow-2xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-semibold text-white">Import Competitor KMZ</h2>
          <button
            onClick={onClose}
            className="rounded p-1 text-slate-400 hover:text-white"
          >
            ✕
          </button>
        </div>

        <p className="mb-4 text-xs text-slate-400">
          Upload your KMZ file to add competitor self-storage facilities to the map. Data is
          stored permanently — no need to re-upload on future sessions. Duplicate locations
          (within 200 ft of each other) are automatically merged.
        </p>

        {/* Drop zone */}
        {status !== "success" && (
          <div
            onDragEnter={() => setIsDragging(true)}
            onDragLeave={() => setIsDragging(false)}
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={[
              "cursor-pointer rounded-lg border-2 border-dashed p-8 text-center transition-colors",
              isDragging
                ? "border-emerald-500 bg-emerald-950/30"
                : "border-slate-600 hover:border-slate-500",
            ].join(" ")}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".kmz"
              onChange={handleFileChange}
              className="hidden"
            />
            {status === "uploading" ? (
              <div className="text-sm text-slate-400 animate-pulse">Uploading and parsing…</div>
            ) : (
              <>
                <div className="mb-1 text-2xl">📍</div>
                <div className="text-sm text-slate-300">
                  Drop your <span className="font-mono text-emerald-400">.kmz</span> file here
                </div>
                <div className="text-xs text-slate-500 mt-1">or click to browse</div>
              </>
            )}
          </div>
        )}

        {/* Success */}
        {status === "success" && result && (
          <div className="rounded-lg bg-emerald-950/50 border border-emerald-700 p-4 text-sm text-emerald-300">
            <div className="font-semibold mb-1">✓ Import complete</div>
            <div>{result.inserted.toLocaleString()} facilities added</div>
            {result.skipped > 0 && (
              <div className="text-emerald-500">{result.skipped} placemarks skipped (no coordinates)</div>
            )}
            <div className="mt-2 text-xs text-emerald-600">
              Reload the page to see the new competitors on the map (toggle the Competitors layer).
            </div>
          </div>
        )}

        {/* Error */}
        {status === "error" && errorMsg && (
          <div className="rounded-lg bg-red-950/50 border border-red-700 p-4 text-sm text-red-300">
            <div className="font-semibold mb-1">Upload failed</div>
            <div>{errorMsg}</div>
          </div>
        )}

        {/* Footer actions */}
        <div className="mt-4 flex justify-between items-center">
          <button
            onClick={async () => {
              if (!confirm("Delete all KMZ-imported competitors? This cannot be undone.")) return;
              try {
                const res = await api.clearKmzCompetitors();
                alert(`Deleted ${res.deleted} KMZ competitors.`);
              } catch {
                alert("Failed to clear KMZ data.");
              }
            }}
            className="text-xs text-slate-500 hover:text-red-400 transition-colors"
          >
            Clear all KMZ data
          </button>

          <button
            onClick={onClose}
            className="rounded-lg border border-slate-600 px-4 py-2 text-sm text-slate-300 hover:bg-slate-800"
          >
            {status === "success" ? "Close" : "Cancel"}
          </button>
        </div>
      </div>
    </div>
  );
}
