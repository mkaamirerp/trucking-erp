import { type ChangeEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  createDraftLoadFromEmailThread,
  disregardEmailThread,
  recomputeEmailThreadIntake,
  getEmailThread,
  getEmailThreadMessages,
  getLoad,
  InboxMessageItem,
  InboxThreadDetail,
  InboxThreadListItem,
  linkLoadToEmailThread,
  listEmailThreads,
  listLoads,
  pullGmailDeltaFromInbox,
  uploadPdfToEmailThread,
  type Load,
} from "../api";
import { IntakeVerificationPanel, type IntakeKpis } from "../components/intake/IntakeVerificationPanel";
import { OPS } from "../routes";
import { useMe } from "../hooks/useMe";
import { useOperationalRefresh } from "@/core/concurrency/useOperationalRefresh";
import { formatRoutingReason } from "../utils/emailIntakeRoutingReason";

function formatWhen(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString();
}

function participantPreview(raw: unknown): string {
  if (!raw) return "No participants";
  if (Array.isArray(raw)) {
    const values = raw
      .map((v) => {
        if (typeof v === "string") return v;
        if (v && typeof v === "object" && "email" in v) return String((v as { email?: unknown }).email ?? "");
        return "";
      })
      .filter(Boolean);
    return values.length ? values.slice(0, 2).join(", ") : "No participants";
  }
  return "Participants available";
}

function recipientPreview(raw: unknown): string {
  if (!raw) return "—";
  if (Array.isArray(raw)) {
    const values = raw
      .map((v) => {
        if (typeof v === "string") return v;
        if (v && typeof v === "object" && "email" in v) return String((v as { email?: unknown }).email ?? "");
        return "";
      })
      .filter(Boolean);
    return values.length ? values.join(", ") : "—";
  }
  return "—";
}

function confidenceLabel(level: string | null | undefined): string {
  if (!level) return "—";
  return level.charAt(0).toUpperCase() + level.slice(1).toLowerCase();
}

function confidenceClass(level: string | null | undefined): string {
  const l = (level || "").toLowerCase();
  if (l === "high") return "border-[var(--trk-success)] bg-[var(--trk-surface)] text-[var(--trk-success)]";
  if (l === "medium") return "border-[var(--trk-warning)] bg-[var(--trk-surface)] text-[var(--trk-warning)]";
  return "border-[var(--trk-border)] bg-[var(--trk-surface)] text-[var(--trk-text-muted)]";
}

