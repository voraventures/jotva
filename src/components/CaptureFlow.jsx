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
import Markdown from "./Markdown.jsx";
import { MicIcon, PauseIcon, PlayIcon, RefreshIcon, StopIcon, CheckIcon, XIcon } from "./icons.jsx";

const AMP_LEN = 40;
const TYPE_MS = 30; // ms per character, per spec

// Idle "snap-fan + light sweep" (the approved logo motion, design-reference/
// logo-animations). When the window opens the back sheets tuck in and spring
// back out one after the other, once; the light keeps sweeping across the
// resting mark every SWEEP_EVERY_MS, and the glow stays on.
const IDLE_INTRO_MS = 2200;
const SWEEP_EVERY_MS = 3000;
const easeInCubic = (x) => x * x * x;
const spring = (x) => (x <= 0 ? 0 : 1 - Math.exp(-7 * x) * Math.cos(9 * x));
function idleFan(t, i) {
  if (t >= IDLE_INTRO_MS) return 1; // fanned once; stays at rest
  if (t < 300) return 1 - easeInCubic(t / 300); // tuck in
  if (t < 450) return 0; // hold collapsed
  return spring(((t - 450 - i * 110) / 1000) * 1.9); // staggered snap out
}
const idleSweep = (t) => (t < 850 ? 0 : Math.min(1, ((t - 850) % SWEEP_EVERY_MS) / 750));

function useIdleClock(active) {
  const [t, setT] = useState(IDLE_INTRO_MS); // rest pose until the first frame
  useEffect(() => {
    if (!active) return undefined;
    const start = performance.now();
    let raf = requestAnimationFrame(function tick(now) {
      setT(now - start);
      raf = requestAnimationFrame(tick);
    });
    return () => cancelAnimationFrame(raf);
  }, [active]);
  return t;
}

