"use client";

/**
 * Zoning Verifier Chat Panel — Layer 3 interactive verification.
 * Accepts URL, pasted text, and image/screenshot uploads.
 * Streams responses from Claude with correction report rendering.
 */

import {
  useState,
  useRef,
  useCallback,
  useEffect,
  type ChangeEvent,
  type DragEvent,
  type KeyboardEvent,
} from "react";

// ── Types ─────────────────────────────────────────────────────────────────────

interface AttachedImage {
  id: string;
  base64: string;
  mediaType: string;
  previewUrl: string;
  name: string;
}

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  images?: AttachedImage[];
  timestamp: number;
}

interface CorrectionEntry {
  zone: string;
  use: string;
  correct_value: string;
  current_value?: string;
  evidence?: string;
  action: "UPDATE";
}

interface ZoningChatPanelProps {
  jurisdictionId?: string | null;
  cityName?: string;
  onClose: () => void;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function generateId() {
  return Math.random().toString(36).slice(2, 9);
}

function extractCorrectionReport(text: string): string | null {
  const start = text.indexOf("---CORRECTION REPORT---");
  const end = text.indexOf("---END CORRECTION REPORT---");
  if (start === -1 || end === -1) return null;
  return text.slice(start, end + "---END CORRECTION REPORT---".length);
}

function parseCorrectionJson(report: string): CorrectionEntry[] {
  try {
    // Match a JSON array that contains objects — skips [City Name, State] placeholders
    const match = report.match(/\[\s*\{[\s\S]*?\}\s*\]/);
    if (!match) return [];
    return JSON.parse(match[0]);
  } catch {
    return [];
  }
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      // Strip data URL prefix: "data:image/png;base64,..."
      resolve(result.split(",")[1]);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

const MAX_IMAGE_SIZE = 5 * 1024 * 1024; // 5 MB
const MAX_IMAGES = 4;

// ── Starter chips ─────────────────────────────────────────────────────────────
const STARTER_CHIPS = [
  "What zones allow self-storage by right?",
  "Is mini-warehouse conditional anywhere?",
  "What zones allow garage condos?",
  "Check backend for discrepancies",
];

// ── Main component ────────────────────────────────────────────────────────────

export function ZoningChatPanel({
  jurisdictionId,
  cityName,
  onClose,
}: ZoningChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [ordinanceUrl, setOrdinanceUrl] = useState("");
  const [ordinanceLabel, setOrdinanceLabel] = useState("");
  const [pastedText, setPastedText] = useState("");
  const [inputMode, setInputMode] = useState<"url" | "paste">("url");
  const [attachedImages, setAttachedImages] = useState<AttachedImage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isFetchingUrl, setIsFetchingUrl] = useState(false);
  const [fetchedOrdinanceText, setFetchedOrdinanceText] = useState("");
  const fetchedOrdinanceTextRef = useRef("");
  const [structuredTable, setStructuredTable] = useState<Record<string, unknown> | null>(null);
  const structuredTableRef = useRef<Record<string, unknown> | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [applyStatus, setApplyStatus] = useState<Record<string, string>>({});

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const sendMessageRef = useRef<(text: string, checkBackend?: boolean, ordinanceTextOverride?: string) => Promise<void>>(
    async () => {}
  );

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ── Image handling ─────────────────────────────────────────────────────────

  const addImages = useCallback(async (files: FileList | File[]) => {
    const fileArray = Array.from(files);
    const toAdd: AttachedImage[] = [];

    for (const file of fileArray) {
      if (toAdd.length + attachedImages.length >= MAX_IMAGES) break;

      if (!file.type.startsWith("image/")) {
        alert(`${file.name} is not an image file.`);
        continue;
      }
      if (file.size > MAX_IMAGE_SIZE) {
        alert(`${file.name} is over 5 MB. Try a cropped screenshot.`);
        continue;
      }

      const base64 = await fileToBase64(file);
      toAdd.push({
        id: generateId(),
        base64,
        mediaType: file.type,
        previewUrl: URL.createObjectURL(file),
        name: file.name,
      });
    }

    setAttachedImages((prev) => [...prev, ...toAdd]);
  }, [attachedImages]);

  const removeImage = useCallback((id: string) => {
    setAttachedImages((prev) => {
      const img = prev.find((i) => i.id === id);
      if (img) URL.revokeObjectURL(img.previewUrl);
      return prev.filter((i) => i.id !== id);
    });
  }, []);

  // Drag and drop
  const handleDragOver = (e: DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };
  const handleDragLeave = () => setIsDragging(false);
  const handleDrop = async (e: DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files.length > 0) {
      await addImages(e.dataTransfer.files);
    }
  };