function ThreadMessageList({
  loadingMessages,
  messagesError,
  selectedThreadId,
  messages,
}: {
  loadingMessages: boolean;
  messagesError: string | null;
  selectedThreadId: number | null;
  messages: InboxMessageItem[];
}) {
  return (
    <>
      {loadingMessages && selectedThreadId ? (
        <div className="text-sm text-[var(--trk-text-muted)]">Loading messages…</div>
      ) : null}
      {!loadingMessages && messagesError ? <div className="text-sm text-red-400">{messagesError}</div> : null}
      {!loadingMessages && !messagesError && selectedThreadId && messages.length === 0 ? (
        <div className="text-sm text-[var(--trk-text-muted)]">No messages in this thread.</div>
      ) : null}
      {!loadingMessages && !messagesError
        ? messages.map((m) => {
            const outbound = (m.direction || "").toLowerCase() === "outbound";
            return (
              <div key={m.id} className={`mb-4 flex ${outbound ? "justify-end" : "justify-start"}`}>
                <article
                  className={`w-full max-w-[820px] rounded-xl border p-4 ${
                    outbound ? "border-[var(--trk-accent)] bg-[var(--trk-surface)]" : "border-[var(--trk-border)] bg-[var(--trk-surface)]"
                  }`}
                >
                  <div className="mb-2 grid gap-1 text-xs text-[var(--trk-text-muted)] md:grid-cols-2">
                    <span>From: {m.from_email || "—"}</span>
                    <span className="md:text-right">{formatWhen(m.received_at || m.sent_at || m.created_at)}</span>
                    <span className="md:col-span-2">To: {recipientPreview(m.to_json)}</span>
                    {m.subject ? <span className="md:col-span-2">Subject: {m.subject}</span> : null}
                  </div>
                  <p className="whitespace-pre-wrap text-sm leading-6 text-[var(--trk-text)]">
                    {m.body_text || m.snippet || "No message body available."}
                  </p>
                  {m.attachments && m.attachments.length > 0 ? (
                    <ul className="mt-2 space-y-1 text-xs text-[var(--trk-text-muted)]">
                      {m.attachments.map((a) => (
                        <li key={a.id}>
                          <span className="text-[var(--trk-text)]">{a.filename || a.external_attachment_id}</span>
                          {a.mime_type ? <span className="text-[var(--trk-text-muted)]"> · {a.mime_type}</span> : null}
                          {a.size_bytes != null ? <span className="text-[var(--trk-text-muted)]"> · {a.size_bytes} bytes</span> : null}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  {m.has_attachments && (!m.attachments || m.attachments.length === 0) ? (
                    <p className="mt-2 text-xs text-[var(--trk-text-muted)]">Has attachments (metadata pending or inline-only).</p>
                  ) : null}
                </article>
              </div>
            );
          })
        : null}
    </>
  );
}

function threadIntakePrimaryLabel(t: InboxThreadListItem): string {
  const s = (t.subject || "").toLowerCase();
  if (/rate\s*con|rate\s*confirmation|\brc\b|^fw:/i.test(s) || /tql/i.test(s)) return "Rate confirmation";
  return t.subject || "(No subject)";
}

export default function LoadInboxPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { me } = useMe();
  const isEmailLoadRoute = location.pathname.startsWith(OPS.EMAIL_LOAD);
  const pageTitle = isEmailLoadRoute ? "Email load" : "Load Intake";
  const pageSubtitle = isEmailLoadRoute
    ? "Gmail threads, sync, and broker-mail intake queues."
    : "Create and verify incoming loads.";
  const pathForKpisRef = useRef(location.pathname);
  pathForKpisRef.current = location.pathname;
  const emailUploadRef = useRef<HTMLInputElement>(null);
  const [provider, setProvider] = useState<string>("");
  const [status, setStatus] = useState<string>("active");
  const [queueFocus, setQueueFocus] = useState<"intake" | "linked">("intake");
  const [bandNewLoads, setBandNewLoads] = useState<InboxThreadListItem[]>([]);
  const [bandNeedsReview, setBandNeedsReview] = useState<InboxThreadListItem[]>([]);
  const [bandBackground, setBandBackground] = useState<InboxThreadListItem[]>([]);
  const [flatThreads, setFlatThreads] = useState<InboxThreadListItem[]>([]);
  const [selectedThreadId, setSelectedThreadId] = useState<number | null>(null);
  const [threadDetail, setThreadDetail] = useState<InboxThreadDetail | null>(null);
  const [messages, setMessages] = useState<InboxMessageItem[]>([]);
  const [loadingThreads, setLoadingThreads] = useState<boolean>(true);
  const [loadingMessages, setLoadingMessages] = useState<boolean>(false);
  const [threadsError, setThreadsError] = useState<string | null>(null);
  const [messagesError, setMessagesError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [disregarding, setDisregarding] = useState<boolean>(false);
  const [draftCreating, setDraftCreating] = useState<boolean>(false);
  const [linkModalOpen, setLinkModalOpen] = useState<boolean>(false);
  const [linkSearch, setLinkSearch] = useState<string>("");
  const [linkResults, setLinkResults] = useState<Load[]>([]);
  const [linkLoading, setLinkLoading] = useState<boolean>(false);
  const [linkSubmitting, setLinkSubmitting] = useState<boolean>(false);
  const [recomputingIntake, setRecomputingIntake] = useState<boolean>(false);
  const [pullingGmailDelta, setPullingGmailDelta] = useState<boolean>(false);
  const [uploadingPdf, setUploadingPdf] = useState<boolean>(false);
  const [linkedLoadDetail, setLinkedLoadDetail] = useState<Load | null>(null);
  const [loadingLinkedLoad, setLoadingLinkedLoad] = useState<boolean>(false);
  const [intakeKpis, setIntakeKpis] = useState<IntakeKpis>({
    pendingReview: 0,
    createdToday: 0,
    awaitingCarrier: 0,
    dispatchedWeek: 0,
  });

  const isBandView = status === "active" && queueFocus === "intake";
  const isLinkedOnlyView = status === "active" && queueFocus === "linked";

  const allThreads = useMemo(() => {
    if (isBandView) return [...bandNewLoads, ...bandNeedsReview, ...bandBackground];
    return flatThreads;
  }, [isBandView, bandNewLoads, bandNeedsReview, bandBackground, flatThreads]);

  const pickNextSelectionId = (
    items: InboxThreadListItem[],
    opts?: { keepSelection?: boolean; retainSelectionId?: number }
  ): number | null => {
    if (opts?.retainSelectionId != null) {
      return opts.retainSelectionId;
    }
    if (items.length === 0) return null;
    const keep = opts?.keepSelection && selectedThreadId && items.some((t) => t.id === selectedThreadId);
    return keep ? selectedThreadId! : items[0].id;
  };

  const refreshIntakeKpis = useCallback(async () => {
    try {
      const prov = provider || undefined;
      const [rq, loadsPage] = await Promise.all([
        listEmailThreads({
          provider: prov,
          status: "active",
          intake_bucket: "needs_review",
          page: 1,
          size: 1,
        }),
        listLoads({ page: 1, size: 200 }),
      ]);
      const items = loadsPage.items ?? [];
      const startOfDay = new Date();
      startOfDay.setHours(0, 0, 0, 0);
      const weekAgo = new Date();
      weekAgo.setDate(weekAgo.getDate() - 7);
      weekAgo.setHours(0, 0, 0, 0);
      const createdToday = items.filter((l) => l.created_at && new Date(l.created_at) >= startOfDay).length;
      const awaitingCarrier = items.filter((l) => {
        const s = (l.status || "").toLowerCase();
        return s === "ready" || s === "unassigned";
      }).length;
      const dispatchedWeek = items.filter((l) => {
        const s = (l.status || "").toLowerCase();
        if (s !== "dispatched") return false;
        const t = l.updated_at ? new Date(l.updated_at) : null;
        return Boolean(t && t >= weekAgo);
      }).length;
      setIntakeKpis({
        pendingReview: rq.total ?? 0,
        createdToday,
        awaitingCarrier,
        dispatchedWeek,
      });
    } catch {
      /* keep last good KPIs */
    }
  }, [provider]);

  const loadThreads = async (opts?: {
    keepSelection?: boolean;
    retainSelectionId?: number;
    silent?: boolean;
  }) => {
    const silent = opts?.silent ?? false;
    if (!silent) setLoadingThreads(true);
    setThreadsError(null);
    setActionError(null);
    try {
      if (isBandView) {
        const [nr, rq, bg] = await Promise.all([
          listEmailThreads({
            provider: provider || undefined,
            status: "active",
            intake_bucket: "new_load",
            page: 1,
            size: 100,
          }),
          listEmailThreads({
            provider: provider || undefined,
            status: "active",
            intake_bucket: "needs_review",
            page: 1,
            size: 100,
          }),
          listEmailThreads({
            provider: provider || undefined,
            status: "active",
            intake_bucket: "background",
            page: 1,
            size: 50,
          }),
        ]);
        setBandNewLoads(nr.items ?? []);
        setBandNeedsReview(rq.items ?? []);
        setBandBackground(bg.items ?? []);
        setFlatThreads([]);
        const merged = [...(nr.items ?? []), ...(rq.items ?? []), ...(bg.items ?? [])];
        const nextId = pickNextSelectionId(merged, opts);
        if (nextId == null) {
          setSelectedThreadId(null);
          setThreadDetail(null);
          setMessages([]);
          return;
        }
        setSelectedThreadId(nextId);
      } else if (isLinkedOnlyView) {
        setBandNewLoads([]);
        setBandNeedsReview([]);
        setBandBackground([]);
        const res = await listEmailThreads({
          provider: provider || undefined,
          status: "active",
          intake_bucket: "linked",
          page: 1,
          size: 100,
        });
        const items = res.items ?? [];
        setFlatThreads(items);
        const nextId = pickNextSelectionId(items, opts);
        if (nextId == null) {
          setSelectedThreadId(null);
          setThreadDetail(null);
          setMessages([]);
          return;
        }
        setSelectedThreadId(nextId);
      } else {
        setBandNewLoads([]);
        setBandNeedsReview([]);
        setBandBackground([]);
        const res = await listEmailThreads({
          provider: provider || undefined,
          status: status || undefined,
          page: 1,
          size: 100,
        });
        const items = res.items ?? [];
        setFlatThreads(items);
        const nextId = pickNextSelectionId(items, opts);
        if (nextId == null) {
          setSelectedThreadId(null);
          setThreadDetail(null);
          setMessages([]);
          return;
        }
        setSelectedThreadId(nextId);
      }
    } catch (err: unknown) {
      setThreadsError(err instanceof Error ? err.message : "Failed to load intake queues");
      setBandNewLoads([]);
      setBandNeedsReview([]);
      setBandBackground([]);
      setFlatThreads([]);
      setSelectedThreadId(null);
      setThreadDetail(null);
      setMessages([]);
    } finally {
      if (!silent) setLoadingThreads(false);
    }
    if (!pathForKpisRef.current.startsWith(OPS.EMAIL_LOAD)) void refreshIntakeKpis();
  };

  useOperationalRefresh({
    intervalMs: 15_000,
    onRefresh: () => loadThreads({ keepSelection: true, silent: true }),
  });

  useEffect(() => {
    loadThreads();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provider, status, queueFocus]);

  useEffect(() => {
    if (!selectedThreadId) {
      setThreadDetail(null);
      setMessages([]);
      return;
    }
    let cancelled = false;
    setLoadingMessages(true);
    setMessagesError(null);
    Promise.all([getEmailThread(selectedThreadId), getEmailThreadMessages(selectedThreadId)])
      .then(([detail, msgs]) => {
        if (cancelled) return;
        setThreadDetail(detail);
        setMessages(msgs ?? []);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setMessagesError(err instanceof Error ? err.message : "Failed to load thread");
        setThreadDetail(null);
        setMessages([]);
      })
      .finally(() => {
        if (!cancelled) setLoadingMessages(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedThreadId]);

  const selectedThread = useMemo(
    () => allThreads.find((t) => t.id === selectedThreadId) ?? threadDetail,
    [allThreads, selectedThreadId, threadDetail]
  );

  const linkedLoadId = threadDetail?.linked_load_id ?? selectedThread?.linked_load_id ?? null;

  useEffect(() => {
    if (isEmailLoadRoute) {
      setLinkedLoadDetail(null);
      setLoadingLinkedLoad(false);
      return;
    }
    if (!linkedLoadId) {
      setLinkedLoadDetail(null);
      return;
    }
    let cancelled = false;
    setLoadingLinkedLoad(true);
    getLoad(linkedLoadId)
      .then((ld) => {
        if (!cancelled) setLinkedLoadDetail(ld);
      })
      .catch(() => {
        if (!cancelled) setLinkedLoadDetail(null);
      })
      .finally(() => {
        if (!cancelled) setLoadingLinkedLoad(false);
      });
    return () => {
      cancelled = true;
    };
  }, [linkedLoadId, isEmailLoadRoute]);

  useEffect(() => {
    if (!location.pathname.startsWith(OPS.INTAKE)) return;
    const sp = new URLSearchParams(location.search);
    const tid = sp.get("thread");
    if (!tid) return;
    const n = Number(tid);
    if (!Number.isFinite(n) || n <= 0) return;
    setSelectedThreadId(n);
    navigate(OPS.INTAKE, { replace: true });
  }, [location.pathname, location.search, navigate]);

  const handleRecomputeIntake = async () => {
    if (!selectedThreadId || recomputingIntake) return;
    const prov = selectedThread?.provider;
    if (prov !== "gmail") return;
    setActionError(null);
    setRecomputingIntake(true);
    try {
      const t = await recomputeEmailThreadIntake(selectedThreadId);
      setThreadDetail(t);
      await loadThreads({ retainSelectionId: t.id });
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Intake recompute failed");
    } finally {
      setRecomputingIntake(false);
    }
  };

  const handleDisregard = async () => {
    if (!selectedThreadId || disregarding) return;
    setActionError(null);
    setDisregarding(true);
    try {
      await disregardEmailThread(selectedThreadId);
      await loadThreads({ keepSelection: false });
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Failed to disregard thread");
    } finally {
      setDisregarding(false);
    }
  };

  const applyThreadAndRefresh = async (r: { thread: InboxThreadDetail }) => {
    setThreadDetail(r.thread);
    await loadThreads({ retainSelectionId: r.thread.id });
  };

  const handleCreateDraftLoad = async () => {
    if (!selectedThreadId || draftCreating) return;
    setActionError(null);
    setDraftCreating(true);
    try {
      const r = await createDraftLoadFromEmailThread(selectedThreadId);
      await applyThreadAndRefresh(r);
      if (r.thread.linked_load_id && selectedThreadId) {
        navigate(OPS.LOAD_WORKSPACE_INTAKE(r.thread.linked_load_id, selectedThreadId));
      }
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Failed to create draft load");
    } finally {
      setDraftCreating(false);
    }
  };

  const runLinkSearch = async () => {
    const q = linkSearch.trim();
    if (!q) {
      setLinkResults([]);
      return;
    }
    setLinkLoading(true);
    setActionError(null);
    try {
      const res = await listLoads({ search: q, page: 1, size: 25 });
      setLinkResults(res.items ?? []);
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Load search failed");
      setLinkResults([]);
    } finally {
      setLinkLoading(false);
    }
  };

  const handleConfirmLinkLoad = async (loadId: number) => {
    if (!selectedThreadId || linkSubmitting) return;
    setLinkSubmitting(true);
    setActionError(null);
    try {
      const r = await linkLoadToEmailThread(selectedThreadId, loadId);
      setLinkModalOpen(false);
      setLinkSearch("");
      setLinkResults([]);
      await applyThreadAndRefresh(r);
      if (r.thread.linked_load_id && selectedThreadId) {
        navigate(OPS.LOAD_WORKSPACE_INTAKE(r.thread.linked_load_id, selectedThreadId));
      }
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Failed to link load");
    } finally {
      setLinkSubmitting(false);
    }
  };

  const handleUploadDocumentChange = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || !selectedThreadId) return;
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setActionError("Choose a PDF file.");
      return;
    }
    setActionError(null);
    setUploadingPdf(true);
    try {
      const updated = await uploadPdfToEmailThread(selectedThreadId, file);
      setThreadDetail(updated);
      const msgs = await getEmailThreadMessages(selectedThreadId);
      setMessages(msgs ?? []);
      await loadThreads({ retainSelectionId: selectedThreadId });
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "PDF upload failed");
    } finally {
      setUploadingPdf(false);
    }
  };

  const handleIgnoreRow = async (threadId: number, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm("Ignore this thread? It will move to Disregarded.")) return;
    setActionError(null);
    try {
      await disregardEmailThread(threadId);
      await loadThreads({ keepSelection: true });
      if (selectedThreadId === threadId) {
        setSelectedThreadId(null);
      }
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Failed to ignore thread");
    }
  };

  const renderThreadRow = (t: InboxThreadListItem, variant: "new_load" | "needs_review") => {
    const active = selectedThreadId === t.id;
    const loadLabel = t.linked_load_number || (t.linked_load_id ? `ID ${t.linked_load_id}` : "—");
    const tripLabel = t.linked_trip_number?.trim() || "—";
    const broker = t.linked_broker_name || participantPreview(t.participants_json);
    return (
      <button
        type="button"
        key={`${variant}-${t.id}`}
        onClick={() => setSelectedThreadId(t.id)}
        className={`w-full border-b border-[var(--trk-bg)] px-3 py-2.5 text-left transition ${
          active ? "bg-[var(--trk-surface)]" : "hover:bg-[var(--trk-surface)]"
        }`}
      >
        {variant === "new_load" ? (
          <div className="flex flex-col gap-1.5">
            <div className="flex items-start justify-between gap-2">
              <div>
                <span className="text-sm font-semibold text-[var(--trk-text)]">Load {loadLabel}</span>
                <p className="mt-0.5 text-[11px] text-[var(--trk-text-muted)]">Trip {tripLabel}</p>
              </div>
              <span className={`shrink-0 rounded border px-1.5 py-0.5 text-[10px] ${confidenceClass(t.confidence_level)}`}>
                {confidenceLabel(t.confidence_level)}
              </span>
            </div>
            <div className="text-xs text-[var(--trk-text-muted)]">{broker}</div>
            <div className="line-clamp-2 text-xs text-[var(--trk-text-muted)]">
              {t.pickup_delivery_summary || t.snippet || "No route summary yet."}
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-[var(--trk-text-muted)]">
              <span>{formatWhen(t.last_message_at || t.created_at)}</span>
              <span className="text-[var(--trk-success)]">Thread #{t.id}</span>
            </div>
            <div className="flex flex-wrap gap-1.5 pt-1">
              {t.linked_load_id ? (
                <span
                  role="link"
                  tabIndex={0}
                  className="cursor-pointer rounded border border-[var(--trk-accent)] bg-[var(--trk-surface)] px-2 py-0.5 text-[11px] text-[var(--trk-accent)] hover:bg-[var(--trk-surface-2)]"
                  onClick={(e) => {
                    e.stopPropagation();
                    navigate(OPS.LOAD_WORKSPACE_INTAKE(t.linked_load_id!, t.id));
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.stopPropagation();
                      navigate(OPS.LOAD_WORKSPACE_INTAKE(t.linked_load_id!, t.id));
                    }
                  }}
                >
                  Open load
                </span>
              ) : null}
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-1">
            <div className="flex items-start justify-between gap-2">
              <span className="line-clamp-2 text-sm font-medium text-[var(--trk-text)]">{threadIntakePrimaryLabel(t)}</span>
              <span className={`shrink-0 rounded border px-1.5 py-0.5 text-[10px] ${confidenceClass(t.confidence_level)}`}>
                {confidenceLabel(t.confidence_level)}
              </span>
            </div>
            <p className="text-xs text-[var(--trk-text-muted)]">{broker}</p>
            <p
              className="line-clamp-2 text-[11px] text-[var(--trk-text-muted)]"
              title={formatRoutingReason(t.routing_reason)}
            >
              {formatRoutingReason(t.routing_reason)}
            </p>
            <div className="flex items-center justify-between gap-2 pt-1 text-[11px] text-[var(--trk-text-muted)]">
              <span>{formatWhen(t.last_message_at || t.created_at)}</span>
              <button
                type="button"
                className="rounded border border-[var(--trk-warning)] px-2 py-0.5 text-[var(--trk-warning)] hover:bg-[var(--trk-surface-2)]"
                onClick={(e) => handleIgnoreRow(t.id, e)}
              >
                Ignore
              </button>
            </div>
          </div>
        )}
      </button>
    );
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="max-w-2xl">
          <h1 className="text-xl font-semibold text-[var(--trk-text)]">{pageTitle}</h1>
          <p className="text-sm text-[var(--trk-text-muted)]">{pageSubtitle}</p>
          {isEmailLoadRoute ? (
            <details className="mt-2 text-xs text-[var(--trk-text-muted)] marker:text-[var(--trk-text-muted)]">
              <summary className="cursor-pointer text-[var(--trk-text-muted)] hover:text-[var(--trk-text)]">Ingestion &amp; troubleshooting</summary>
              <p className="mt-2 leading-relaxed">
                New Gmail is classified and routed via backend sync (push → delta → route). Use Refresh to reload this list
                from the server. Pull new mail is optional if push was delayed or you are debugging.
              </p>
            </details>
          ) : (
            <p className="mt-2 text-xs text-[var(--trk-text-muted)]">
              Open <strong className="text-[var(--trk-text-muted)]">Email load</strong> for sync, queues, and ingestion tools. This screen
              focuses on verification and draft load creation.
            </p>
          )}
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            className="rounded border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2 text-sm text-[var(--trk-text)]"
          >
            <option value="">All providers</option>
            <option value="gmail">Gmail</option>
          </select>
          <select
            value={status}
            onChange={(e) => {
              const v = e.target.value;
              setStatus(v);
              if (v !== "active") setQueueFocus("intake");
            }}
            className="rounded border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2 text-sm text-[var(--trk-text)]"
          >
            <option value="active">Active threads</option>
            <option value="">All statuses</option>
            <option value="disregarded">Disregarded</option>
            <option value="archived">Archived</option>
          </select>
          {status === "active" && (
            <select
              value={queueFocus}
              onChange={(e) => setQueueFocus(e.target.value as "intake" | "linked")}
              className="rounded border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2 text-sm text-[var(--trk-text)]"
            >
              <option value="intake">Queues: New loads + Needs review</option>
              <option value="linked">Linked threads</option>
            </select>
          )}
          <button
            type="button"
            onClick={() => loadThreads({ keepSelection: true })}
            className="rounded border border-[var(--trk-border-strong)] px-3 py-2 text-sm text-[var(--trk-text)] hover:bg-[var(--trk-surface)]"
          >
            Refresh list
          </button>
          <button
            type="button"
            title="Same delta sync as automatic Gmail push — use only as a fallback"
            disabled={pullingGmailDelta}
            onClick={async () => {
              setPullingGmailDelta(true);
              setActionError(null);
              try {
                await pullGmailDeltaFromInbox(30);
                await loadThreads({ keepSelection: true });
              } catch (e: unknown) {
                setActionError(e instanceof Error ? e.message : "Pull new mail failed");
              } finally {
                setPullingGmailDelta(false);
              }
            }}
            className="rounded border border-[var(--trk-border-strong)] bg-[var(--trk-surface)] px-3 py-2 text-sm text-[var(--trk-text)] hover:bg-[var(--trk-surface-2)] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {pullingGmailDelta ? "Pulling…" : "Pull new mail (optional)"}
          </button>
        </div>
      </div>

      {actionError && <div className="rounded border border-[var(--trk-danger)] bg-[var(--trk-surface)] p-3 text-sm text-[var(--trk-danger)]">{actionError}</div>}
      <div className="grid min-h-[620px] grid-cols-1 gap-4 lg:grid-cols-[380px_1fr]">
        <section className="flex flex-col rounded-xl border border-[var(--trk-border)] bg-[var(--trk-bg)]">
          <div className="border-b border-[var(--trk-border)] px-4 py-3 text-sm font-semibold text-[var(--trk-text)]">Queues</div>
          <div className="max-h-[560px] flex-1 overflow-auto">
            {loadingThreads && <div className="px-4 py-6 text-sm text-[var(--trk-text-muted)]">Loading…</div>}
            {!loadingThreads && threadsError && <div className="px-4 py-6 text-sm text-red-400">{threadsError}</div>}
            {!loadingThreads &&
              !threadsError &&
              isBandView &&
              bandNewLoads.length === 0 &&
              bandNeedsReview.length === 0 &&
              bandBackground.length === 0 && (
                <div className="px-4 py-10 text-sm text-[var(--trk-text-muted)]">No active intake items.</div>
              )}
            {!loadingThreads && !threadsError && isLinkedOnlyView && flatThreads.length === 0 && (
              <div className="px-4 py-10 text-sm text-[var(--trk-text-muted)]">No linked threads.</div>
            )}
            {!loadingThreads && !threadsError && !isBandView && !isLinkedOnlyView && flatThreads.length === 0 && (
              <div className="px-4 py-10 text-sm text-[var(--trk-text-muted)]">No threads.</div>
            )}

            {!loadingThreads && !threadsError && isBandView && (
              <>
                <div className="border-b border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2">
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-[var(--trk-text-muted)]">New loads</p>
                  <p className="text-[11px] text-[var(--trk-text-muted)]">Auto-created loads with trip numbers; verify in Loads.</p>
                </div>
                {bandNewLoads.length === 0 ? (
                  <div className="px-3 py-4 text-xs text-[var(--trk-text-muted)]">None right now.</div>
                ) : (
                  bandNewLoads.map((t) => renderThreadRow(t, "new_load"))
                )}

                <div className="border-b border-t border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2">
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-[var(--trk-text-muted)]">Needs review</p>
                  <p className="text-[11px] text-[var(--trk-text-muted)]">Rate cons and broker mail — verify, link, or ignore.</p>
                </div>
                {bandNeedsReview.length === 0 ? (
                  <div className="px-3 py-4 text-xs text-[var(--trk-text-muted)]">None right now.</div>
                ) : (
                  bandNeedsReview.map((t) => renderThreadRow(t, "needs_review"))
                )}

                <div className="border-b border-t border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2">
                  <p className="text-xs font-semibold uppercase tracking-wide text-[var(--trk-text-muted)]">Other synced mail</p>
                  <p className="text-[11px] text-[var(--trk-text-muted)]">
                    Non–broker-intake threads (still in Gmail). Open from here or disregard.
                  </p>
                </div>
                {bandBackground.length === 0 ? (
                  <div className="px-3 py-4 text-xs text-[var(--trk-text-muted)]">None.</div>
                ) : (
                  bandBackground.map((t) => renderThreadRow(t, "needs_review"))
                )}
              </>
            )}

            {!loadingThreads &&
              !threadsError &&
              isLinkedOnlyView &&
              flatThreads.map((t) => {
                const active = selectedThreadId === t.id;
                return (
                  <button
                    type="button"
                    key={t.id}
                    onClick={() => setSelectedThreadId(t.id)}
                    className={`w-full border-b border-[var(--trk-bg)] px-4 py-3 text-left transition ${
                      active ? "bg-[var(--trk-surface)]" : "hover:bg-[var(--trk-surface)]"
                    }`}
                  >
                    <p className="truncate text-sm font-semibold text-[var(--trk-text)]">{t.subject || "(No subject)"}</p>
                    <p className="mt-1 text-xs text-[var(--trk-text-muted)]">
                      {t.linked_load_number ? `Load ${t.linked_load_number}` : `Load id ${t.linked_load_id ?? "—"}`}
                    </p>
                    <p className="mt-0.5 text-[11px] text-[var(--trk-text-muted)]">Trip {t.linked_trip_number?.trim() || "—"}</p>
                    <p className="mt-1 text-[11px] text-[var(--trk-text-muted)]">{formatWhen(t.last_message_at || t.created_at)}</p>
                  </button>
                );
              })}

            {!loadingThreads && !threadsError && !isBandView && !isLinkedOnlyView &&
              flatThreads.map((t) => {
                const active = selectedThreadId === t.id;
                return (
                  <button
                    type="button"
                    key={t.id}
                    onClick={() => setSelectedThreadId(t.id)}
                    className={`w-full border-b border-[var(--trk-bg)] px-4 py-3 text-left transition ${
                      active ? "bg-[var(--trk-surface)]" : "hover:bg-[var(--trk-surface)]"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <p className="truncate text-sm font-semibold text-[var(--trk-text)]">{t.subject || "(No subject)"}</p>
                      {t.unread_count > 0 && (
                        <span className="rounded-full bg-[var(--trk-heading)]/20 px-2 py-0.5 text-xs text-[var(--trk-heading)]">{t.unread_count}</span>
                      )}
                    </div>
                    <p className="mt-1 truncate text-xs text-[var(--trk-text-muted)]">{participantPreview(t.participants_json)}</p>
                    <p className="mt-1 truncate text-xs text-[var(--trk-text-muted)]">{t.snippet || "No snippet"}</p>
                    <div className="mt-2 flex items-center justify-between text-[11px] text-[var(--trk-text-muted)]">
                      <span>{formatWhen(t.last_message_at || t.created_at)}</span>
                      <span>{t.intake_bucket}</span>
                    </div>
                  </button>
                );
              })}
          </div>
        </section>

        <section className="flex min-h-[620px] flex-col rounded-xl border border-[var(--trk-border)] bg-[var(--trk-bg)]">
          <div className="shrink-0 border-b border-[var(--trk-border)] px-4 py-2.5">
            {!selectedThread ? (
              <p className="text-sm text-[var(--trk-text-muted)]">
                {isEmailLoadRoute
                  ? "Select a queue item to read the thread."
                  : "Select a queue item to verify intake."}
              </p>
            ) : (
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <h2 className="truncate text-sm font-semibold text-[var(--trk-text)]">
                    {selectedThread.intake_bucket === "needs_review" || selectedThread.intake_bucket === "background"
                      ? threadIntakePrimaryLabel(selectedThread)
                      : selectedThread.subject || "(No subject)"}
                  </h2>
                  <p className="truncate text-xs text-[var(--trk-text-muted)]">
                    {participantPreview(selectedThread.participants_json)}
                    <span className="text-[var(--trk-text-muted)]"> · </span>
                    {selectedThread.provider} · {selectedThread.intake_bucket}
                    {selectedThread.confidence_level ? ` · ${confidenceLabel(selectedThread.confidence_level)}` : ""}
                  </p>
                  {selectedThread.pickup_delivery_summary ? (
                    <p className="mt-0.5 truncate text-[11px] text-[var(--trk-text-muted)]/90">{selectedThread.pickup_delivery_summary}</p>
                  ) : null}
                  {selectedThread.linked_load_id ? (
                    <p className="mt-0.5 truncate text-[11px] text-[var(--trk-text-muted)]">
                      Trip {selectedThread.linked_trip_number?.trim() || "—"}
                    </p>
                  ) : null}
                  {!selectedThread.linked_load_id && selectedThread.routing_reason ? (
                    <p
                      className="mt-0.5 line-clamp-3 text-[11px] text-[var(--trk-warning)]"
                      title={formatRoutingReason(selectedThread.routing_reason)}
                    >
                      {formatRoutingReason(selectedThread.routing_reason)}
                    </p>
                  ) : null}
                </div>
                <div className="flex flex-shrink-0 flex-wrap items-center justify-end gap-2">
                  {isEmailLoadRoute ? (
                    <button
                      type="button"
                      onClick={() => navigate(`${OPS.INTAKE}?thread=${selectedThread.id}`)}
                      className="rounded border border-[var(--trk-border-strong)] bg-[var(--trk-surface)] px-3 py-1.5 text-xs font-medium text-[var(--trk-text)] hover:bg-[var(--trk-surface-2)]"
                    >
                      Load Intake
                    </button>
                  ) : null}
                  {selectedThread.linked_load_id && selectedThreadId ? (
                    <button
                      type="button"
                      onClick={() =>
                        navigate(OPS.LOAD_WORKSPACE_INTAKE(selectedThread.linked_load_id!, selectedThreadId))
                      }
                      className="rounded border border-[var(--trk-accent)] bg-[var(--trk-surface)] px-3 py-1.5 text-xs font-medium text-[var(--trk-accent)] hover:bg-[var(--trk-surface-2)]"
                    >
                      Open in Loads
                    </button>
                  ) : null}
                  {(selectedThread.intake_bucket === "needs_review" || selectedThread.intake_bucket === "background") &&
                    !selectedThread.linked_load_id &&
                    selectedThread.status === "active" && (
                      <button
                        type="button"
                        onClick={() => {
                          setLinkModalOpen(true);
                          setLinkResults([]);
                          setLinkSearch("");
                        }}
                        className="rounded border border-[var(--trk-border-strong)] bg-[var(--trk-surface)] px-3 py-1.5 text-xs font-medium text-[var(--trk-text)] hover:bg-[var(--trk-surface-2)]"
                      >
                        Link existing load
                      </button>
                    )}
                  <button
                    type="button"
                    onClick={handleDisregard}
                    disabled={disregarding || selectedThread.status === "disregarded"}
                    className="rounded border border-[var(--trk-warning)] bg-[var(--trk-surface)] px-3 py-1.5 text-xs font-medium text-[var(--trk-warning)] hover:bg-[var(--trk-surface-2)] disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {selectedThread.status === "disregarded"
                      ? "Disregarded"
                      : disregarding
                        ? "Disregarding…"
                        : "Ignore"}
                  </button>
                </div>
              </div>
            )}
          </div>

          <div className="min-h-0 flex-1 overflow-auto p-4">
            {selectedThread ? (
              isEmailLoadRoute ? (
                <>
                  <input
                    ref={emailUploadRef}
                    type="file"
                    accept=".pdf,application/pdf"
                    className="hidden"
                    onChange={handleUploadDocumentChange}
                  />
                  <p className="mb-3 text-xs text-[var(--trk-text-muted)]">
                    Read and triage mail here. Open <span className="text-[var(--trk-text-muted)]">Load Intake</span> for verify, form,
                    and create-load.
                  </p>
                  <div className="mb-4 flex flex-wrap items-center gap-2 border-b border-[var(--trk-border)] pb-4">
                    <button
                      type="button"
                      onClick={() => navigate(`${OPS.INTAKE}?thread=${selectedThread.id}`)}
                      className="rounded-lg border border-[var(--trk-heading)] bg-[var(--trk-heading)] px-3 py-2 text-sm font-semibold text-[var(--trk-btn-text)] hover:opacity-90"
                    >
                      Open Load Intake
                    </button>
                    <button
                      type="button"
                      onClick={() => emailUploadRef.current?.click()}
                      disabled={uploadingPdf || selectedThread.status !== "active"}
                      className="rounded-lg border border-[var(--trk-accent)] bg-[var(--trk-accent)] px-3 py-2 text-sm font-semibold text-[var(--trk-btn-text)] hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {uploadingPdf ? "Uploading…" : "Upload PDF"}
                    </button>
                    <button
                      type="button"
                      onClick={handleRecomputeIntake}
                      disabled={
                        !(selectedThread.provider === "gmail" && selectedThread.status === "active") || recomputingIntake
                      }
                      className="rounded-lg border border-[var(--trk-text-muted)] bg-[var(--trk-surface)] px-3 py-2 text-sm font-medium text-[var(--trk-text-muted)] hover:bg-[var(--trk-border)] disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      {recomputingIntake ? "Re-parsing…" : "Re-parse"}
                    </button>
                  </div>
                  <ThreadMessageList
                    loadingMessages={loadingMessages}
                    messagesError={messagesError}
                    selectedThreadId={selectedThreadId}
                    messages={messages}
                  />
                </>
              ) : (
                <>
                  {loadingLinkedLoad && linkedLoadId ? (
                    <p className="mb-2 text-xs text-[var(--trk-text-muted)]">Loading linked load for verification…</p>
                  ) : null}
                  <IntakeVerificationPanel
                    emailThreadId={selectedThreadId}
                    threadSubject={selectedThread.subject}
                    routingReason={formatRoutingReason(selectedThread.routing_reason)}
                    messages={messages}
                    linkedLoad={linkedLoadDetail}
                    kpis={intakeKpis}
                    canReparse={selectedThread.provider === "gmail" && selectedThread.status === "active"}
                    recomputingIntake={recomputingIntake}
                    onReparse={handleRecomputeIntake}
                    canVerifyCreate={
                      (selectedThread.intake_bucket === "needs_review" || selectedThread.intake_bucket === "background") &&
                      !selectedThread.linked_load_id &&
                      selectedThread.status === "active"
                    }
                    draftCreating={draftCreating}
                    onVerifyCreate={handleCreateDraftLoad}
                    onManualEntry={() => navigate(OPS.LOAD_NEW)}
                    uploadBusy={uploadingPdf}
                    onUploadDocumentChange={handleUploadDocumentChange}
                    userEmail={me?.email ?? null}
                    onClose={() => navigate(OPS.DASHBOARD)}
                    onIntakeActionsComplete={async () => {
                      if (!selectedThreadId) return;
                      const [detail, msgs] = await Promise.all([
                        getEmailThread(selectedThreadId),
                        getEmailThreadMessages(selectedThreadId),
                      ]);
                      setThreadDetail(detail);
                      setMessages(msgs ?? []);
                      await loadThreads({ retainSelectionId: selectedThreadId });
                    }}
                  />

                  <details className="mt-6 rounded-xl border border-[var(--trk-border)] bg-[var(--trk-surface)]">
                    <summary className="cursor-pointer px-4 py-3 text-sm font-semibold text-[var(--trk-text)] marker:text-[var(--trk-text-muted)]">
                      Email thread (reference)
                    </summary>
                    <div className="border-t border-[var(--trk-border)] p-4">
                      <ThreadMessageList
                        loadingMessages={loadingMessages}
                        messagesError={messagesError}
                        selectedThreadId={selectedThreadId}
                        messages={messages}
                      />
                    </div>
                  </details>
                </>
              )
            ) : null}
          </div>
        </section>
      </div>

      {linkModalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          role="dialog"
          aria-modal="true"
          aria-label="Link existing load"
        >
          <div className="w-full max-w-md rounded-xl border border-[var(--trk-border)] bg-[var(--trk-bg)] p-4 shadow-xl">
            <h3 className="text-sm font-semibold text-[var(--trk-text)]">Link Existing Load</h3>
            <p className="mt-1 text-xs text-[var(--trk-text-muted)]">Search by load number, broker reference, or broker name.</p>
            <div className="mt-3 flex gap-2">
              <input
                value={linkSearch}
                onChange={(e) => setLinkSearch(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && runLinkSearch()}
                placeholder="Search…"
                className="flex-1 rounded border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2 text-sm text-[var(--trk-text)]"
              />
              <button
                type="button"
                onClick={runLinkSearch}
                disabled={linkLoading}
                className="rounded border border-[var(--trk-border-strong)] px-3 py-2 text-sm text-[var(--trk-text)] hover:bg-[var(--trk-surface)] disabled:opacity-50"
              >
                {linkLoading ? "…" : "Search"}
              </button>
            </div>
            <div className="mt-3 max-h-52 overflow-auto rounded border border-[var(--trk-border)]">
              {linkResults.length === 0 && !linkLoading && (
                <p className="p-3 text-xs text-[var(--trk-text-muted)]">No results yet. Enter a term and search.</p>
              )}
              {linkResults.map((ld) => (
                <div
                  key={ld.id}
                  className="flex items-center justify-between gap-2 border-b border-[var(--trk-bg)] px-3 py-2 text-xs"
                >
                  <div>
                    <div className="font-medium text-[var(--trk-text)]">{ld.load_number}</div>
                    <div className="text-[11px] text-[var(--trk-text-muted)]">
                      Trip {ld.trip_number?.trim() || "—"}
                    </div>
                    <div className="text-[var(--trk-text-muted)]">
                      {[ld.broker_load_reference, ld.broker_name_snapshot].filter(Boolean).join(" · ") || "—"}
                    </div>
                  </div>
                  <button
                    type="button"
                    disabled={linkSubmitting}
                    onClick={() => handleConfirmLinkLoad(ld.id)}
                    className="shrink-0 rounded border border-[var(--trk-success)] bg-[var(--trk-surface)] px-2 py-1 text-[var(--trk-success)] hover:bg-[var(--trk-surface-2)] disabled:opacity-50"
                  >
                    Link
                  </button>
                </div>
              ))}
            </div>
            <div className="mt-3 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setLinkModalOpen(false);
                  setLinkResults([]);
                }}
                className="rounded border border-[var(--trk-border-strong)] px-3 py-1.5 text-xs text-[var(--trk-text)] hover:bg-[var(--trk-surface)]"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
