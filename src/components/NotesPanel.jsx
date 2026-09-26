// The meeting workspace — header + tabs recreated from
// design_handoff_jotva_workspace/Jotva Meeting.dc.html (#5i, canonical).
// Title is static (zero manual labor: nothing here is ever typed by the
// user), a green-gradient summary hero dominates, then Actions/Decisions
// (left, heavier) and Topics/Open Questions/Highlight (right, lighter).
// Content types the canonical mockup doesn't show (Heads Up, Compliance,
// Conflicts, Next Steps, Key Discussions, Related) are real, still-shipping
// capabilities — kept as conditional callouts above the hero (alerts) or
// quiet unboxed sections below the two columns (extra generated content),
// so the primary layout stays pixel-true while nothing is removed.
import React, { useEffect, useRef, useState } from "react";
import { useGlassLens } from "../glassLens.js";
import { useTranslation } from "react-i18next";
import { api, showInFolder } from "../api.js";
import { useStore, useLogo } from "../store.jsx";
import AskTab from "./AskTab.jsx";
import FollowUp from "./FollowUp.jsx";
import Markdown from "./Markdown.jsx";
import Onboarding from "./Onboarding.jsx";
import TimelineTab from "./TimelineTab.jsx";
import TranscriptTab from "./TranscriptTab.jsx";
import { CheckIcon, ClockIcon, DotsIcon, PlayIcon, StarIcon, UsersIcon, WarnIcon } from "./icons.jsx";
import { Confirm } from "./ui.jsx";

const INTEGRATION_LABELS = {
  slack: "Slack",
  notion: "Notion",
  linear: "Linear",
  jira: "Jira",
  hubspot: "HubSpot",
  salesforce: "Salesforce",
  google_drive: "Google Drive",
  zapier: "Zapier",
};

const AVATAR_COLORS = ["var(--av-amber)", "var(--av-purple)", "var(--av-teal)", "var(--av-green)"];
const ACTIONS_PREVIEW = 4;

const PLACED = new Set([
  "Executive Summary",
  "Action Items",
  "Decisions Made",
  "Key Discussions",
  "Next Steps",
  "Compliance Flags",
]);
const isQuestionSection = (name) => /question/i.test(name);
const isRiskSection = (name) => /risk|compliance|flag/i.test(name);
// "None identified." bodies leave the callout hidden (shown only when
// applicable) — also when the model renders it as a bullet ("- None …").
const hasContent = (body) => body && body.trim() && !/^[-*\s]*none\b/i.test(body.trim());

// Executive Summary asks the model for one *emphasized* key phrase (single
// asterisks) — rendered italic green in the hero, per the design spec.
function renderSummary(text) {
  const parts = [];
  let rest = text;
  let i = 0;
  while (rest.length) {
    const start = rest.indexOf("*");
    const end = start === -1 ? -1 : rest.indexOf("*", start + 1);
    if (start === -1 || end === -1) {
      parts.push(rest);
      break;
    }
    if (start > 0) parts.push(rest.slice(0, start));
    parts.push(
      <em className="summary-key" key={`sk${i++}`}>
        {rest.slice(start + 1, end)}
      </em>
    );
    rest = rest.slice(end + 1);
  }
  return parts;
}