  // ── Load ordinance URL ─────────────────────────────────────────────────────

  async function handleLoadUrl() {
    if (!ordinanceUrl.trim()) return;
    setIsFetchingUrl(true);
    setFetchedOrdinanceText("");
    fetchedOrdinanceTextRef.current = "";
    setStructuredTable(null);
    structuredTableRef.current = null;
    try {
      const res = await fetch(`/api/fetch-ordinance?url=${encodeURIComponent(ordinanceUrl)}`);
      const data = await res.json() as {
        text?: string;
        error?: string;
        via?: string;
        url?: string;
        structuredTable?: Record<string, unknown>;
      };
      if (data.error) {
        setOrdinanceLabel(`Error: ${data.error}`);
      } else {
        const text = data.text ?? "";
        setFetchedOrdinanceText(text);
        fetchedOrdinanceTextRef.current = text;

        // Capture structured table if PDF was parsed
        if (data.structuredTable) {
          setStructuredTable(data.structuredTable);
          structuredTableRef.current = data.structuredTable;
        }

        try {
          const u = new URL(data.url ?? ordinanceUrl);
          const viaLabel =
            data.via === "pdf-structured" ? " (PDF parsed)" :
            data.via === "pdf-low-confidence" ? " (PDF — low confidence, verify manually)" :
            data.via === "jina" || data.via === "jina-smart" ? " (JS rendered)" :
            data.via === "jina-partial" ? " (partial)" :
            data.via === "jina-failed" ? " (table not found — showing DB state)" : "";
          setOrdinanceLabel(u.hostname + u.pathname.slice(0, 40) + viaLabel);
        } catch {
          setOrdinanceLabel(ordinanceUrl.slice(0, 50));
        }
        sendMessageWithOrdinance(
          "Analyze this ordinance against the database and report all conflicts.",
          text || `[Ordinance URL provided: ${ordinanceUrl} — automatic fetch did not find the Table of Uses section]`,
        );
      }
    } catch {
      setOrdinanceLabel("Error: could not fetch URL");
    } finally {
      setIsFetchingUrl(false);
    }
  }

  // ── Send message ───────────────────────────────────────────────────────────

  // Wrapper that injects a specific ordinance text blob (avoids stale closure on auto-trigger)
  function sendMessageWithOrdinance(text: string, ordinanceText: string) {
    sendMessageRef.current(text, false, ordinanceText);
  }

