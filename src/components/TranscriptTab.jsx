// Transcript tab — recreated from Jotva Meeting.dc.html #5d: a player bar
// (dark play button, mm:ss, green progress + handle, speed), avatar +
// name + timestamp + paragraph turns, the "now playing" turn lit with a
// green keyline while past turns dim. The mockup's right rail ("search +
// Chapters") is rebuilt on real data only: transcript search (filters real
// segments) and a Moments list of real user-flagged markers — never
// fabricated chapter titles/timestamps we have no way to generate for real.
import React, { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, mediaUrl } from "../api.js";
import { useStore } from '../store.jsx';
import { transcriptText } from '../transcriptText.js';
import { PauseIcon, PlayIcon, SearchIcon } from "./icons.jsx";

const SPEEDS = [1, 1.25, 1.5, 2];
const AVATAR_COLORS = ["var(--av-amber)", "var(--av-teal)", "var(--av-purple)", "var(--av-green)"];

function fmtTs(sec) {
  const s = Math.max(0, Math.floor(sec || 0));
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}

function speakerInitials(name) {
  const m = /Speaker[\s_]*(\d+)/i.exec(name || "");
  if (m) return `S${m[1]}`;
  return (name || "")
    .split(/\s+/)
    .map((w) => w[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

function speakerColorIndex(name) {
  const m = /Speaker\s*(\d+)/i.exec(name || "");
  const n = m ? parseInt(m[1], 10) : 1;
  return (n - 1) % AVATAR_COLORS.length;
}

export default function TranscriptTab({ meeting, jump }) {
  const { t } = useTranslation();
  const { refreshDetail, showToast } = useStore();
  const [retrying, setRetrying] = useState(false);
  const segments = meeting.transcript?._segments || [];
  const markers = meeting.markers || [];
  const hasAudio = !!meeting.audio_path;
  const audioRef = useRef(null);
  const rowRefs = useRef([]);
  const [playing, setPlaying] = useState(false);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(meeting.transcript?.duration_sec || 0);
  const [speed, setSpeed] = useState(1);
  const [query, setQuery] = useState("");

  const src = useMemo(
    () => (hasAudio ? mediaUrl(`/api/meetings/${meeting.id}/audio`) : null),
    [hasAudio, meeting.id]
  );

  useEffect(() => {
    const el = audioRef.current;
    if (!el) return undefined;
    const onTime = () => setCurrent(el.currentTime);
    const onMeta = () => setDuration(el.duration || 0);
    const onEnd = () => setPlaying(false);
    el.addEventListener("timeupdate", onTime);
    el.addEventListener("loadedmetadata", onMeta);
    el.addEventListener("ended", onEnd);
    return () => {
      el.removeEventListener("timeupdate", onTime);
      el.removeEventListener("loadedmetadata", onMeta);
      el.removeEventListener("ended", onEnd);
    };
  }, [src]);

  const togglePlay = () => {
    const el = audioRef.current;
    if (!el) return;
    if (playing) {
      el.pause();
      setPlaying(false);
    } else {
      el.play().then(() => setPlaying(true)).catch(() => {});
    }
  };

  const seek = (sec) => {
    const el = audioRef.current;
    if (el) {
      el.currentTime = sec;
      if (!playing) el.play().then(() => setPlaying(true)).catch(() => {});
    }
    setCurrent(sec);
    const idx = segments.findIndex((s, i) => {
      const next = segments[i + 1];
      return sec >= (s.start ?? 0) && (!next || sec < (next.start ?? Infinity));
    });
    if (idx >= 0) rowRefs.current[idx]?.scrollIntoView({ block: "center", behavior: "smooth" });
  };

  // Opened from an Overview highlight: jump to that moment once the audio is ready.
  useEffect(() => {
    const el = audioRef.current;
    if (!jump || !el) return undefined;
    const go = () => seek(jump.sec);
    if (el.readyState >= 1) { go(); return undefined; }
    el.addEventListener("loadedmetadata", go, { once: true });
    return () => el.removeEventListener("loadedmetadata", go);
  }, [jump?.id, src]); // eslint-disable-line react-hooks/exhaustive-deps

  const cycleSpeed = () => {
    const next = SPEEDS[(SPEEDS.indexOf(speed) + 1) % SPEEDS.length];
    setSpeed(next);
    if (audioRef.current) audioRef.current.playbackRate = next;
  };

  // The segment the playhead is inside — lit while its window is current;
  // segments fully played and passed dim, upcoming ones stay at full read.
  const currentIdx = useMemo(() => {
    if (!segments.length) return -1;
    for (let i = segments.length - 1; i >= 0; i--) {
      if (current >= (segments[i].start ?? 0)) return i;
    }
    return -1;
  }, [segments, current]);

  const matchIndexes = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (q.length < 2) return null;
    return segments.reduce((acc, seg, i) => {
      if ((seg.text || "").toLowerCase().includes(q)) acc.push(i);
      return acc;
    }, []);
  }, [query, segments]);

  if (!segments.length && !meeting.transcript?.text) {
    return (
      <div className="empty-state" style={{ height: "auto", padding: "80px 24px" }}>
        <div className="empty-title">{t("transcript.emptyHead")}</div>
        <div className="empty-sub">{t("transcript.emptySub")}</div>
      </div>
    );
  }

  const pct = duration ? Math.min(100, (current / duration) * 100) : 0;

  return (
    <div className="ws-split">
      <div className="ws-split-main">
        <div className="transcript-actions">
          <button className="btn secondary" onClick={async () => {
            try { await navigator.clipboard.writeText(transcriptText(meeting.transcript, t('timeline.speakerFallback'))); showToast(t('speakers.copied')); }
            catch { showToast(t('notes.toast.copyFailed'), 'error'); }
          }}>{t('speakers.copy')}</button>
          <button className="btn secondary" onClick={() => {
            const url = URL.createObjectURL(new Blob([transcriptText(meeting.transcript, t('timeline.speakerFallback'))], {type: 'text/plain;charset=utf-8'}));
            const link = document.createElement('a'); link.href = url; link.download = 'Jotva-transcript.txt'; link.click();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
          }}>{t('speakers.save')}</button>
        </div>
        {['failed', 'models_missing'].includes(meeting.transcript?.speaker_analysis?.status) && <div className="speaker-notice" role="status">
          <p>{t('speakers.analysisWarning')}</p><p>{t('speakers.retryNote')}</p>
          <button className="btn secondary" disabled={retrying || !hasAudio} onClick={async () => {
            setRetrying(true);
            try { const result = await api.post(`/api/speakers/${meeting.id}/retry`, {}); await refreshDetail(); if (result.status !== 'ready') showToast(t('speakers.error'), 'error'); }
            catch { showToast(t('speakers.error'), 'error'); } finally { setRetrying(false); }
          }}>{t(retrying ? 'speakers.processing' : 'speakers.retryAnalysis')}</button>
        </div>}
        {meeting.transcript?.speaker_analysis?.named_speakers > 0 && <div className="speaker-notice">{t('speakers.displayNames')}</div>}
        {src && (
          <>
            <audio ref={audioRef} src={src} preload="metadata" />
            <div className="playback">
              <button
                className="pb-play"
                onClick={togglePlay}
                aria-label={playing ? t("transcript.pause") : t("transcript.play")}
              >
                {playing ? <PauseIcon size={14} /> : <PlayIcon size={14} />}
              </button>
              <span className="pb-time">{fmtTs(current)}</span>
              <input
                className="pb-scrub"
                type="range"
                min={0}
                max={duration || 0}
                step={0.1}
                value={Math.min(current, duration || 0)}
                style={{ "--pb-pct": `${pct}%` }}
                onChange={(e) => seek(Number(e.target.value))}
                aria-label={t("transcript.scrub")}
              />
              <span className="pb-time">{fmtTs(duration)}</span>
              <button className="pb-speed" onClick={cycleSpeed}>
                {speed}×
              </button>
            </div>
          </>
        )}

        {segments.length ? (
          <div className="tr-turns">
            {segments.map((seg, i) => {
              const isCurrent = i === currentIdx && (playing || current > 0);
              const isPast = i < currentIdx;
              const dimmed = isPast && !isCurrent;
              const matched = matchIndexes && matchIndexes.includes(i);
              return (
                <div
                  key={i}
                  ref={(el) => (rowRefs.current[i] = el)}
                  className={`tr-turn${isCurrent ? " current" : ""}${dimmed ? " past" : ""}${matched ? " matched" : ""}`}
                  role={src ? "button" : undefined}
                  tabIndex={src ? 0 : undefined}
                  onClick={src ? () => seek(seg.start ?? 0) : undefined}
                  onKeyDown={src ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); seek(seg.start ?? 0); } } : undefined}
                >
                  <span
                    className="tr-avatar"
                    style={{ background: AVATAR_COLORS[speakerColorIndex((seg.speaker_id || seg.speaker)?.replace('_', ' '))] }}
                  >
                    {speakerInitials(seg.speaker || t("timeline.speakerFallback"))}
                  </span>
                  <div className="tr-turn-main">
                    <div className="tr-turn-head">
                      <span className="tr-speaker">{seg.speaker || t("timeline.speakerFallback")}</span>
                      <span className="tr-time">
                        {fmtTs(seg.start)}
                        {isCurrent && ` · ${t("transcript.nowPlaying")}`}
                      </span>
                    </div>
                    <p className="tr-text">{seg.text}</p>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="tr-plain">{meeting.transcript.text}</p>
        )}
      </div>

      {segments.length > 0 && (
        <div className="ws-rail">
          <div className="rail-search">
            <SearchIcon size={15} />
            <input
              placeholder={t("transcript.searchPlaceholder")}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              spellCheck={false}
            />
          </div>
          {matchIndexes && (
            <div className="rail-search-count">
              {t("transcript.matchCount", { count: matchIndexes.length })}
            </div>
          )}
          <div className="rail-label">{t("transcript.moments")}</div>
          {markers.length === 0 ? (
            <div className="section-empty-note">{t("transcript.noMoments")}</div>
          ) : (
            <div className="rail-list">
              {markers.map((at, i) => {
                const active = current >= at && (markers[i + 1] == null || current < markers[i + 1]);
                return (
                  <button
                    key={i}
                    className={`rail-item${active ? " active" : ""}`}
                    onClick={() => seek(at)}
                  >
                    <span className="rail-item-time">{fmtTs(at)}</span>
                    <span className="rail-item-label">{t("timeline.flagged")}</span>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