// The Jotva mark as a live meter: while recording, the back sheets fan open with
// the speaker's level (quiet = almost stacked, loud = fully fanned). While idle
// it fans once, then keeps a light sweeping across it (unless motion is reduced).
function LogoMark({ phase, amp, size = 168, animate = false }) {
  const uid = useId().replace(/:/g, "");
  const idle = animate && phase === "idle";
  const t = useIdleClock(idle);
  const recent = amp.slice(-8);
  const level = recent.reduce((a, b) => a + b, 0) / recent.length;
  const fan = phase === "recording" ? Math.min(1.1, 0.35 + level * 0.75) : phase === "processing" ? 0.8 : 1;
  const fans = idle ? [idleFan(t, 0), idleFan(t, 1)] : [fan, fan];
  const sweep = idle ? idleSweep(t) : 0;
  const grad = (id, stops) => (
    <linearGradient id={`${uid}${id}`} x1="1" y1="0" x2="0" y2="1">
      {stops.map(([o, c]) => <stop key={o} offset={o} stopColor={c} />)}
    </linearGradient>
  );
  const paths = [sheetPath(BACK[1], fans[1]), sheetPath(BACK[0], fans[0]), sheetPath(undefined, 0)];
  const sheet = (d, id) => (
    <path d={d} fill={`url(#${uid}${id})`} style={idle ? undefined : { d: `path("${d}")`, transition: "d 140ms ease-out" }} />
  );
  return (
    <svg width={size} height={(size * 664) / 715} viewBox={LOGO_VIEWBOX} aria-hidden="true" overflow="visible">
      <defs>
        {grad("f", COLORS.front)}{grad("m", COLORS.mid)}{grad("b", COLORS.back)}
        <linearGradient id={`${uid}sw`} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#fff" stopOpacity="0" />
          <stop offset=".5" stopColor="#fff" stopOpacity=".7" />
          <stop offset="1" stopColor="#fff" stopOpacity="0" />
        </linearGradient>
        <filter id={`${uid}bloom`} x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="22" /></filter>
        <clipPath id={`${uid}clip`}>{paths.map((d) => <path key={d} d={d} />)}</clipPath>
      </defs>
      {phase === "idle" && (
        <g filter={`url(#${uid}bloom)`} opacity={0.5 + 0.2 * Math.sin(Math.PI * sweep)}>
          <path d={paths[0]} fill="#7a3df6" /><path d={paths[1]} fill="#3452f6" /><path d={paths[2]} fill="#4e90f8" />
        </g>
      )}
      {sheet(paths[0], "b")}
      {sheet(paths[1], "m")}
      {sheet(paths[2], "f")}
      {sweep > 0 && sweep < 1 && (
        <g clipPath={`url(#${uid}clip)`}>
          <rect x="-160" y="-1000" width="200" height="1400" fill={`url(#${uid}sw)`}
            style={{ mixBlendMode: "screen" }} transform={`rotate(22) translate(${-420 + sweep * 1000} 0)`} />
        </g>
      )}
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
    openSettings,
    meetingLiveNotes,
    liveTranscriptChunks,
    hasFeature,
    openUpgrade,
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

  // Manual recordings are named by the user (calendar recordings take the event's
  // name). Left blank, Jotva suggests a name once the notes are written.
  const [meetingName, setMeetingName] = useState("");
  useEffect(() => {
    if (phase === "idle") setMeetingName("");
  }, [phase]);
  const start = () => startRecording({ title: meetingName.trim() });

  // Recording card tabs: the jot pad (default) and Pro live notes.
  const [recTab, setRecTab] = useState("jots");
  const [seenLiveAt, setSeenLiveAt] = useState(0);
  useEffect(() => {
    if (phase === "recording") setRecTab("jots");
  }, [phase]);
  const liveForThis = meetingLiveNotes && meetingLiveNotes.meetingId === recording.meetingId ? meetingLiveNotes : null;
  useEffect(() => {
    if (recTab === "live" && liveForThis) setSeenLiveAt(liveForThis.at);
  }, [recTab, liveForThis]);
  const liveUnseen = !!liveForThis && liveForThis.at > seenLiveAt && recTab !== "live";
  const showLiveTab = () => (hasFeature("live_notes") ? setRecTab("live") : openUpgrade("live_notes"));

  // Which microphone "Start recording" will use, so a wrong or missing input is
  // visible (and fixable) before the meeting, not after.
  const [micName, setMicName] = useState(null);
  useEffect(() => {
    if (phase !== "idle") return;
    api.get("/api/recording/devices").then((d) => {
      const chosen = d.devices?.find((dev) => dev.index === d.mic_device);
      const name = chosen?.name || d.default_input?.name;
      const virtual = chosen ? chosen.is_loopback_like : d.default_input?.is_loopback_like;
      const real = d.devices?.find((dev) => !dev.is_loopback_like);
      setMicName(virtual ? real?.name || "" : name || "");
    }).catch(() => setMicName(null));
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
          ? t(progress[processingId]?.stage === 'speaker_analysis' ? 'speakers.processing' : "processing.jotting")
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
            <LogoMark phase={phase} amp={amp} animate={!reducedMotion} />
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

        {phase === "idle" && (
          <div className="capture-name">
            <label htmlFor="capture-name-input">{t("capture.name.label")}</label>
            <input id="capture-name-input" autoFocus value={meetingName} maxLength={300} spellCheck
              placeholder={t("capture.name.placeholder")} onChange={(e) => setMeetingName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && start()} />
          </div>
        )}

        {phase === "recording" && (
          <div className="capture-jot">
            <div className="capture-tabs" role="tablist">
              <button type="button" role="tab" aria-selected={recTab === "jots"} className={recTab === "jots" ? "on" : ""}
                onClick={() => setRecTab("jots")}>{t("capture.jot.label")}</button>
              <button type="button" role="tab" aria-selected={recTab === "live"} className={recTab === "live" ? "on" : ""}
                onClick={showLiveTab}>
                {t("capture.live.tab")}
                {!hasFeature("live_notes") && <span className="pro-badge">{t("upgrade.badge")}</span>}
                {liveUnseen && <span className="capture-tab-dot" aria-label={t("capture.live.updated")} />}
              </button>
              {recTab === "jots" && jot && <span className={`capture-jot-status ${jotStatus}`}>{t(`capture.jot.${jotStatus}`)}</span>}
            </div>
            {recTab === "jots" ? (
              <textarea id="capture-jot-input" aria-label={t("capture.jot.label")} autoFocus value={jot} maxLength={20000} spellCheck
                placeholder={t("capture.jot.placeholder")} onChange={(e) => onJot(e.target.value)} />
            ) : (
              <div className="capture-live" aria-live="polite">
                {liveForThis ? (
                  <>
                    <Markdown text={liveForThis.text} />
                    <div className="capture-live-foot">{t("capture.live.updatedAgo", { time: new Date(liveForThis.at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) })}</div>
                  </>
                ) : liveTranscriptChunks.length ? (
                  <div className="capture-live-hearing">
                    <div className="capture-live-status"><span className="live-dot" aria-hidden="true" />{t("capture.live.starting")}</div>
                    <p>“{liveTranscriptChunks[liveTranscriptChunks.length - 1]}”</p>
                  </div>
                ) : (
                  <div className="capture-live-empty">{t("capture.live.empty")}</div>
                )}
              </div>
            )}
          </div>
        )}

        {phase === "idle" && micName !== null && (
          <div className={`capture-mic${micName ? "" : " missing"}`}>
            <MicIcon size={13} aria-hidden="true" />
            <span>{micName ? t("capture.mic.using", { name: micName }) : t("capture.mic.none")}</span>
            <button type="button" onClick={() => openSettings("recording")}>{t("capture.mic.change")}</button>
          </div>
        )}

        <div className="capture-controls">
          {phase === "idle" && (
            <button className="capture-start-btn" onClick={start}>
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
            <div className="capture-dots" aria-label={t("processing.jotting")}>
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
