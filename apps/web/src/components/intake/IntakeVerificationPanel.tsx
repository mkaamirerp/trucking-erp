/**
 * Load Intake — review actions, duplicate workflow, and thread actions only.
 * Editable load fields live in LoadWorkspaceForm (/loads/new, /loads/:id).
 */
import { type ChangeEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { EmailIntakeReviewBundle, InboxMessageAttachmentItem, InboxMessageItem } from "@/api";
import {
  dismissEmailThreadIntakeReview,
  duplicateIntakeReviewConfirm,
  duplicateIntakeReviewDismissFalsePositive,
  duplicateIntakeReviewLinkPrior,
  getEmailThreadIntakeReview,
  reopenEmailThreadIntakeReview,
  resolveEmailThreadIntakeReview,
} from "@/api";
import type { Load } from "@/api";
import {
  INTAKE_REVIEW_DISMISS_OPTIONS,
  INTAKE_REVIEW_REOPEN_OPTIONS,
  INTAKE_REVIEW_RESOLVE_OPTIONS,
  intakeReviewEventTypeLabel,
  intakeReviewReasonOperatorHint,
} from "@/constants/emailIntakeReviewReasonCodes";
import { OPS } from "@/routes";

export type IntakeKpis = {
  pendingReview: number;
  createdToday: number;
  awaitingCarrier: number;
  dispatchedWeek: number;
};

function findFirstPdf(messages: InboxMessageItem[]): { att: InboxMessageAttachmentItem; message: InboxMessageItem } | null {
  for (const m of messages) {
    for (const a of m.attachments ?? []) {
      if (a.mime_type?.includes("pdf") || (a.filename ?? "").toLowerCase().endsWith(".pdf")) {
        return { att: a, message: m };
      }
    }
  }
  return null;
}

function formatBytes(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function fieldClass() {
  return "w-full rounded-lg border border-[#334155] bg-[#0d111a] px-3 py-2 text-sm text-[#e8edf5] placeholder:text-[#64748b] focus:border-[#f5a623] focus:outline-none focus:ring-1 focus:ring-[#f5a623]/40";
}

type Props = {
  emailThreadId?: number | null;
  threadSubject: string | null;
  routingReason: string | null;
  messages: InboxMessageItem[];
  linkedLoad: Load | null;
  kpis: IntakeKpis;
  canReparse: boolean;
  recomputingIntake: boolean;
  onReparse: () => void;
  canVerifyCreate: boolean;
  draftCreating: boolean;
  onVerifyCreate: () => void;
  onManualEntry: () => void;
  uploadBusy?: boolean;
  onUploadDocumentChange: (e: ChangeEvent<HTMLInputElement>) => void;
  userEmail?: string | null;
  onClose?: () => void;
  onIntakeActionsComplete?: () => void | Promise<void>;
};

export function IntakeVerificationPanel({
  emailThreadId = null,
  threadSubject,
  routingReason,
  messages,
  linkedLoad,
  kpis,
  canReparse,
  recomputingIntake,
  onReparse,
  canVerifyCreate,
  draftCreating,
  onVerifyCreate,
  onManualEntry,
  uploadBusy = false,
  onUploadDocumentChange,
  userEmail = null,
  onClose,
  onIntakeActionsComplete,
}: Props) {
  const navigate = useNavigate();
  const uploadRef = useRef<HTMLInputElement>(null);
  const [reviewDetail, setReviewDetail] = useState<EmailIntakeReviewBundle | null>(null);
  const [dupBusy, setDupBusy] = useState(false);
  const [dupDismissNote, setDupDismissNote] = useState("");
  const [reviewWorkflowBusy, setReviewWorkflowBusy] = useState(false);
  const [resolveReason, setResolveReason] = useState(() => INTAKE_REVIEW_RESOLVE_OPTIONS[0]?.code ?? "");
  const [resolveNote, setResolveNote] = useState("");
  const [dismissReason, setDismissReason] = useState(() => INTAKE_REVIEW_DISMISS_OPTIONS[0]?.code ?? "");
  const [dismissNote, setDismissNote] = useState("");
  const [reopenReason, setReopenReason] = useState(() => INTAKE_REVIEW_REOPEN_OPTIONS[0]?.code ?? "");
  const [reopenNote, setReopenNote] = useState("");

  const reloadIntakeReview = useCallback(async () => {
    if (!emailThreadId) {
      setReviewDetail(null);
      return;
    }
    try {
      setReviewDetail(await getEmailThreadIntakeReview(emailThreadId));
    } catch {
      setReviewDetail(null);
    }
  }, [emailThreadId]);

  useEffect(() => {
    void reloadIntakeReview();
  }, [reloadIntakeReview]);

  useEffect(() => {
    setResolveReason(INTAKE_REVIEW_RESOLVE_OPTIONS[0]?.code ?? "");
    setDismissReason(INTAKE_REVIEW_DISMISS_OPTIONS[0]?.code ?? "");
    setReopenReason(INTAKE_REVIEW_REOPEN_OPTIONS[0]?.code ?? "");
    setResolveNote("");
    setDismissNote("");
    setReopenNote("");
  }, [emailThreadId]);

  useEffect(() => {
    setDupDismissNote("");
  }, [emailThreadId]);

  const pdf = useMemo(() => findFirstPdf(messages), [messages]);
  const ocrComplete = Boolean(pdf);

  const tagLine = (threadSubject || "").toLowerCase().includes("tql") ? "TQL" : null;

  const intakeTags = useMemo(() => {
    const tags: string[] = [];
    if (tagLine) tags.push(tagLine);
    const l = linkedLoad;
    if (!l) return tags;
    if (l.mode) tags.push(l.mode);
    const equip = [l.trailer_type, l.trailer_size].filter(Boolean).join(" ").trim();
    if (equip) tags.push(equip.replace(/\s+/g, " "));
    if (l.estimated_weight != null) tags.push(`${l.estimated_weight.toLocaleString()} lbs`);
    if (l.pallet_case_count?.trim()) tags.push(l.pallet_case_count.trim());
    if (l.hazmat_flag === false) tags.push("Non-hazmat");
    else if (l.hazmat_flag === true) tags.push("Hazardous");
    return tags;
  }, [tagLine, linkedLoad]);

  const duplicateReviewUi = useMemo(() => {
    const rev = reviewDetail?.review;
    const events = reviewDetail?.events ?? [];
    const eventTypes = new Set(events.map((e) => e.event_type));
    if (!rev || rev.primary_code !== "duplicate_pdf_sha256") return null;
    const d = rev.detail_json;
    const priorRaw =
      d && typeof d === "object" && d !== null && "prior_load_id" in d
        ? (d as { prior_load_id?: unknown }).prior_load_id
        : null;
    const suggestedPrior =
      priorRaw === null || priorRaw === undefined || priorRaw === "" ? null : Number(priorRaw);
    const sha =
      d && typeof d === "object" && d !== null && "content_sha256" in d
        ? String((d as { content_sha256?: unknown }).content_sha256 ?? "").trim()
        : "";
    const st = rev.status;
    const canLink = (st === "open" || st === "claimed") && suggestedPrior != null && Number.isFinite(suggestedPrior);
    const canDismiss = st === "open" || st === "claimed";
    const linkedId = linkedLoad?.id ?? null;
    const canConfirm =
      suggestedPrior != null &&
      Number.isFinite(suggestedPrior) &&
      linkedId != null &&
      Number(linkedId) === Number(suggestedPrior);
    const linkedToPrior =
      st === "resolved" &&
      eventTypes.has("duplicate_link_prior") &&
      eventTypes.has("auto_resolved_thread_linked_load") &&
      suggestedPrior != null &&
      linkedId != null &&
      Number(linkedId) === Number(suggestedPrior);
    const duplicateConfirmed = eventTypes.has("duplicate_confirmed");
    return {
      suggestedPrior,
      sha,
      canLink,
      canDismiss,
      canConfirm,
      status: st,
      linkedToPrior,
      duplicateConfirmed,
    };
  }, [reviewDetail, linkedLoad?.id]);

  const runDuplicateAction = async (fn: () => Promise<unknown>) => {
    if (!emailThreadId || dupBusy) return;
    setDupBusy(true);
    try {
      await fn();
      await onIntakeActionsComplete?.();
      await reloadIntakeReview();
    } finally {
      setDupBusy(false);
    }
  };

  const runReviewWorkflowAction = async (fn: () => Promise<unknown>) => {
    if (!emailThreadId || reviewWorkflowBusy) return;
    setReviewWorkflowBusy(true);
    try {
      await fn();
      await onIntakeActionsComplete?.();
      await reloadIntakeReview();
    } finally {
      setReviewWorkflowBusy(false);
    }
  };

  const kpiCards = useMemo(
    () => [
      {
        label: "Pending review",
        value: kpis.pendingReview,
        accent: "text-emerald-300",
        icon: (
          <svg className="h-5 w-5 text-emerald-400/90" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 10.5V6a3.75 3.75 0 10-7.5 0v4.5m11.356-1.993l1.263 12c.07.665-.45 1.243-1.119 1.243H4.25a1.125 1.125 0 01-1.12-1.243l1.264-12A1.125 1.125 0 015.513 7.5h12.974c.576 0 1.059.435 1.119 1.007zM8.25 10.5a.75.75 0 01.75.75v3a.75.75 0 01-1.5 0v-3a.75.75 0 01.75-.75z" />
          </svg>
        ),
      },
      {
        label: "Created today",
        value: kpis.createdToday,
        accent: "text-sky-300",
        icon: (
          <svg className="h-5 w-5 text-sky-400/90" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 12h8v5H8l-1.5 2H3v-7z" />
            <path strokeLinecap="round" strokeLinejoin="round" d="M11 12V8h3l4 4v4h-2.5" />
            <path strokeLinecap="round" d="M6.5 19.25a1.75 1.75 0 100-3.5 1.75 1.75 0 000 3.5z" />
            <path strokeLinecap="round" d="M17 19.25a1.75 1.75 0 100-3.5 1.75 1.75 0 000 3.5z" />
          </svg>
        ),
      },
      {
        label: "Awaiting carrier",
        value: kpis.awaitingCarrier,
        accent: "text-amber-300",
        icon: (
          <svg className="h-5 w-5 text-amber-400/90" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        ),
      },
      {
        label: "Dispatched this week",
        value: kpis.dispatchedWeek,
        accent: "text-violet-300",
        icon: (
          <svg className="h-5 w-5 text-violet-400/90" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        ),
      },
    ],
    [kpis.pendingReview, kpis.createdToday, kpis.awaitingCarrier, kpis.dispatchedWeek]
  );

  return (
    <div className="relative flex flex-col gap-5 text-[#e8edf5]">
      {onClose ? (
        <button
          type="button"
          onClick={onClose}
          className="absolute left-1/2 top-0 z-10 flex h-9 w-9 -translate-x-1/2 items-center justify-center rounded-full border border-[#334155] bg-[#0d111a] text-lg leading-none text-[#94a3b8] hover:bg-[#1e293b] hover:text-[#e8edf5]"
          aria-label="Close intake"
        >
          ×
        </button>
      ) : null}

      <div className={`flex flex-col gap-4 ${onClose ? "pt-10" : ""}`}>
        <div className="flex flex-col gap-4 border-b border-[#1e293b] pb-5">
          <div className="flex flex-col items-stretch gap-3 sm:flex-row sm:items-start sm:justify-end">
            {userEmail ? <p className="text-xs text-[#94a3b8] sm:order-first sm:mr-auto sm:pt-2 sm:text-left">{userEmail}</p> : null}
            <input ref={uploadRef} type="file" accept=".pdf,application/pdf" className="hidden" onChange={onUploadDocumentChange} />
            <div className="flex flex-wrap items-center justify-end gap-2">
              <button
                type="button"
                onClick={onManualEntry}
                className="rounded-lg border border-[#475569] bg-transparent px-3 py-2 text-sm font-medium text-[#e8edf5] hover:bg-[#1e293b]"
              >
                + Manual entry
              </button>
              <button
                type="button"
                onClick={() => uploadRef.current?.click()}
                disabled={uploadBusy}
                className="rounded-lg border border-[#2563eb] bg-[#1d4ed8] px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-[#2563eb] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {uploadBusy ? "Uploading…" : "Upload document"}
              </button>
              <button
                type="button"
                onClick={onVerifyCreate}
                disabled={!canVerifyCreate || draftCreating}
                className="rounded-lg border border-emerald-700/80 bg-emerald-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {draftCreating ? "Creating…" : "Verify & create load"}
              </button>
            </div>
          </div>
        </div>

        {linkedLoad ? (
          <div className="flex flex-col gap-2 rounded-xl border border-[#334155] bg-[#0d111a] px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-[#e8edf5]">
              Linked load{" "}
              <span className="font-mono font-semibold text-[#93c5fd]">{linkedLoad.load_number}</span>
              {linkedLoad.trip_number?.trim() ? (
                <span className="ml-2 text-xs text-[#64748b]">Trip {linkedLoad.trip_number.trim()}</span>
              ) : null}
            </p>
            <button
              type="button"
              onClick={() =>
                emailThreadId != null
                  ? navigate(OPS.LOAD_WORKSPACE_INTAKE(linkedLoad.id, emailThreadId))
                  : navigate(OPS.LOAD_DETAIL(linkedLoad.id))
              }
              className="shrink-0 rounded-lg border border-[#f5a623]/50 bg-[#f5a623]/10 px-3 py-2 text-xs font-semibold text-[#f5a623] hover:bg-[#f5a623]/20"
            >
              Open load workspace
            </button>
          </div>
        ) : null}

        {routingReason && routingReason !== "Not yet classified." ? (
          <div
            className="rounded-xl border border-amber-800/55 bg-amber-950/35 px-4 py-3 shadow-[inset_0_1px_0_0_rgba(251,191,36,0.06)]"
            role="status"
            title={routingReason}
          >
            <div className="text-[11px] font-semibold uppercase tracking-wide text-amber-200/95">
              Why this thread is in review
            </div>
            <p className="mt-2 text-sm leading-relaxed text-amber-50/95">{routingReason}</p>
          </div>
        ) : null}

        {reviewDetail?.review ? (
          <div className="rounded-xl border border-slate-700 bg-[#0a0e14] px-4 py-3">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">Structured review</div>
            <p className="mt-1 font-mono text-xs text-slate-200">
              <span className="text-slate-500">primary_code</span> {reviewDetail.review.primary_code}
            </p>
            <p className="mt-1 text-xs text-slate-400">
              Status: <span className="text-slate-200">{reviewDetail.review.status}</span>
              {reviewDetail.review.claimed_by_tenant_user_id != null ? (
                <span className="ml-2">· claimed by tenant_user_id {reviewDetail.review.claimed_by_tenant_user_id}</span>
              ) : null}
            </p>
            {duplicateReviewUi ? (
              <div className="mt-3 rounded-xl border border-amber-900/40 bg-amber-950/25 px-3 py-2">
                <div className="text-[11px] font-semibold uppercase tracking-wide text-amber-200/90">Duplicate PDF match</div>
                {duplicateReviewUi.suggestedPrior != null ? (
                  <p className="mt-1 text-xs text-amber-50/90">
                    Suggested prior load id:{" "}
                    <span className="font-mono text-amber-100">{duplicateReviewUi.suggestedPrior}</span>
                  </p>
                ) : (
                  <p className="mt-1 text-xs text-amber-200/80">No prior_load_id on review detail.</p>
                )}
                {duplicateReviewUi.sha ? (
                  <p className="mt-1 font-mono text-[10px] text-amber-100/70" title="Attachment content SHA-256">
                    sha256 {duplicateReviewUi.sha.slice(0, 16)}…
                  </p>
                ) : null}
                {duplicateReviewUi.status === "open" || duplicateReviewUi.status === "claimed" ? (
                  <p className="mt-2 text-xs leading-relaxed text-amber-100/85">
                    <span className="font-medium text-amber-200/95">Link to prior load</span> attaches this thread to the
                    suggested load and records that choice. The intake review then{" "}
                    <span className="font-medium text-amber-200/95">closes automatically</span> (system event). Use{" "}
                    <span className="font-medium text-amber-200/95">Confirm duplicate</span> afterward only if you want an
                    extra explicit acknowledgment on the audit trail.
                  </p>
                ) : null}
                {duplicateReviewUi.linkedToPrior && !duplicateReviewUi.duplicateConfirmed ? (
                  <div
                    className="mt-2 rounded-lg border border-sky-800/50 bg-sky-950/35 px-3 py-2 text-xs leading-relaxed text-sky-100/95"
                    role="status"
                  >
                    <span className="font-semibold text-sky-200/95">What happened:</span> this thread is linked to load{" "}
                    <span className="font-mono text-sky-100">{duplicateReviewUi.suggestedPrior}</span>. The duplicate intake
                    review was <span className="font-medium">resolved automatically</span> when the link was saved. If you
                    agree the PDF match is real, click <span className="font-medium">Confirm duplicate</span> below to add a
                    clear operator confirmation to the history (optional).
                  </div>
                ) : null}
                {duplicateReviewUi.duplicateConfirmed ? (
                  <p className="mt-2 rounded-lg border border-emerald-900/45 bg-emerald-950/30 px-3 py-2 text-xs text-emerald-100/90">
                    <span className="font-semibold text-emerald-200/95">Acknowledgment recorded.</span> Operator confirmed
                    this thread belongs with the suggested prior load. See “Activity” below for the full trail.
                  </p>
                ) : null}
                {duplicateReviewUi.status === "dismissed" ? (
                  <p className="mt-2 rounded-lg border border-slate-600/60 bg-slate-900/40 px-3 py-2 text-xs text-slate-300/95">
                    <span className="font-semibold text-slate-200/95">Review dismissed.</span> The duplicate signal was
                    treated as a false positive; link or create a load separately if this email still needs one.
                  </p>
                ) : null}
                <div className="mt-2 flex flex-col gap-2">
                  {duplicateReviewUi.canDismiss ? (
                    <input
                      type="text"
                      className={`${fieldClass()} max-w-md text-xs`}
                      placeholder="Optional note (dismiss only — reason is fixed as not duplicate)"
                      value={dupDismissNote}
                      onChange={(e) => setDupDismissNote(e.target.value)}
                      disabled={dupBusy}
                    />
                  ) : null}
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      disabled={!duplicateReviewUi.canLink || dupBusy}
                      onClick={() => runDuplicateAction(() => duplicateIntakeReviewLinkPrior(emailThreadId!, {}))}
                      className="rounded-lg border border-amber-700/70 bg-amber-900/30 px-3 py-1.5 text-xs font-semibold text-amber-100 hover:bg-amber-900/45 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      Link to prior load
                    </button>
                    <button
                      type="button"
                      disabled={!duplicateReviewUi.canConfirm || dupBusy}
                      onClick={() => runDuplicateAction(() => duplicateIntakeReviewConfirm(emailThreadId!))}
                      className="rounded-lg border border-emerald-800/60 bg-emerald-950/35 px-3 py-1.5 text-xs font-semibold text-emerald-100 hover:bg-emerald-950/50 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      Confirm duplicate (audit)
                    </button>
                    <button
                      type="button"
                      disabled={!duplicateReviewUi.canDismiss || dupBusy}
                      onClick={() =>
                        runDuplicateAction(() =>
                          duplicateIntakeReviewDismissFalsePositive(emailThreadId!, dupDismissNote.trim() || null),
                        )
                      }
                      className="rounded-lg border border-slate-600 bg-slate-900/50 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-800/60 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      Dismiss (false positive)
                    </button>
                  </div>
                </div>
              </div>
            ) : null}
            {(() => {
              const rev = reviewDetail.review;
              if (!rev) return null;
              const st = rev.status;
              const dup = duplicateReviewUi;
              const showGenericResolveDismiss = !dup && (st === "open" || st === "claimed");
              const showReopen = st === "resolved" || st === "dismissed";
              if (!showGenericResolveDismiss && !showReopen) return null;
              return (
                <div className="mt-3 space-y-3 rounded-lg border border-slate-600/50 bg-slate-950/35 px-3 py-3">
                  <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Review actions</div>
                  <p className="text-[10px] text-slate-500">
                    Reason is chosen from the list below (not typed). Optional note is free text only. Raw codes stay in
                    activity tooltips for legacy rows.
                  </p>
                  {showGenericResolveDismiss ? (
                    <div className="space-y-3">
                      <div className="flex flex-col gap-2 lg:flex-row lg:flex-wrap lg:items-end">
                        <label className="flex min-w-[200px] flex-1 flex-col gap-1 text-xs text-slate-400">
                          Resolve review
                          <select
                            className={fieldClass()}
                            value={resolveReason}
                            onChange={(e) => setResolveReason(e.target.value)}
                            disabled={reviewWorkflowBusy}
                          >
                            {INTAKE_REVIEW_RESOLVE_OPTIONS.map((o) => (
                              <option key={o.code} value={o.code}>
                                {o.label}
                              </option>
                            ))}
                          </select>
                        </label>
                        <input
                          type="text"
                          className={`${fieldClass()} min-w-[200px] flex-1`}
                          placeholder="Optional note"
                          value={resolveNote}
                          onChange={(e) => setResolveNote(e.target.value)}
                          disabled={reviewWorkflowBusy}
                        />
                        <button
                          type="button"
                          disabled={reviewWorkflowBusy || !resolveReason}
                          onClick={() =>
                            runReviewWorkflowAction(() =>
                              resolveEmailThreadIntakeReview(emailThreadId!, {
                                reason_code: resolveReason,
                                note: resolveNote.trim() || null,
                              }),
                            )
                          }
                          className="rounded-lg border border-emerald-800/60 bg-emerald-950/40 px-3 py-2 text-xs font-semibold text-emerald-100 hover:bg-emerald-950/55 disabled:cursor-not-allowed disabled:opacity-40"
                        >
                          {reviewWorkflowBusy ? "…" : "Resolve"}
                        </button>
                      </div>
                      <div className="flex flex-col gap-2 lg:flex-row lg:flex-wrap lg:items-end">
                        <label className="flex min-w-[200px] flex-1 flex-col gap-1 text-xs text-slate-400">
                          Dismiss review
                          <select
                            className={fieldClass()}
                            value={dismissReason}
                            onChange={(e) => setDismissReason(e.target.value)}
                            disabled={reviewWorkflowBusy}
                          >
                            {INTAKE_REVIEW_DISMISS_OPTIONS.map((o) => (
                              <option key={o.code} value={o.code}>
                                {o.label}
                              </option>
                            ))}
                          </select>
                        </label>
                        <input
                          type="text"
                          className={`${fieldClass()} min-w-[200px] flex-1`}
                          placeholder="Optional note"
                          value={dismissNote}
                          onChange={(e) => setDismissNote(e.target.value)}
                          disabled={reviewWorkflowBusy}
                        />
                        <button
                          type="button"
                          disabled={reviewWorkflowBusy || !dismissReason}
                          onClick={() =>
                            runReviewWorkflowAction(() =>
                              dismissEmailThreadIntakeReview(emailThreadId!, {
                                reason_code: dismissReason,
                                note: dismissNote.trim() || null,
                              }),
                            )
                          }
                          className="rounded-lg border border-slate-600 bg-slate-900/60 px-3 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-800/70 disabled:cursor-not-allowed disabled:opacity-40"
                        >
                          {reviewWorkflowBusy ? "…" : "Dismiss"}
                        </button>
                      </div>
                    </div>
                  ) : null}
                  {showReopen ? (
                    <div className="flex flex-col gap-2 lg:flex-row lg:flex-wrap lg:items-end">
                      <label className="flex min-w-[200px] flex-1 flex-col gap-1 text-xs text-slate-400">
                        Reopen review
                        <select
                          className={fieldClass()}
                          value={reopenReason}
                          onChange={(e) => setReopenReason(e.target.value)}
                          disabled={reviewWorkflowBusy}
                        >
                          {INTAKE_REVIEW_REOPEN_OPTIONS.map((o) => (
                            <option key={o.code} value={o.code}>
                              {o.label}
                            </option>
                          ))}
                        </select>
                      </label>
                      <input
                        type="text"
                        className={`${fieldClass()} min-w-[200px] flex-1`}
                        placeholder="Optional note"
                        value={reopenNote}
                        onChange={(e) => setReopenNote(e.target.value)}
                        disabled={reviewWorkflowBusy}
                      />
                      <button
                        type="button"
                        disabled={reviewWorkflowBusy || !reopenReason}
                        onClick={() =>
                          runReviewWorkflowAction(() =>
                            reopenEmailThreadIntakeReview(emailThreadId!, {
                              reason_code: reopenReason,
                              note: reopenNote.trim() || null,
                            }),
                          )
                        }
                        className="rounded-lg border border-sky-800/55 bg-sky-950/35 px-3 py-2 text-xs font-semibold text-sky-100 hover:bg-sky-950/50 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        {reviewWorkflowBusy ? "…" : "Reopen"}
                      </button>
                    </div>
                  ) : null}
                </div>
              );
            })()}
            {reviewDetail.events.length > 0 ? (
              <div className="mt-3">
                <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">Activity</div>
                <ul className="mt-1 max-h-52 overflow-auto text-[11px] text-slate-500">
                  {reviewDetail.events.slice(-12).map((ev) => {
                    const reasonHint = intakeReviewReasonOperatorHint(ev.reason_code);
                    const tip = [ev.event_type, ev.reason_code].filter(Boolean).join(" · ");
                    return (
                      <li key={ev.id} className="border-t border-slate-800/80 py-1.5 first:border-t-0" title={tip || undefined}>
                        <span className="text-slate-200">{intakeReviewEventTypeLabel(ev.event_type)}</span>
                        <span className="text-slate-600"> · {ev.actor_kind}</span>
                        {reasonHint ? <span className="text-slate-500"> · {reasonHint}</span> : null}
                        <span className="block text-[10px] text-slate-600">{new Date(ev.created_at).toLocaleString()}</span>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ) : null}
          </div>
        ) : null}

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {kpiCards.map((k) => (
            <div
              key={k.label}
              className="flex gap-3 rounded-xl border border-[#1e293b] bg-[#0d111a] px-3 py-3 shadow-[inset_0_1px_0_0_rgba(255,255,255,0.04)]"
            >
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-[#0a0e14]">{k.icon}</div>
              <div className="min-w-0">
                <div className={`text-2xl font-semibold tabular-nums leading-tight ${k.accent}`}>{k.value}</div>
                <div className="mt-1 text-[11px] font-medium uppercase tracking-wide text-[#64748b]">{k.label}</div>
              </div>
            </div>
          ))}
        </div>

        <div className="rounded-xl border border-[#1e293b] bg-[#0d111a] px-4 py-4">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="flex min-w-0 flex-1 gap-3">
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-[#1e293b] text-[#93c5fd]">
                <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                </svg>
              </div>
              <div className="min-w-0 flex-1">
                {pdf ? (
                  <>
                    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                      <span className="truncate text-sm font-semibold text-[#e8edf5]">{pdf.att.filename || "attachment.pdf"}</span>
                      <span className="text-xs text-[#64748b]">{formatBytes(pdf.att.size_bytes)}</span>
                    </div>
                    <p className="mt-1 text-xs font-medium text-emerald-400/90">Parsed successfully</p>
                  </>
                ) : (
                  <p className="text-sm text-[#64748b]">No PDF attachment on this thread yet.</p>
                )}
                {intakeTags.length > 0 ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {intakeTags.map((t) => (
                      <span key={t} className="rounded-full bg-[#1d4ed8]/22 px-2.5 py-0.5 text-[11px] font-medium text-[#93c5fd]">
                        {t}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            </div>
            <div className="flex shrink-0 flex-wrap items-center gap-2 border-t border-[#1e293b] pt-3 lg:border-t-0 lg:border-l lg:pl-4 lg:pt-0">
              <span
                className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm ${
                  ocrComplete ? "border-emerald-800/50 bg-emerald-950/40 text-emerald-300" : "border-[#334155] bg-[#0a0e14] text-[#64748b]"
                }`}
                title="Based on PDF attachment presence on this thread; server-side OCR status is not exposed yet"
              >
                {ocrComplete ? "✓ OCR complete" : "No PDF on thread"}
              </span>
              <button
                type="button"
                onClick={onReparse}
                disabled={!canReparse || recomputingIntake}
                className="rounded-lg border border-[#475569] bg-[#0f1420] px-3 py-2 text-sm font-medium text-[#94a3b8] hover:bg-[#1e293b] disabled:cursor-not-allowed disabled:opacity-40"
                title={!canReparse ? "Re-parse uses Gmail intake rules on this thread" : "Re-run PDF / intake classification"}
              >
                {recomputingIntake ? "Re-parsing…" : "Re-parse"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