function initials(name) {
  return (name || "")
    .split(/\s+/)
    .map((w) => w[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

function EmptyState() {
  const { t } = useTranslation();
  return (
    <div className="empty-state" data-tour="notes-panel">
      <div className="empty-title">{t("notes.empty.selectMeeting")}</div>
      <div className="empty-sub">{t("notes.empty.selectMeetingSub")}</div>
    </div>
  );
}

function DetailSkeleton() {
  return (
    <div className="workspace">
      <div className="ws-inner skeleton-detail" aria-hidden="true">
        <div className="skeleton" style={{ height: 38, width: "62%" }} />
        <div className="skeleton" style={{ height: 16, width: "38%" }} />
        <div className="skeleton" style={{ height: 180, borderRadius: 18 }} />
        <div className="skeleton" style={{ height: 140, borderRadius: 14 }} />
      </div>
    </div>
  );
}

const fmtClock = (sec) => `${Math.floor(sec / 60)}:${String(Math.floor(sec % 60)).padStart(2, "0")}`;
const OWNER_COLORS = ["#c2762e", "#7048e8", "#1f8a9e", "#b8407a", "#3b7a3b", "#4263eb"];
const ownerColor = (name) => OWNER_COLORS[[...name].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7) % OWNER_COLORS.length];

// "2026-09-15" -> "Sep 15" / "Tomorrow" (localized); free-text dues ("next week") pass through.
function formatDue(due, lang) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(due || "");
  if (!m) return { label: due || "", overdue: false };
  const date = new Date(+m[1], +m[2] - 1, +m[3]);
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const days = Math.round((date - today) / 86400000);
  let label;
  if (Math.abs(days) <= 1) {
    label = new Intl.RelativeTimeFormat(lang, { numeric: "auto" }).format(days, "day");
    label = label.charAt(0).toLocaleUpperCase(lang) + label.slice(1);
  } else {
    label = date.toLocaleDateString(lang, { month: "short", day: "numeric", ...(date.getFullYear() !== today.getFullYear() && { year: "numeric" }) });
  }
  return { label, overdue: days < 0 };
}

// Markdown list ("1. …", "- …") -> item strings; null when the text isn't a plain list.
function listItems(text) {
  const lines = (text || "").split("\n").map((l) => l.trim()).filter(Boolean);
  if (!lines.length || !lines.every((l) => /^(\d+[.)]|[-*•])\s+/.test(l))) return null;
  return lines.map((l) => l.replace(/^(\d+[.)]|[-*•])\s+/, ""));
}

function ActionRow({ item, onAssign, onComplete }) {
  const { t, i18n } = useTranslation();
  const [assigning, setAssigning] = useState(false);
  const [name, setName] = useState("");
  const isTbd = !item.owner || item.owner.trim().toUpperCase() === "TBD";
  const done = item.status === "done";

  const submit = () => {
    const trimmed = name.trim();
    if (trimmed) onAssign(item.id, trimmed);
    setAssigning(false);
    setName("");
  };

  const due = formatDue(item.due, i18n.language);
  return (
    <div className="ov-action-row">
      <button
        className={`ov-check${done ? " done" : ""}`}
        onClick={() => onComplete(item)}
        aria-label={done ? t("notes.action.markIncomplete") : t("notes.action.markComplete")}
      >
        {done && <CheckIcon size={10} strokeWidth={3.5} />}
      </button>
      <div className="ov-action-main">
        <span className={`ov-action-text${done ? " done" : ""}`}>{item.action}</span>
        <div className="ov-action-meta">
          {assigning ? (
            <input
              className="assign-input"
              autoFocus
              placeholder={t("notes.action.owner")}
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") submit();
                if (e.key === "Escape") setAssigning(false);
              }}
              onBlur={submit}
            />
          ) : (
            <button className={`ov-action-owner${isTbd ? " tbd" : ""}`} onClick={() => setAssigning(true)}>
              {isTbd ? t("notes.action.assignOwner") : (
                <><span className="owner-avatar" style={{ background: ownerColor(item.owner) }} aria-hidden="true">{initials(item.owner)}</span>{item.owner}</>
              )}
            </button>
          )}
          {(done || due.label) && (
            <span className={`ov-action-due${due.overdue && !done ? " overdue" : ""}`}>{done ? t("notes.action.done") : due.label}</span>
          )}
        </div>
      </div>
    </div>
  );
}

