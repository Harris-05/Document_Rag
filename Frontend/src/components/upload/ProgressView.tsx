"use client";

import { CheckCircle, Circle, CircleNotch } from "@phosphor-icons/react";
import { Button } from "@/components/ui/Button";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { overallProgress, type UploadState } from "@/hooks/useUpload";
import { formatBytes, formatCount } from "@/lib/format";
import { FileBadge, kindFromName } from "./FileBadge";

type ActiveState = Extract<UploadState, { phase: "uploading" | "processing" }>;

type StageKey = "upload" | "extract" | "save";
type StageStatus = "done" | "active" | "pending";

const STAGES: { key: StageKey; label: string }[] = [
  { key: "upload", label: "Upload" },
  { key: "extract", label: "Extract text" },
  { key: "save", label: "Save to library" },
];

function activeStage(state: ActiveState): StageKey {
  if (state.phase === "uploading") return "upload";
  return state.document.stage === "saving" ? "save" : "extract";
}

function stageStatus(key: StageKey, current: StageKey): StageStatus {
  const order: StageKey[] = ["upload", "extract", "save"];
  const delta = order.indexOf(key) - order.indexOf(current);
  return delta < 0 ? "done" : delta === 0 ? "active" : "pending";
}

function describe(state: ActiveState): string {
  if (state.phase === "uploading") {
    const sent = Math.round(state.file.size * state.fraction);
    return `Uploading ${formatBytes(sent)} of ${formatBytes(state.file.size)}`;
  }
  const { stage, progress_done, progress_total } = state.document;
  if (stage === "saving") return "Saving to your library";
  if (progress_total && progress_total > 0) {
    return progress_done === 0
      ? `Opening a ${formatCount(progress_total)} page document`
      : `Reading page ${formatCount(progress_done)} of ${formatCount(progress_total)}`;
  }
  return "Reading the document text";
}

function StageIcon({ status }: { status: StageStatus }) {
  if (status === "done") return <CheckCircle size={18} weight="fill" className="text-success" aria-hidden />;
  if (status === "active")
    return <CircleNotch size={18} weight="bold" className="animate-spin text-accent motion-reduce:animate-none" aria-hidden />;
  return <Circle size={18} className="text-line-strong" aria-hidden />;
}

interface ProgressViewProps {
  state: ActiveState;
  onCancel: () => void;
}

export function ProgressView({ state, onCancel }: ProgressViewProps) {
  const current = activeStage(state);
  const progress = overallProgress(state);
  const detail = describe(state);

  return (
    <div className="flex min-h-[19rem] flex-col justify-between gap-8 rounded-card border border-line bg-surface p-6 shadow-card sm:p-8">
      <div className="flex items-center gap-3">
        <FileBadge kind={kindFromName(state.file.name)} size={44} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-[15px] font-medium text-ink" title={state.file.name}>
            {state.file.name}
          </p>
          <p className="text-[13px] text-ink-subtle">{formatBytes(state.file.size)}</p>
        </div>
        <p className="font-mono text-2xl font-medium tabular-nums text-ink">
          {Math.round(progress * 100)}
          <span className="text-base text-ink-subtle">%</span>
        </p>
      </div>

      <div className="flex flex-col gap-3">
        <ProgressBar value={progress} label={`Processing ${state.file.name}`} />
        <p className="text-sm text-ink-muted" role="status" aria-live="polite">
          {detail}
        </p>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-4">
        <ol className="flex flex-wrap items-center gap-x-5 gap-y-2">
          {STAGES.map(({ key, label }) => {
            const status = stageStatus(key, current);
            return (
              <li
                key={key}
                aria-current={status === "active" ? "step" : undefined}
                className={`flex items-center gap-2 text-sm ${
                  status === "pending" ? "text-ink-subtle" : "text-ink"
                }`}
              >
                <StageIcon status={status} />
                {label}
              </li>
            );
          })}
        </ol>
        {state.phase === "uploading" && (
          <Button variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        )}
      </div>
    </div>
  );
}