  const sendMessage = useCallback(
    async (text: string, checkBackend = false, ordinanceTextOverride?: string) => {
      const userText = text.trim();
      if (!userText && attachedImages.length === 0) return;
      if (isLoading) return;

      const userMsg: ChatMessage = {
        id: generateId(),
        role: "user",
        content: userText,
        images: attachedImages.length > 0 ? [...attachedImages] : undefined,
        timestamp: Date.now(),
      };

      const newMessages = [...messages, userMsg];
      setMessages(newMessages);
      setInput("");
      setAttachedImages([]);
      setIsLoading(true);

      // Placeholder for streaming response
      const assistantId = generateId();
      setMessages((prev) => [
        ...prev,
        {
          id: assistantId,
          role: "assistant",
          content: "",
          timestamp: Date.now(),
        },
      ]);

      try {
        const res = await fetch("/api/zoning-chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            messages: newMessages.map((m) => ({
              role: m.role,
              content: m.content,
            })),
            ordinanceUrl: ordinanceLabel ? ordinanceUrl : undefined,
            pastedText: ordinanceTextOverride ?? (fetchedOrdinanceTextRef.current || (inputMode === "paste" ? pastedText : undefined)),
            images: userMsg.images?.map((img) => ({
              base64: img.base64,
              mediaType: img.mediaType,
            })),
            jurisdictionId,
            checkBackend: checkBackend || userText.toLowerCase().includes("check backend"),
            structuredTable: structuredTableRef.current ?? undefined,
          }),
        });

        if (!res.ok) {
          const errText = await res.text().catch(() => "");
          let errMsg = `API error ${res.status}`;
          try { errMsg = (JSON.parse(errText) as { error?: string }).error ?? errMsg; } catch { /* not JSON — use status code */ }
          throw new Error(errMsg);
        }

        // Stream the response — update the message bubble as chunks arrive
        const reader = res.body!.getReader();
        const decoder = new TextDecoder();
        let fullText = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          fullText += decoder.decode(value, { stream: true });
          const snapshot = fullText;
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, content: snapshot } : m
            )
          );
        }
      } catch (err) {
        const errMsg = err instanceof Error ? err.message : "Request failed";
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: `Error: ${errMsg}` }
              : m
          )
        );
      } finally {
        setIsLoading(false);
        // If assistant message is still empty after stream ends, show fallback
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId && m.content === ""
              ? { ...m, content: "No response received. The request may have timed out — try again or paste the ordinance text directly." }
              : m
          )
        );
      }
    },
    [
      messages,
      attachedImages,
      isLoading,
      ordinanceUrl,
      ordinanceLabel,
      pastedText,
      inputMode,
      jurisdictionId,
      structuredTable,
    ]
  );

  // Keep sendMessageRef pointing at the latest sendMessage (used by handleLoadUrl auto-trigger)
  useEffect(() => {
    sendMessageRef.current = sendMessage;
  }, [sendMessage]);

  // ── Apply correction ───────────────────────────────────────────────────────

  const applyCorrection = useCallback(
    async (messageId: string, report: string) => {
      if (!jurisdictionId) return;
      setApplyStatus((prev) => ({ ...prev, [messageId]: "applying" }));

      const corrections = parseCorrectionJson(report);
      if (corrections.length === 0) {
        setApplyStatus((prev) => ({ ...prev, [messageId]: "error: no corrections parsed" }));
        return;
      }

      try {
        const res = await fetch("/api/apply-correction", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            jurisdictionId,
            corrections,
            source: ordinanceUrl || "user session",
            verifiedDate: new Date().toISOString().slice(0, 10),
          }),
        });
        const data = await res.json();
        setApplyStatus((prev) => ({
          ...prev,
          [messageId]: res.ok ? `done:${data.message}` : `error:${data.error}`,
        }));
      } catch (err) {
        setApplyStatus((prev) => ({
          ...prev,
          [messageId]: `error:${err instanceof Error ? err.message : "Failed"}`,
        }));
      }
    },
    [jurisdictionId, ordinanceUrl]
  );

  // ── Copy for VS Code ───────────────────────────────────────────────────────

  function copyForVsCode(report: string) {
    const prompt = `The following zoning corrections have been verified against ${cityName ?? "this city"}'s municipal code${ordinanceUrl ? ` (${ordinanceUrl})` : ""}. Apply these fixes to the Site Scout backend:

${report}

Specifically:
1. For each correction in the JSON, call PATCH /api/jurisdictions/{jurisdictionId}/zones/{zone_code} with the correct value, classification_source="human", human_reviewed=true
2. The jurisdiction ID is: ${jurisdictionId ?? "[set jurisdictionId]"}
3. After applying, verify the zone_use_matrix reflects the corrections

Source: ${ordinanceUrl || "user session"}
Verified: ${new Date().toISOString().slice(0, 10)}`;

    navigator.clipboard.writeText(prompt).catch(() => {});
  }

  // ── Keyboard handler ───────────────────────────────────────────────────────

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <aside
      className={[
        "fixed inset-y-0 right-0 z-50 flex w-[520px] flex-col border-l border-slate-200 bg-white shadow-2xl",
        isDragging ? "ring-2 ring-inset ring-emerald-400" : "",
      ].join(" ")}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Header */}
      <header className="flex shrink-0 items-center justify-between border-b border-slate-200 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-slate-900">
            Zoning Verifier
          </span>
          {cityName && (
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">
              {cityName}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => sendMessage("Check backend for discrepancies", true)}
            disabled={isLoading}
            className="rounded-md border border-amber-300 bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-700 hover:bg-amber-100 disabled:opacity-50"
            title="Compare ordinance against backend data"
          >
            ⚡ Check Backend
          </button>
          <button
            onClick={onClose}
            className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
          >
            ✕
          </button>
        </div>
      </header>

      {/* Ordinance source bar */}
      <div className="shrink-0 border-b border-slate-100 bg-slate-50 px-4 py-2">
        <div className="flex gap-2 mb-1.5">
          <button
            onClick={() => setInputMode("url")}
            className={[
              "rounded px-2 py-0.5 text-xs font-medium",
              inputMode === "url"
                ? "bg-slate-200 text-slate-800"
                : "text-slate-500 hover:text-slate-700",
            ].join(" ")}
          >
            URL
          </button>
          <button
            onClick={() => setInputMode("paste")}
            className={[
              "rounded px-2 py-0.5 text-xs font-medium",
              inputMode === "paste"
                ? "bg-slate-200 text-slate-800"
                : "text-slate-500 hover:text-slate-700",
            ].join(" ")}
          >
            Paste Text
          </button>
        </div>

        {inputMode === "url" ? (
          <div className="flex gap-1.5">
            <input
              type="url"
              value={ordinanceUrl}
              onChange={(e) => setOrdinanceUrl(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleLoadUrl()}
              placeholder="Paste ordinance URL…"
              className="min-w-0 flex-1 rounded border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-800 placeholder-slate-400 focus:border-emerald-400 focus:outline-none"
            />
            <button
              onClick={handleLoadUrl}
              disabled={isFetchingUrl}
              className="shrink-0 rounded bg-slate-700 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-800 disabled:opacity-50"
            >
              {isFetchingUrl ? "Loading…" : "Load"}
            </button>
          </div>
        ) : (
          <textarea
            value={pastedText}
            onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setPastedText(e.target.value)}
            placeholder="Paste ordinance text here…"
            rows={3}
            className="w-full rounded border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-800 placeholder-slate-400 focus:border-emerald-400 focus:outline-none resize-none"
          />
        )}

        {ordinanceLabel && (
          <p className="mt-1 text-[10px] text-emerald-700">
            ● Loaded: {ordinanceLabel}
          </p>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full gap-3 py-8">
            <p className="text-xs text-slate-400 text-center">
              Drop a URL, paste text, or upload a screenshot of a zoning table or map
            </p>
            <div className="flex flex-wrap justify-center gap-2">
              {STARTER_CHIPS.map((chip) => (
                <button
                  key={chip}
                  onClick={() => sendMessage(chip)}
                  className="rounded-full border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:border-emerald-300 hover:bg-emerald-50 hover:text-emerald-700 transition-colors"
                >
                  {chip}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <MessageBubble
            key={msg.id}
            message={msg}
            isLoading={isLoading && msg === messages[messages.length - 1] && msg.role === "assistant" && msg.content === ""}
            applyStatus={applyStatus[msg.id]}
            onApplyCorrection={
              jurisdictionId
                ? (report) => applyCorrection(msg.id, report)
                : undefined
            }
            onCopyForVsCode={copyForVsCode}
          />
        ))}

        {/* Typing indicator */}
        {isLoading && messages[messages.length - 1]?.content === "" && (
          <div className="flex gap-1 px-1">
            {[0, 1, 2].map((i) => (
              <span
                key={i}
                className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-bounce"
                style={{ animationDelay: `${i * 150}ms` }}
              />
            ))}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Image thumbnails */}
      {attachedImages.length > 0 && (
        <div className="shrink-0 flex items-center gap-2 border-t border-slate-100 bg-slate-50 px-4 py-2">
          <span className="text-[10px] text-slate-500">
            {attachedImages.length} image{attachedImages.length !== 1 ? "s" : ""} attached
          </span>
          {attachedImages.map((img) => (
            <div key={img.id} className="relative">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={img.previewUrl}
                alt={img.name}
                className="h-12 w-12 rounded border border-slate-200 object-cover"
              />
              <button
                onClick={() => removeImage(img.id)}
                className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[8px] text-white hover:bg-red-600"
              >
                ✕
              </button>
            </div>
          ))}
          <button
            onClick={() => setAttachedImages([])}
            className="ml-auto text-[10px] text-slate-400 hover:text-slate-600"
          >
            Clear all
          </button>
        </div>
      )}

      {/* Input bar */}
      <div className="shrink-0 border-t border-slate-200 bg-white px-3 py-3">
        {isDragging && (
          <div className="mb-2 rounded border-2 border-dashed border-emerald-400 bg-emerald-50 px-3 py-2 text-center text-xs text-emerald-700">
            Drop image to attach
          </div>
        )}
        <div className="flex items-end gap-2">
          {/* Hidden file input */}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            multiple
            className="hidden"
            onChange={async (e: ChangeEvent<HTMLInputElement>) => {
              if (e.target.files) await addImages(e.target.files);
              e.target.value = "";
            }}
          />

          {/* Paperclip */}
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={attachedImages.length >= MAX_IMAGES}
            className="shrink-0 rounded p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600 disabled:opacity-30"
            title="Attach image or screenshot"
          >
            📎
          </button>

          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask anything about this city's zoning…"
            rows={1}
            className="min-h-[36px] flex-1 resize-none rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-800 placeholder-slate-400 focus:border-emerald-400 focus:outline-none"
            style={{ maxHeight: "120px" }}
          />

          <button
            onClick={() => sendMessage(input)}
            disabled={isLoading || (!input.trim() && attachedImages.length === 0)}
            className="shrink-0 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-40"
          >
            →
          </button>
        </div>
      </div>
    </aside>
  );
}

// ── Message bubble ────────────────────────────────────────────────────────────

function MessageBubble({
  message,
  isLoading,
  applyStatus,
  onApplyCorrection,
  onCopyForVsCode,
}: {
  message: ChatMessage;
  isLoading: boolean;
  applyStatus?: string;
  onApplyCorrection?: (report: string) => void;
  onCopyForVsCode: (report: string) => void;
}) {
  const isUser = message.role === "user";
  const correctionReport = !isUser
    ? extractCorrectionReport(message.content)
    : null;

  const textBeforeReport = correctionReport
    ? message.content.slice(0, message.content.indexOf("---CORRECTION REPORT---"))
    : message.content;
  const textAfterReport = correctionReport
    ? message.content.slice(
        message.content.indexOf("---END CORRECTION REPORT---") +
          "---END CORRECTION REPORT---".length
      )
    : "";

  return (
    <div className={["flex gap-2", isUser ? "justify-end" : "justify-start"].join(" ")}>
      {!isUser && (
        <div className="mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-[10px]">
          🎯
        </div>
      )}

      <div className={["max-w-[90%] space-y-2", isUser ? "items-end" : "items-start"].join(" ")}>
        {/* User images */}
        {isUser && message.images && message.images.length > 0 && (
          <div className="flex flex-wrap gap-1 justify-end">
            {message.images.map((img) => (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                key={img.id}
                src={img.previewUrl}
                alt={img.name}
                className="h-20 w-20 rounded border border-slate-200 object-cover cursor-pointer hover:opacity-90"
                onClick={() => window.open(img.previewUrl, "_blank")}
              />
            ))}
          </div>
        )}

        {/* Main text */}
        {(textBeforeReport || (!correctionReport && message.content)) && (
          <div
            className={[
              "rounded-xl px-3.5 py-2.5 text-sm leading-relaxed",
              isUser
                ? "bg-emerald-600 text-white"
                : "border-l-2 border-emerald-300 bg-slate-50 text-slate-800",
            ].join(" ")}
          >
            {isLoading ? (
              <span className="text-slate-400">…</span>
            ) : (
              <FormattedText text={isUser ? message.content : textBeforeReport} />
            )}
          </div>
        )}

        {/* Correction report block */}
        {correctionReport && (
          <CorrectionReportBlock
            report={correctionReport}
            applyStatus={applyStatus}
            onApply={onApplyCorrection}
            onCopy={onCopyForVsCode}
          />
        )}

        {/* Text after report */}
        {textAfterReport.trim() && (
          <div className="border-l-2 border-emerald-300 bg-slate-50 rounded-xl px-3.5 py-2.5 text-sm leading-relaxed text-slate-800">
            <FormattedText text={textAfterReport} />
          </div>
        )}
      </div>
    </div>
  );
}

// ── Correction report block ───────────────────────────────────────────────────

function CorrectionReportBlock({
  report,
  applyStatus,
  onApply,
  onCopy,
}: {
  report: string;
  applyStatus?: string;
  onApply?: (report: string) => void;
  onCopy: (report: string) => void;
}) {
  const isDone = applyStatus?.startsWith("done:");
  const isError = applyStatus?.startsWith("error:");
  const isApplying = applyStatus === "applying";
  const statusMsg = applyStatus?.replace(/^(done:|error:)/, "");

  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 overflow-hidden">
      <div className="flex items-center gap-2 border-b border-amber-200 bg-amber-100 px-3 py-2">
        <span className="text-amber-700">⚠️</span>
        <span className="text-xs font-semibold text-amber-800">Correction Report</span>
      </div>
      <pre className="overflow-x-auto p-3 text-[10px] leading-relaxed text-amber-900 font-mono whitespace-pre-wrap">
        {report}
      </pre>
      <div className="flex gap-2 border-t border-amber-200 bg-amber-100 px-3 py-2">
        {onApply && !isDone && (
          <button
            onClick={() => onApply(report)}
            disabled={isApplying}
            className="rounded bg-amber-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-amber-700 disabled:opacity-50"
          >
            {isApplying ? "Applying…" : "Apply Correction"}
          </button>
        )}
        {isDone && (
          <span className="rounded bg-emerald-100 px-2.5 py-1 text-xs font-medium text-emerald-700">
            ✓ Applied
          </span>
        )}
        <button
          onClick={() => onCopy(report)}
          className="rounded border border-amber-300 bg-white px-2.5 py-1 text-xs font-medium text-amber-700 hover:bg-amber-50"
        >
          📋 Copy for VS Code
        </button>
      </div>
      {(isDone || isError) && statusMsg && (
        <p
          className={[
            "px-3 py-1.5 text-[10px]",
            isDone ? "text-emerald-700 bg-emerald-50" : "text-red-700 bg-red-50",
          ].join(" ")}
        >
          {statusMsg}
        </p>
      )}
    </div>
  );
}

// ── Formatted text renderer ───────────────────────────────────────────────────

function FormattedText({ text }: { text: string }) {
  // Split into lines and render with basic markdown-ish formatting
  const lines = text.split("\n");
  return (
    <>
      {lines.map((line, i) => {
        // Bold **text**
        const parts = line.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
        return (
          <span key={i}>
            {parts.map((part, j) => {
              if (part.startsWith("**") && part.endsWith("**")) {
                return <strong key={j}>{part.slice(2, -2)}</strong>;
              }
              if (part.startsWith("`") && part.endsWith("`")) {
                return (
                  <code key={j} className="rounded bg-slate-200 px-1 py-0.5 font-mono text-[11px] text-slate-700">
                    {part.slice(1, -1)}
                  </code>
                );
              }
              return <span key={j}>{part}</span>;
            })}
            {i < lines.length - 1 && <br />}
          </span>
        );
      })}
    </>
  );
}
