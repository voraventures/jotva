// The signature capture flow — recreated from
// design_handoff_jotva_workspace/CaptureFlow.dc.html: a single 560×640
// card that moves through idle → recording → processing → ready. Recording
// and processing lock the card (no dismissal, matching the "full-app
// takeover" product rule); idle and ready allow backdrop/Escape dismissal.
//
// A 40-sample rolling amplitude array rolls forward on every genuine
// `recording_level` sample from the backend and drives the logo's fan.
import React, { useEffect, useId, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useStore, useLogo } from "../store.jsx";
import { api } from "../api.js";
import { BACK, COLORS, VIEWBOX as LOGO_VIEWBOX, sheetPath } from "../logoGeometry.js";
import { MicIcon, PauseIcon, PlayIcon, RefreshIcon, StopIcon, CheckIcon, XIcon } from "./icons.jsx";

const AMP_LEN = 40;
const TYPE_MS = 30; // ms per character, per spec

// The Jotva mark as a live meter: while recording, the back sheets fan open with
// the speaker's level (quiet = almost stacked, loud = fully fanned).
function LogoMark({ phase, amp, size = 168 }) {
  const uid = useId().replace(/:/g, "");
  const recent = amp.slice(-8);
  const level = recent.reduce((a, b) => a + b, 0) / recent.length;
  const fan = phase === "recording" ? Math.min(1.1, 0.35 + level * 0.75) : phase === "processing" ? 0.8 : 1;
  const grad = (id, stops) => (
    <linearGradient id={`${uid}${id}`} x1="1" y1="0" x2="0" y2="1">
      {stops.map(([o, c]) => <stop key={o} offset={o} stopColor={c} />)}
    </linearGradient>
  );
  const sheet = (d, id) => (
    <path d={d} fill={`url(#${uid}${id})`} style={{ d: `path("${d}")`, transition: "d 140ms ease-out" }} />
  );
  return (
    <svg width={size} height={(size * 664) / 715} viewBox={LOGO_VIEWBOX} aria-hidden="true">
      <defs>{grad("f", COLORS.front)}{grad("m", COLORS.mid)}{grad("b", COLORS.back)}</defs>
      {sheet(sheetPath(BACK[1], fan), "b")}
      {sheet(sheetPath(BACK[0], fan), "m")}
      {sheet(sheetPath(undefined, 0), "f")}
    </svg>
  );
}

function fmtElapsed(totalSec) {
  const s = Math.max(0, Math.floor(totalSec));
  const m = String(Math.floor(s / 60)).padStart(2, "0");
  const ss = String(s % 60).padStart(2, "0");
  return `${m}:${ss}`;
}