function ConflictCard({ conflict, onResolve }) {
  const { t } = useTranslation();
  return (
    <div className="conflict-card">
      <div className="surface-title">
        <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
          <WarnIcon size={15} /> {t("notes.conflict.detected")}
        </span>
      </div>
      <div className="conflict-pair">
        <div className="conflict-side new">
          <span className="conflict-tag">{t("notes.conflict.new")}</span>
          <p>{conflict.new_decision}</p>
        </div>
        <div className="conflict-side old">
          <span className="conflict-tag">
            {conflict.old_date?.slice(0, 10)} · {conflict.old_meeting_title}
          </span>
          <p>{conflict.old_decision}</p>
        </div>
      </div>
      {conflict.explanation && <p className="conflict-why">{conflict.explanation}</p>}
      <div className="conflict-actions">
        <button className="btn compact" onClick={() => onResolve(conflict.id, "superseded")}>
          {t("notes.conflict.supersedes")}
        </button>
        <button className="btn secondary compact" onClick={() => onResolve(conflict.id, "reviewed")}>
          {t("notes.conflict.markReviewed")}
        </button>
      </div>
    </div>
  );
}

export default function NotesPanel() {
  const { t } = useTranslation();
  const {
    selectedId,
    meetingDetail,
    refreshDetail,
    refreshMeetings,
    refreshMyWork,
    progress,
    showToast,
    selectMeeting,
    deleteMeeting,
    templates,
  } = useStore();
  const logoUrl = useLogo();
  const [tab, setTab] = useState("overview"); // overview | timeline | transcript | ask
  const [jump, setJump] = useState(null); // { sec, id }: Overview highlight -> transcript playback
  const tabsRef = useRef(null);
  const tabRefs = useRef({});
  const [tabHover, setTabHover] = useState(null);
  const tabLensTarget = tabHover || tab;
  const tabLens = useGlassLens(tabsRef, () => tabRefs.current[tabLensTarget], `${tabLensTarget}:${meetingDetail?.id}:${!!meetingDetail?.notes}`);
  const [menu, setMenu] = useState(null); // null | "main" | "send" | "regen"
  const [followUpOpen, setFollowUpOpen] = useState(false);
  const [shareModal, setShareModal] = useState(null); // { url }
  const [showAllActions, setShowAllActions] = useState(false);
  const [onboarded, setOnboarded] = useState(
    () => localStorage.getItem("jotva_onboarded") === "true"
  );
  const [confirmDelete, setConfirmDelete] = useState(false);
  const menuRef = useRef(null);

  useEffect(() => {
    setMenu(null);
    setFollowUpOpen(false);
    setTab("overview");
    setShowAllActions(false);
  }, [meetingDetail?.id]);

  useEffect(() => {
    if (!menu) return;
    const onDocMouseDown = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) setMenu(null);
    };
    document.addEventListener("mousedown", onDocMouseDown);
    return () => document.removeEventListener("mousedown", onDocMouseDown);
  }, [menu]);

  if (!onboarded) {
    return (
      <div className="workspace">
        <Onboarding onDone={() => setOnboarded(true)} />
      </div>
    );
  }
  if (!selectedId) {
    return (
      <div className="workspace">
        <EmptyState />
      </div>
    );
  }
  if (!meetingDetail) return <DetailSkeleton />;

  const m = meetingDetail;
  const live = progress[m.id]?.stage || m.status;
  const intel = m.intelligence || {};
  const actions = intel.actions || [];
  const decisions = intel.decisions || [];
  const participants = intel.participants || [];
  const topics = intel.topics || [];
  const headsUp = intel.heads_up || [];
  const related = intel.related || [];
  const conflicts = (m.conflicts || []).filter((c) => c.status === "open");
  const markers = m.markers || [];
  const sections = m.notes?.sections || {};
  const executiveSummary = sections["Executive Summary"] || "";
  const keyDiscussions = sections["Key Discussions"] || "";
  const nextSteps = sections["Next Steps"] || "";
  const compliance = sections["Compliance Flags"] || "";
  const questionEntries = Object.entries(sections).filter(
    ([name, body]) => isQuestionSection(name) && hasContent(body)
  );
  const riskEntries = Object.entries(sections).filter(
    ([name, body]) =>
      !PLACED.has(name) && !isQuestionSection(name) && isRiskSection(name) && hasContent(body)
  );
  const otherEntries = Object.entries(sections).filter(
    ([name, body]) =>
      !PLACED.has(name) && !isQuestionSection(name) && !isRiskSection(name) && body?.trim()
  );

  const toggleStar = () => {
    api
      .patch(`/api/meetings/${m.id}`, { starred: !m.starred })
      .then(() => {
        refreshDetail();
        refreshMeetings();
      })
      .catch((e) => showToast(e.message, "error"));
  };

  const assign = (actionId, owner) => {
    api
      .patch(`/api/intelligence/actions/${actionId}`, { owner })
      .then(() => {
        refreshDetail();
        refreshMyWork();
      })
      .catch((e) => showToast(e.message, "error"));
  };

  const completeAction = (item) => {
    const next = item.status === "done" ? "open" : "done";
    api
      .patch(`/api/intelligence/actions/${item.id}`, {
        status: next,
        completed_at: next === "done" ? new Date().toISOString() : null,
      })
      .then(() => {
        refreshDetail();
        refreshMyWork();
      })
      .catch((e) => showToast(e.message, "error"));
  };

  const shareMeeting = () => {
    setMenu(null);
    api
      .post(`/api/meetings/${m.id}/share`)
      .then((r) => setShareModal({ url: r.share_url }))
      .catch((e) => showToast(e.message, "error"));
  };

  const copyShareLink = () => {
    if (!shareModal) return;
    navigator.clipboard
      ?.writeText(shareModal.url)
      .then(() => showToast(t("notes.toast.linkCopied")))
      .catch(() => showToast(t("notes.toast.copyFailed"), "error"));
  };

  const resolveConflict = (conflictId, resolution) => {
    api
      .patch(`/api/intelligence/conflicts/${conflictId}`, { resolution })
      .then(() => {
        refreshDetail();
        showToast(
          resolution === "superseded"
            ? t("notes.toast.oldSuperseded")
            : t("notes.toast.markedReviewed")
        );
      })
      .catch((e) => showToast(e.message, "error"));
  };

  const doExport = (fmt) => {
    setMenu(null);
    if (fmt === "pdf") {
      // Prints the live #pdf-print-root (design-reference/Meeting Note PDF.dc.html)
      // via Electron's own Chromium instead of the fpdf2 drawing library, so the
      // export matches the real HTML/CSS template exactly.
      if (!window.jotva?.exportPdf) {
        showToast(t("notes.toast.pdfDesktopOnly"), "error");
        return;
      }
      window.jotva
        .exportPdf(m.title)
        .then((res) => {
          if (!res?.ok) throw new Error(res?.error || "Export failed");
          showToast(t("notes.toast.exported", { fmt: "PDF" }));
          showInFolder(res.path);
        })
        .catch((e) => showToast(e.message, "error"));
      return;
    }
    api
      .post(`/api/export/${m.id}/${fmt}`)
      .then(({ path }) => {
        showToast(t("notes.toast.exported", { fmt: fmt.toUpperCase() }));
        showInFolder(path);
      })
      .catch((e) => showToast(e.message, "error"));
  };

  const copySlackDigest = () => {
    setMenu(null);
    api
      .get(`/api/export/${m.id}/slack`)
      .then(({ text }) =>
        navigator.clipboard.writeText(text).then(() => showToast(t("notes.toast.slackCopied")))
      )
      .catch((e) => showToast(e.message, "error"));
  };

  const sendTo = (provider) => {
    setMenu(null);
    showToast(t("notes.toast.sendingTo", { label: INTEGRATION_LABELS[provider] }));
    api
      .post(`/api/integrations/${provider}/send/${m.id}`)
      .then((r) => showToast(r.message))
      .catch((e) => showToast(e.message, "error"));
  };

  const regenerateWith = (templateId) => {
    setMenu(null);
    api
      .post(`/api/meetings/${m.id}/regenerate`, { template_id: templateId })
      .then(() => showToast(t("notes.toast.regenerating")))
      .catch((e) => showToast(e.message, "error"));
  };

  const started = new Date(m.started_at);
  const isToday = started.toDateString() === new Date().toDateString();
  const fmtDate = `${
    isToday
      ? t("notes.header.today")
      : started.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" })
  }, ${started.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`;
  const durationMins =
    m.started_at && m.ended_at ? Math.round((new Date(m.ended_at) - started) / 60000) : 0;
  const durationLabel =
    durationMins >= 60
      ? `${Math.floor(durationMins / 60)}h ${durationMins % 60 ? `${durationMins % 60}m` : ""}`.trim()
      : `${durationMins}m`;

  const busy = ["recording", "transcribing", "generating"].includes(live);
  const ready = !busy && live !== "error" && m.notes;

  const visibleActions = showAllActions ? actions : actions.slice(0, ACTIONS_PREVIEW);
  const hiddenActionCount = actions.length - visibleActions.length;
  const firstMarker = markers.length > 0 ? markers[0] : null;

  return (
    <div className="workspace">
      <div className="ws-inner" data-tour="notes-panel">
        <div className="ws-header">
          <div className="ws-header-left">
            <div className="ws-title-row">
              <h1 className="ws-title">{m.title}</h1>
              {!!m.is_demo && <span className="demo-badge">{t("list.demoBadge")}</span>}
              <button
                className={`ws-star${m.starred ? " on" : ""}`}
                title={m.starred ? t("notes.header.unstar") : t("notes.header.star")}
                onClick={toggleStar}
              >
                <StarIcon size={19} filled={!!m.starred} />
              </button>
            </div>
            <div className="ws-meta">
              <span>{fmtDate}</span>
              {durationMins > 0 && (
                <span className="meta-item">
                  <ClockIcon size={14} /> {durationLabel}
                </span>
              )}
              {participants.length > 0 && (
                <span className="meta-item">
                  <UsersIcon size={14} /> {t("notes.header.attendee", { count: participants.length })}
                </span>
              )}
            </div>
          </div>
          <div className="ws-header-right">
            {participants.length > 0 && (
              <span className="avatar-stack" title={participants.join(", ")}>
                {participants.slice(0, 3).map((p, i) => (
                  <span
                    className="avatar"
                    key={p}
                    style={{ background: AVATAR_COLORS[i % AVATAR_COLORS.length] }}
                  >
                    {initials(p)}
                  </span>
                ))}
                {participants.length > 3 && (
                  <span className="avatar" style={{ background: "var(--surface-2)", color: "var(--muted)" }}>
                    +{participants.length - 3}
                  </span>
                )}
              </span>
            )}
            {/* Public share button removed: it minted jotva:// URLs no recipient
                could open (backend is loopback-only). Team sharing via the
                workspace folder still works from the menu. */}
            <div className="row-menu" style={{ position: "relative", top: 0, right: 0 }} ref={menuRef}>
              <button
                className="icon-btn"
                aria-label={t("notes.header.moreOptions")}
                onClick={() => setMenu(menu ? null : "main")}
              >
                <DotsIcon size={16} />
              </button>
              {menu === "main" && (
                <div className="card-menu-dropdown" role="menu">
                  <button
                    className="menu-item"
                    onClick={() => {
                      setMenu(null);
                      setFollowUpOpen(true);
                    }}
                  >
                    {t("notes.toolbar.followup")}
                  </button>
                  <button className="menu-item" onClick={() => doExport("pdf")}>
                    {t("notes.toolbar.pdf")}
                  </button>
                  <button className="menu-item" onClick={() => doExport("markdown")}>
                    {t("notes.toolbar.md")}
                  </button>
                  <button className="menu-item" onClick={copySlackDigest}>
                    {t("notes.toolbar.slackDigest")}
                  </button>
                  <button className="menu-item" onClick={() => setMenu("send")}>
                    {t("notes.toolbar.sendTo")} ›
                  </button>
                  <button className="menu-item" onClick={() => setMenu("regen")}>
                    {t("notes.toolbar.regenerate")} ›
                  </button>
                  <div className="menu-divider" />
                  <button
                    className="menu-item"
                    onClick={() => {
                      setMenu(null);
                      api
                        .post(`/api/meetings/${m.id}/share-to-workspace`)
                        .then(() => showToast(t("notes.toast.sharedTeam")))
                        .catch((e) => showToast(e.message, "error"));
                    }}
                  >
                    {t("notes.header.shareTeam")}
                  </button>
                  <button
                    className="delete-menu-item"
                    onClick={() => {
                      setMenu(null);
                      setConfirmDelete(true);
                    }}
                  >
                    {t("notes.header.deleteMeeting")}
                  </button>
                </div>
              )}
              {menu === "send" && (
                <div className="card-menu-dropdown" role="menu">
                  {Object.entries(INTEGRATION_LABELS).map(([key, label]) => (
                    <button key={key} className="menu-item" onClick={() => sendTo(key)}>
                      {label}
                    </button>
                  ))}
                </div>
              )}
              {menu === "regen" && (
                <div className="card-menu-dropdown" role="menu">
                  {templates.map((tpl) => (
                    <button key={tpl.id} className="menu-item" onClick={() => regenerateWith(tpl.id)}>
                      {tpl.name}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {busy ? (
          <div className="empty-state" style={{ height: "auto", padding: "120px 24px" }}>
            <div className="empty-title">{t("processing.growing")}</div>
            <div className="empty-sub">{t("processing.takesAbout")}</div>
          </div>
        ) : live === "error" ? (
          <div className="callout risk" style={{ marginTop: 28 }}>
            <WarnIcon size={15} />
            <div className="callout-body">
              <div className="callout-title">{t("notes.error.processingFailed")}</div>
              <div className="section-body">
                <p>{m.error || t("notes.error.processingFailedSub")}</p>
              </div>
              <button className="btn compact" style={{ marginTop: 10 }} onClick={() => regenerateWith(null)}>
                {t("notes.error.retry")}
              </button>
            </div>
          </div>
        ) : !m.notes ? (
          <div className="empty-state" style={{ height: "auto", padding: "80px 24px" }}>
            <div className="empty-sub">{t("notes.error.noNotes")}</div>
          </div>
        ) : (
          <>
            <div className="ws-tabs" ref={tabsRef} onPointerLeave={() => setTabHover(null)}
              onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) setTabHover(null); }}>
              <span {...tabLens} />
              {["overview", "timeline", "transcript", "ask"].map((k) => (
                <button
                  key={k}
                  ref={(el) => { tabRefs.current[k] = el; }}
                  className={`ws-tab${tab === k ? " active" : ""}`}
                  onPointerEnter={() => setTabHover(k)}
                  onFocus={() => setTabHover(k)}
                  onClick={() => setTab(k)}
                >
                  {t(`notes.tab.${k}`)}
                </button>
              ))}
            </div>

            {tab === "overview" && ready && (
              <div className="ws-tabbody">
                {headsUp.length > 0 && (
                  <div className="callout heads-up-callout ov-banner" role="note" aria-label={t("notes.bar.headsUp")}>
                    <WarnIcon size={15} />
                    <div className="ov-banner-body">{headsUp.map((h, i) => <span key={i}>{h}</span>)}</div>
                  </div>
                )}
                {hasContent(compliance) && (
                  <div className="callout risk ov-banner">
                    <WarnIcon size={15} />
                    <div className="ov-banner-body"><strong>{t("notes.section.compliance")}</strong><Markdown text={compliance} /></div>
                  </div>
                )}
                {riskEntries.map(([name, body]) => (
                  <div className="callout risk ov-banner" key={name}>
                    <WarnIcon size={15} />
                    <div className="ov-banner-body"><strong>{name}</strong><Markdown text={body} /></div>
                  </div>
                ))}
                {conflicts.map((c) => (
                  <ConflictCard key={c.id} conflict={c} onResolve={resolveConflict} />
                ))}

                {/* the one deliberate green moment */}
                <div className="summary-hero">
                  <img className="summary-hero-watermark" src={logoUrl} alt="" aria-hidden="true" />
                  <div className="summary-hero-head">
                    <img className="logo-img" src={logoUrl} alt="" aria-hidden="true" />
                    <span className="summary-eyebrow">{t("notes.section.summaryBy")}</span>
                  </div>
                  {executiveSummary ? (
                    <p className="summary-body">{renderSummary(executiveSummary)}</p>
                  ) : (
                    <p className="summary-body summary-empty">{t("notes.section.noSummary")}</p>
                  )}
                </div>

                <div className="ov-columns">
                  <div className="ov-col-left">
                    <div className="ov-section-head">
                      <span className="ov-eyebrow">{t("notes.section.actions")}</span>
                      <span className="ov-count">{actions.length}</span>
                    </div>
                    {actions.length === 0 ? (
                      <div className="section-empty-note">{t("notes.action.none")}</div>
                    ) : (
                      <>
                        {visibleActions.map((a) => (
                          <ActionRow key={a.id} item={a} onAssign={assign} onComplete={completeAction} />
                        ))}
                        {hiddenActionCount > 0 && (
                          <button className="ov-show-more" onClick={() => setShowAllActions(true)}>
                            {t("notes.action.showMore", { count: hiddenActionCount })}
                          </button>
                        )}
                      </>
                    )}

                    <div className="ov-section-head ov-section-head-spaced">
                      <span className="ov-eyebrow">{t("notes.section.decisions")}</span>
                      <span className="ov-count">{decisions.length}</span>
                    </div>
                    {decisions.length === 0 ? (
                      <div className="section-empty-note">{t("notes.decisions.none")}</div>
                    ) : (
                      decisions.map((d) => (
                        <div className="ov-decision-row" key={d.id}>
                          <span className="ov-decision-dot" />
                          <span className={d.status === "superseded" ? "superseded" : ""}>{d.text}</span>
                        </div>
                      ))
                    )}

                    {keyDiscussions.trim() && (
                      <>
                        <div className="ov-section-head ov-section-head-spaced">
                          <span className="ov-eyebrow">{t("notes.section.discussions")}</span>
                        </div>
                        <div className="ov-discussions"><Markdown text={keyDiscussions} /></div>
                      </>
                    )}
                  </div>

                  <div className="ov-col-right">
                    <div className="ov-eyebrow">{t("notes.section.topics")}</div>
                    {topics.length === 0 ? (
                      <div className="section-empty-note">{t("notes.action.none")}</div>
                    ) : (
                      <div className="ov-topic-chips">
                        {topics.map((tp) => (
                          <span className="ov-topic-chip" key={tp}>
                            {tp}
                          </span>
                        ))}
                      </div>
                    )}

                    {questionEntries.length > 0 &&
                      questionEntries.map(([name, body]) => (
                        <React.Fragment key={name}>
                          <div className="ov-section-head ov-section-head-spaced">
                            <span className="ov-eyebrow">{t("notes.section.questions")}</span>
                          </div>
                          <div className="ov-questions">
                            <Markdown text={body} />
                          </div>
                        </React.Fragment>
                      ))}

                    {firstMarker != null && (
                      <>
                        <div className="ov-eyebrow ov-eyebrow-spaced">{t("notes.section.highlight")}</div>
                        {m.audio_path ? (
                          <button className="ov-highlight-card ov-highlight-play"
                            onClick={() => { setJump({ sec: firstMarker, id: Date.now() }); setTab("transcript"); }}>
                            <span className="ov-play" aria-hidden="true"><PlayIcon size={11} /></span>
                            <span className="ov-highlight-text">{t("notes.section.flaggedMoment")}</span>
                            <span className="ov-highlight-time">{fmtClock(firstMarker)}</span>
                          </button>
                        ) : (
                          <div className="ov-highlight-card">
                            <span className="ov-highlight-text">{t("notes.section.flaggedMoment")}</span>
                            <span className="ov-highlight-time">{fmtClock(firstMarker)}</span>
                          </div>
                        )}
                      </>
                    )}

                    {nextSteps.trim() && (
                      <>
                        <div className="ov-eyebrow ov-eyebrow-spaced">{t("notes.section.nextSteps")}</div>
                        {listItems(nextSteps) ? (
                          <ol className="ov-steps">{listItems(nextSteps).map((step, i) => <li key={i}>{renderSummary(step)}</li>)}</ol>
                        ) : (
                          <Markdown text={nextSteps} />
                        )}
                      </>
                    )}
                  </div>
                </div>

                {otherEntries.map(([name, body]) => (
                  <div className="plain-section" key={name}>
                    <div className="surface-title">{name}</div>
                    <Markdown text={body} />
                  </div>
                ))}
                {related.length > 0 && (
                  <div className="plain-section">
                    <div className="surface-title">{t("notes.section.relatedMeetings")}</div>
                    {related.map((r) => (
                      <button
                        key={r.meeting_id}
                        className="related-row"
                        onClick={() => selectMeeting(r.meeting_id)}
                      >
                        <span className="related-title">{r.title}</span>
                        <span className="topic-chips">
                          {r.shared_topics.map((tp) => (
                            <span className="topic-tag" key={tp}>
                              {tp}
                            </span>
                          ))}
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {tab === "timeline" && (
              <div className="ws-tabbody">
                <TimelineTab meeting={m} />
              </div>
            )}
            {tab === "transcript" && (
              <div className="ws-tabbody">
                <TranscriptTab meeting={m} jump={jump} />
              </div>
            )}
            {tab === "ask" && (
              <div className="ws-tabbody ask-tabbody">
                <AskTab meeting={m} />
              </div>
            )}
          </>
        )}
      </div>

      {confirmDelete && (
        <Confirm
          title={t("list.deleteTitle")}
          body={t("list.deleteBody", { title: m.title })}
          confirmLabel={t("common.delete")}
          danger
          onConfirm={() => {
            setConfirmDelete(false);
            deleteMeeting(m.id);
          }}
          onCancel={() => setConfirmDelete(false)}
        />
      )}
      {followUpOpen && <FollowUp meeting={m} onClose={() => setFollowUpOpen(false)} />}
      {shareModal && (
        <div
          className="modal-backdrop share-backdrop"
          onMouseDown={(e) => e.target === e.currentTarget && setShareModal(null)}
        >
          <div className="modal share-modal">
            <div className="modal-header">
              <div className="modal-title">{t("notes.share.created")}</div>
              <button className="icon-btn" onClick={() => setShareModal(null)} aria-label={t("notes.share.close")}>
                ✕
              </button>
            </div>
            <div className="modal-body">
              <div className="share-row">
                <input
                  className="text-input"
                  readOnly
                  value={shareModal.url}
                  onFocus={(e) => e.target.select()}
                />
                <button className="btn" onClick={copyShareLink}>
                  {t("notes.share.copyLink")}
                </button>
              </div>
              <div className="field-help share-expires">{t("notes.share.expires")}</div>
              <div className="share-foot">
                <button className="btn secondary" onClick={() => setShareModal(null)}>
                  {t("notes.share.close")}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