function stripMarkdown(text) {
  return (text || "").replace(/\*\*(.*?)\*\*/g, "$1").replace(/[_`]/g, "").trim();
}

export default function CaptureFlow() {
  const { t } = useTranslation();
  const {
    recording,
    recordingLevel,
    paused,
    muted,
    togglePause,
    stopRecording,
    startRecording,
    processingId,
    readyMeetingId,
    setReadyMeetingId,
    captureOpen,
    setCaptureOpen,
    meetings,
    meetingDetail,
    selectMeeting,
    setNav,
    progress,
    settings,
  } = useStore();
  const logoUrl = useLogo();
  const [systemReducedMotion, setSystemReducedMotion] = useState(false);
  useEffect(() => {
    const query = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (!query) return;
    const update = () => setSystemReducedMotion(query.matches);
    update(); query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  const reducedMotion = settings?.reduce_motion || systemReducedMotion;

  const phase = recording.active
    ? "recording"
    : processingId
      ? "processing"
      : readyMeetingId
        ? "ready"
        : captureOpen
          ? "idle"
          : null;

  // ---- real rolling amplitude array (indices sampled by the 7 logo bars) ----
  const [amp, setAmp] = useState(() => new Array(AMP_LEN).fill(0.28));
  useEffect(() => {
    if (phase !== "recording") return;
    const level = paused || muted ? 0 : Math.min(1, Math.max(0, recordingLevel || 0));
    setAmp((prev) => [...prev.slice(1), level]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recordingLevel, phase, paused, muted]);
  useEffect(() => {
    if (phase === "idle") setAmp(new Array(AMP_LEN).fill(0.28));
  }, [phase]);

  // ---- elapsed mm:ss (recording controls row) — stands still while paused ----
  const startRef = useRef(Date.now());
  const pausedTotalRef = useRef(0);
  const pauseStartRef = useRef(null);
  const [now, setNow] = useState(Date.now());
  const recMeeting = meetings.find((m) => m.id === recording.meetingId);

  useEffect(() => {
    const started = recMeeting?.started_at ? new Date(recMeeting.started_at).getTime() : Date.now();
    if (!isNaN(started)) startRef.current = started;
    pausedTotalRef.current = 0;
    pauseStartRef.current = null;
  }, [recMeeting?.id]);

  useEffect(() => {
    if (paused) pauseStartRef.current = Date.now();
    else if (pauseStartRef.current) {
      pausedTotalRef.current += Date.now() - pauseStartRef.current;
      pauseStartRef.current = null;
    }
  }, [paused]);

  useEffect(() => {
    if (phase !== "recording") return undefined;
    const id = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(id);
  }, [phase]);

  const reference = paused && pauseStartRef.current ? pauseStartRef.current : now;
  const elapsed = (reference - startRef.current - pausedTotalRef.current) / 1000;
  const startedLabel = recMeeting?.started_at
    ? new Date(recMeeting.started_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
    : "";

  // ---- typewriter over the real generated summary ----
  const readyMeeting =
    (readyMeetingId && meetingDetail?.id === readyMeetingId ? meetingDetail : null) ||
    meetings.find((m) => m.id === readyMeetingId);
  const summary = useMemo(() => {
    const sections = meetingDetail?.id === readyMeetingId ? meetingDetail?.notes?.sections : null;
    return stripMarkdown(sections?.["Executive Summary"] || "");
  }, [meetingDetail, readyMeetingId]);
  const [typed, setTyped] = useState("");
  useEffect(() => {
    if (phase !== "ready" || !summary) {
      setTyped("");
      return undefined;
    }
    if (reducedMotion) { setTyped(summary); return undefined; }
    let i = 0;
    setTyped("");
    const id = setInterval(() => {
      i++;
      setTyped(summary.slice(0, i));
      if (i >= summary.length) clearInterval(id);
    }, TYPE_MS);
    return () => clearInterval(id);
  }, [phase, summary, reducedMotion]);

  // ---- jot pad: the user's own notes while recording, autosaved to steer the AI notes ----
  const jotMeetingId = recording.active ? recording.meetingId : null;
  const [jot, setJot] = useState("");
  const [jotStatus, setJotStatus] = useState("saved"); // saving | saved | error
  const jotTimer = useRef(null);
  const jotLatest = useRef({ id: null, text: "" });
  useEffect(() => { setJot(""); setJotStatus("saved"); }, [jotMeetingId]);
  useEffect(() => () => clearTimeout(jotTimer.current), []);
  const saveJot = (id, text) =>
    api.patch(`/api/meetings/${id}/jot`, { text })
      .then(() => setJotStatus("saved"))
      .catch(() => setJotStatus("error")); // the next keystroke retries
  const onJot = (text) => {
    setJot(text);
    setJotStatus("saving");
    jotLatest.current = { id: jotMeetingId, text };
    clearTimeout(jotTimer.current);
    jotTimer.current = setTimeout(() => { jotTimer.current = null; saveJot(jotMeetingId, text); }, 600);
  };
  // Save any pending jot before stopping, so notes generation sees the latest text.
  const stopWithJot = async () => {
    if (jotTimer.current) {
      clearTimeout(jotTimer.current);
      jotTimer.current = null;
      if (jotLatest.current.id) await saveJot(jotLatest.current.id, jotLatest.current.text);
    }
    stopRecording();
  };

  // Every hook must run unconditionally (before the `if (!phase)` bailout
  // below), including this one — it only *acts* when a dismissible phase
  // is on screen, but it must always be called in the same order.
  const dismissible = phase === "idle" || phase === "ready";
  const dismissibleRef = useRef(dismissible);
  dismissibleRef.current = dismissible;
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape" && dismissibleRef.current) {
        setCaptureOpen(false);
        setReadyMeetingId(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setCaptureOpen, setReadyMeetingId]);

  if (!phase) return null;

  const intel = (meetingDetail?.id === readyMeetingId ? meetingDetail?.intelligence : null) || {};
  const chipCounts = [
    { key: "actions", n: intel.actions?.length || 0 },
    { key: "decisions", n: intel.decisions?.length || 0 },
    { key: "topics", n: intel.topics?.length || 0 },
  ];

  const close = () => {
    if (!dismissible) return;
    setCaptureOpen(false);
    setReadyMeetingId(null);
  };

  const viewMeeting = () => {
    setNav("meetings");
    selectMeeting(readyMeetingId);
    setReadyMeetingId(null);
  };
  const replay = () => {
    setReadyMeetingId(null);
    setCaptureOpen(true);
  };

  const title =
    phase === "idle"
      ? t("capture.idleTitle")
      : phase === "recording"
        ? t("capture.recordingTitle")
        : phase === "processing"
          ? t(progress[processingId]?.stage === 'speaker_analysis' ? 'speakers.processing' : "processing.growing")
          : readyMeeting?.title || "";
  const subtitle =
    phase === "idle"
      ? t("capture.idleSubtitle")
      : phase === "recording"
        ? t("capture.recordingSubtitle", { time: startedLabel })
        : phase === "processing"
          ? t("processing.takesAbout")
          : typed;
  const caretOn = phase === "ready" && summary && typed.length < summary.length;
  const pct = progress[processingId]?.pct;

  return (
    <div
      className="capture-backdrop"
      onMouseDown={(e) => e.target === e.currentTarget && close()}
    >
      <div className={`capture-card${phase === "recording" ? " is-recording" : ""}`} role="dialog" aria-modal="true" aria-label={title}>
        <div className="capture-header">
          <img className="logo-img" src={logoUrl} alt="" aria-hidden="true" />
          <span className="capture-wordmark brand-wordmark">Jotva</span>
          <div style={{ flex: 1 }} />
          {dismissible && <button className="icon-btn" aria-label={t("common.close")} onClick={close}><XIcon size={20} /></button>}
          {phase === "recording" && (
            <span className="capture-rec">
              <span className="capture-rec-dot" />
              {t("capture.rec")}
            </span>
          )}
        </div>

        <div className="capture-stage">
          {phase === "processing" && (
            <div className="capture-rings" aria-hidden="true">
              <svg width="300" height="300" viewBox="0 0 300 300" className="capture-ring-outer">
                <circle cx="150" cy="150" r="140" fill="none" strokeDasharray="2 14" strokeLinecap="round" />
              </svg>
              <svg width="238" height="238" viewBox="0 0 238 238" className="capture-ring-inner">
                <circle cx="119" cy="119" r="110" fill="none" strokeDasharray="2 18" strokeLinecap="round" />
              </svg>
            </div>
          )}
          <div className={`capture-mark phase-${phase}`}>
            <LogoMark phase={phase} amp={amp} />
            {phase === "ready" && (
              <span className="capture-ready-check" key={readyMeetingId}>
                <CheckIcon size={20} strokeWidth={3.2} />
              </span>
            )}
          </div>
        </div>

        <div className="capture-caption">
          <div className="capture-title">{title}</div>
          <div className="capture-subtitle">
            {subtitle}
            {caretOn && <span className="capture-caret" />}
          </div>
        </div>

        {phase === "ready" && (
          <div className="capture-chips">
            {chipCounts.map((c, i) => (
              <span className="capture-chip" style={{ animationDelay: `${0.5 + i * 0.14}s` }} key={c.key}>
                {t(`capture.chip.${c.key}`, { count: c.n })}
              </span>
            ))}
          </div>
        )}

        {phase === "recording" && (
          <div className="capture-jot">
            <label htmlFor="capture-jot-input" className="capture-jot-label">
              <span>{t("capture.jot.label")}</span>
              {jot && <span className={`capture-jot-status ${jotStatus}`}>{t(`capture.jot.${jotStatus}`)}</span>}
            </label>
            <textarea id="capture-jot-input" autoFocus value={jot} maxLength={20000} spellCheck
              placeholder={t("capture.jot.placeholder")} onChange={(e) => onJot(e.target.value)} />
          </div>
        )}

        <div className="capture-controls">
          {phase === "idle" && (
            <button className="capture-start-btn" onClick={() => startRecording()}>
              <MicIcon size={17} />
              {t("capture.startRecording")}
            </button>
          )}
          {phase === "recording" && (
            <>
              <span className="capture-timer">{fmtElapsed(elapsed)}</span>
              <button
                className={`capture-round-btn${paused ? " active" : ""}`}
                onClick={togglePause}
                aria-label={paused ? t("recording.resume") : t("recording.pause")}
                title={paused ? t("recording.resume") : t("recording.pause")}
              >
                {paused ? <PlayIcon size={16} /> : <PauseIcon size={16} />}
              </button>
              <button
                className="capture-round-btn stop"
                onClick={stopWithJot}
                aria-label={t("recording.stop")}
                title={t("recording.stop")}
              >
                <StopIcon size={17} />
              </button>
            </>
          )}
          {phase === "processing" && (
            <div className="capture-dots" aria-label={t("processing.growing")}>
              <span style={{ animationDelay: "0s" }} />
              <span style={{ animationDelay: "0.2s" }} />
              <span style={{ animationDelay: "0.4s" }} />
              {pct != null && <span className="capture-dots-pct">{Math.round(pct * 100)}%</span>}
            </div>
          )}
          {phase === "ready" && (
            <>
              <button className="capture-view-btn" onClick={viewMeeting}>
                {t("capture.viewMeeting")}
              </button>
              <button className="capture-replay-btn" onClick={replay}>
                <RefreshIcon size={15} />
                {t("capture.replay")}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
