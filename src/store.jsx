// Global app state: data fetching, websocket events, theme persistence.
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { api, connectWebSocket, initBackend, openExternal } from "./api.js";
import i18n from "./i18n.js";
import { normalizeSettingsSection } from "./navigation.js";
import logoPrimary from "./assets/logo-primary.svg?no-inline";
import logoPrimaryDark from "./assets/logo-primary-dark.svg?no-inline";

export const StoreContext = createContext(null);

// Light is the default material system; dark is its own, not an inversion (HIG 21).
export const THEMES = ["default", "dark"];

// Themes with a dark --bg; the in-app logo uses white waveform bars on these
// (green seed outline stays identical across every theme).
export const DARK_THEMES = new Set(["dark"]);

// Settings key holding each AI provider's bring-your-own-key model.
const MODEL_SETTING_KEYS = { anthropic: "claude_model", openai: "openai_model", google: "gemini_model" };

export function StoreProvider({ children }) {
  const [ready, setReady] = useState(false);
  const [connectionFailed, setConnectionFailed] = useState(false);
  const [health, setHealth] = useState({});
  const [theme, setThemeState] = useState(() => {
    // migrate stored values for removed themes (sky/warm etc.) to default
    const stored = localStorage.getItem("jotva_theme");
    return THEMES.includes(stored) ? stored : "dark";
  });
  const [nav, setNav] = useState("meetings"); // meetings|actions|decisions|topics|people
  const [meetings, setMeetings] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [meetingDetail, setMeetingDetail] = useState(null);
  const [license, setLicense] = useState(null);
  const [avatar, setAvatar] = useState(null); // profile photo data: URL, or null
  const [myWork, setMyWork] = useState(null);
  const [recording, setRecording] = useState({ active: false, meetingId: null });
  const [recordingLevel, setRecordingLevel] = useState(0);
  const [calendarStatus, setCalendarStatus] = useState({});
  const [upcoming, setUpcoming] = useState([]);
  const [prompt, setPrompt] = useState(null); // auto-record prompt payload
  const [upcomingWarning, setUpcomingWarning] = useState(null); // 5-min heads-up toast payload
  const [settings, setSettings] = useState({});
  const [settingsOpen, setSettingsOpenState] = useState(false);
  const [settingsSection, setSettingsSection] = useState("general");
  const openSettings = useCallback((section = "general") => {
    setSettingsSection(normalizeSettingsSection(section));
    setSettingsOpenState(true);
  }, []);
  const setSettingsOpen = useCallback((open) => {
    if (open) openSettings();
    else setSettingsOpenState(false);
  }, [openSettings]);
  const [progress, setProgress] = useState({}); // meeting_id -> {stage, pct}
  const [toasts, setToasts] = useState([]); // [{id, message, kind, action}]
  const toastSeq = useRef(0);
  const [templates, setTemplates] = useState([]);
  const [selectedTemplate, setSelectedTemplate] = useState("builtin-default");
  const [coachData, setCoachData] = useState(null);
  const [coachOpen, setCoachOpen] = useState(true);
  const [brief, setBrief] = useState(null); // pre-meeting intelligence payload
  const [muted, setMuted] = useState(false);
  const [paused, setPaused] = useState(false);
  // Meeting whose growth takeover is on screen (set when a recording stops,
  // cleared when its notes are ready or fail).
  const [processingId, setProcessingId] = useState(null);
  // Meeting that just finished processing — drives the capture flow's "ready"
  // phase (title + summary + chips) until the user views it or replays.
  const [readyMeetingId, setReadyMeetingId] = useState(null);
  // Capture-flow card opened in "idle" phase from the sidebar's Record entry,
  // before the user has actually started the microphone.
  const [captureOpen, setCaptureOpen] = useState(false);
  // Notes as the AI writes them, by meeting id (the meeting page shows them live).
  const [liveNotes, setLiveNotes] = useState({});
  // Pro live notes during a recording: { meetingId, text, at } (latest update).
  const [meetingLiveNotes, setMeetingLiveNotes] = useState(null);
  // Automatic updates: { version } once a new version has downloaded.
  const [updateReady, setUpdateReady] = useState(null);
  // Bumped when the email sync finishes, so the Agent view refetches.
  const [emailVersion, setEmailVersion] = useState(0);
  const [markerCount, setMarkerCount] = useState(0);
  const [liveTranscriptChunks, setLiveTranscriptChunks] = useState([]);
  const [activeCall, setActiveCall] = useState(null); // { app, process, detected_at }
  const [workspace, setWorkspace] = useState(null);
  const selectedIdRef = useRef(null);
  selectedIdRef.current = selectedId;
  const proPollRef = useRef(null);
  const licenseRef = useRef(null);
  licenseRef.current = license;

  const notify = useCallback((title, body) => {
    window.jotva?.notify?.(title, body || "");
  }, []);

  // opts.action: { label, onAction } renders a button inside the toast (e.g. Undo).
  const showToast = useCallback((message, kind = "info", opts = {}) => {
    const id = ++toastSeq.current;
    setToasts((prev) => [...prev.slice(-2), { id, message, kind, action: opts.action }]);
    setTimeout(
      () => setToasts((prev) => prev.filter((t) => t.id !== id)),
      opts.duration || 4000
    );
    return id;
  }, []);

  // A saved bring-your-own-key model vanished from the provider's list and notes
  // switched to the recommended one. Tell the user once, then clear the flag.
  const showModelNotice = useCallback((notice) => {
    if (!notice?.to) return;
    showToast(i18n.t("store.toast.modelSwitched", { from: notice.from, to: notice.to }), "info", { duration: 8000 });
    const key = MODEL_SETTING_KEYS[notice.provider];
    setSettings((s) => ({ ...s, model_notice: null, ...(key ? { [key]: notice.to } : {}) }));
    api.delete("/api/ai/model-notice").catch(() => {});
  }, [showToast]);

  const dismissToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const setTheme = useCallback((name) => {
    setThemeState(name);
    localStorage.setItem("jotva_theme", name);
    document.documentElement.dataset.theme = name;
    api.post("/api/settings", { key: "theme", value: name }).catch(() => {});
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  // Appearance preferences: font size + reduce motion.
  // Font size is applied via a [data-fontsize] attribute (CSS sets --font-size-base);
  // mirrored to localStorage so it applies instantly before server settings load.
  useEffect(() => {
    const size = settings.font_size || localStorage.getItem("jotva_fontsize") || "medium";
    document.documentElement.dataset.fontsize = size;
    if (settings.font_size) localStorage.setItem("jotva_fontsize", settings.font_size);
    document.body.classList.toggle("reduce-motion", !!settings.reduce_motion);
  }, [settings.font_size, settings.reduce_motion]);

  const refreshMeetings = useCallback(
    () => api.get("/api/meetings").then(setMeetings).catch(() => {}),
    []
  );
  const refreshLicense = useCallback(
    () => api.get("/api/license/status").then(setLicense).catch(() => {}),
    []
  );
  const refreshMyWork = useCallback(
    () => api.get("/api/intelligence/my-work").then(setMyWork).catch(() => {}),
    []
  );
  const refreshCalendar = useCallback(() => {
    api.get("/api/calendar/status").then(setCalendarStatus).catch(() => {});
    api.get("/api/calendar/upcoming").then(setUpcoming).catch(() => {});
  }, []);
  const refreshTemplates = useCallback(
    () => api.get("/api/templates").then(setTemplates).catch(() => {}),
    []
  );

  const selectMeeting = useCallback((id) => {
    setSelectedId(id);
    setMeetingDetail(null);
    if (id) {
      api.get(`/api/meetings/${id}`).then(setMeetingDetail).catch(() => {});
    }
  }, []);

  const refreshDetail = useCallback(() => {
    const id = selectedIdRef.current;
    if (id) api.get(`/api/meetings/${id}`).then(setMeetingDetail).catch(() => {});
  }, []);

  // Optimistic delete with a 6s Undo window: the meeting leaves the list
  // immediately, the API call fires only after the toast expires.
  // ponytail: quitting the app inside the window cancels the delete (safe side).
  const pendingDeletes = useRef(new Map()); // id -> timeout
  const deleteMeeting = useCallback(
    (id) => {
      setMeetings((prev) => prev.filter((m) => m.id !== id));
      if (selectedIdRef.current === id) selectMeeting(null);
      const timer = setTimeout(() => {
        pendingDeletes.current.delete(id);
        api
          .delete(`/api/meetings/${id}`)
          .then(() => refreshMyWork())
          .catch((err) => {
            showToast(err.message, "error");
            refreshMeetings();
          });
      }, 6000);
      pendingDeletes.current.set(id, timer);
      showToast(i18n.t("common.meetingDeleted"), "info", {
        duration: 6000,
        action: {
          label: i18n.t("common.undo"),
          onAction: () => {
            clearTimeout(timer);
            pendingDeletes.current.delete(id);
            refreshMeetings();
          },
        },
      });
    },
    [refreshMeetings, refreshMyWork, selectMeeting, showToast]
  );

  // ---------- boot ----------
  useEffect(() => {
    let cleanup = () => {};
    (async () => {
      // If the backend process never emits its ready handshake (spawn error,
      // port bind failure), getBackend would pend forever — time out instead.
      const info = await Promise.race([
        initBackend(),
        new Promise((r) => setTimeout(() => r(null), 30000)),
      ]);
      if (!info) {
        setConnectionFailed(true);
        return;
      }
      // wait for backend to accept requests
      let healthy = false;
      for (let i = 0; i < 60; i++) {
        try {
          const h = await api.get("/api/health");
          setHealth(h);
          healthy = true;
          break;
        } catch {
          await new Promise((r) => setTimeout(r, 500));
        }
      }
      if (!healthy) {
        setConnectionFailed(true);
        return;
      }
      await Promise.all([
        refreshMeetings(),
        refreshLicense(),
        refreshMyWork(),
        refreshCalendar(),
        api.get("/api/settings").then((s) => {
          setSettings(s);
          if (s.default_template) setSelectedTemplate(s.default_template);
          if (s.model_notice) showModelNotice(s.model_notice);
        }).catch(() => {}),
        refreshTemplates(),
        api.get("/api/settings/avatar").then((r) => setAvatar(r.avatar || null)).catch(() => {}),
        api
          .get("/api/recording/status")
          .then((s) => setRecording({ active: s.recording, meetingId: s.meeting_id }))
          .catch(() => {}),
      ]);
      setReady(true);

      cleanup = connectWebSocket((event, data) => {
        switch (event) {
          case "recording_started":
            setRecording({ active: true, meetingId: data.meeting_id });
            setCaptureOpen(false);
            setCoachData(null);
            setMuted(false);
            setPaused(false);
            setMarkerCount(0);
            setLiveTranscriptChunks([]);
            refreshMeetings();
            notify(
              i18n.t("store.notify.recordingStartedTitle"),
              i18n.t("store.notify.recordingStartedBody")
            );
            break;
          case "transcript_chunk":
            if (data.text) {
              // Bound the buffer: a multi-hour meeting would otherwise grow an
              // ever-longer array and re-render the full list on every chunk.
              setLiveTranscriptChunks((prev) => [...prev.slice(-149), data.text]);
            }
            break;
          case "coach_update":
            setCoachData(data);
            break;
          case "recording_muted":
            setMuted(!!data.muted);
            break;
          case "recording_paused":
            setPaused(!!data.paused);
            break;
          case "marker_added":
            setMarkerCount(data.count || 0);
            break;
          case "meeting_brief":
            setBrief(data);
            notify(
              i18n.t("store.notify.briefReadyTitle"),
              i18n.t("store.notify.briefReadyBody", {
                title: data.title,
                minutes: data.minutes_until,
              })
            );
            break;
          case "daily_pulse":
            notify(
              i18n.t("store.notify.pulseTitle"),
              i18n.t("store.notify.pulseBody", { count: data.stale_count })
            );
            break;
          case "model_notice":
            showModelNotice(data);
            break;
          case "conflicts_found":
            notify(
              i18n.t("store.notify.conflictTitle"),
              i18n.t("store.notify.conflictBody")
            );
            if (selectedIdRef.current === data.meeting_id) refreshDetail();
            break;
          case "transcription_done":
            notify(
              i18n.t("store.notify.transcriptionDoneTitle"),
              i18n.t("store.notify.transcriptionDoneBody")
            );
            break;
          case "recording_stopped":
            // Straight to the meeting page, where the notes write themselves in.
            setRecording((prev) => {
              if (prev.meetingId) {
                setCaptureOpen(false);
                setNav("meetings");
                selectMeeting(prev.meetingId);
              }
              return { active: false, meetingId: null };
            });
            setRecordingLevel(0);
            setPaused(false);
            setLiveTranscriptChunks([]);
            break;
          case "email_updated":
            setEmailVersion((v) => v + 1);
            break;
          case "email_urgent":
            notify(
              i18n.t("agent.notifyTitle", { count: data.count }),
              data.first?.counterpart_name ? `${data.first.counterpart_name}: ${data.first.subject || ""}` : ""
            );
            setEmailVersion((v) => v + 1);
            break;
          case "live_notes":
            setMeetingLiveNotes({ meetingId: data.meeting_id, text: data.text, at: data.at * 1000 });
            break;
          case "notes_delta":
            setLiveNotes((prev) => ({ ...prev, [data.meeting_id]: data.text }));
            break;
          case "recording_level":
            setRecordingLevel(data.rms || 0);
            break;
          case "meeting_status":
            setProgress((p) => ({
              ...p,
              [data.meeting_id]: { stage: data.status, pct: null },
            }));
            refreshMeetings();
            if (data.status === "ready" || data.status === "error") {
              setProcessingId((cur) => {
                if (cur !== data.meeting_id) return cur;
                if (data.status === "ready") setReadyMeetingId(data.meeting_id);
                return null;
              });
              refreshMyWork();
              refreshLicense();
              if (selectedIdRef.current === data.meeting_id) refreshDetail();
              // Keep the live text until the saved notes have loaded, then drop it.
              setTimeout(() => setLiveNotes(({ [data.meeting_id]: _done, ...rest }) => rest), 4000);
              if (data.status === "error") showToast(data.error || i18n.t("store.toast.processingFailed"), "error");
              if (data.status === "ready")
                notify(
                  i18n.t("store.notify.notesReadyTitle"),
                  i18n.t("store.notify.notesReadyBody")
                );
            }
            break;
          case "speaker_analysis":
            setProgress(p => ({...p, [data.meeting_id]: {stage: data.status === 'processing' ? 'speaker_analysis' : 'generating', pct: null}}));
            break;
          case "transcription_progress":
            setProgress((p) => ({
              ...p,
              [data.meeting_id]: { stage: "transcribing", pct: data.progress },
            }));
            break;
          case "meeting_prompt":
          case "auto_record_starting":
            setPrompt({ ...data, auto: event === "auto_record_starting" });
            notify(
              i18n.t("store.notify.meetingDetectedTitle"),
              i18n.t("store.notify.meetingDetectedBody", {
                title: data.title || i18n.t("store.notify.fallbackMeeting"),
              })
            );
            break;
          case "auto_record_upcoming":
            setUpcomingWarning(data);
            break;
          case "calendar_synced":
            api.get("/api/calendar/upcoming").then(setUpcoming).catch(() => {});
            break;
          case "google_connected":
          case "ms_connected":
            refreshCalendar();
            showToast(i18n.t("store.toast.calendarConnected"));
            break;
          case "ms_connect_failed":
            showToast(i18n.t("store.toast.msFailed"), "error");
            break;
          default:
            break;
        }
      });
    })();
    return () => cleanup();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const selectedTemplateRef = useRef(selectedTemplate);
  selectedTemplateRef.current = selectedTemplate;
  const startInFlightRef = useRef(false);

  const startRecording = useCallback(
    async (opts = {}) => {
      // Device init can block /start for tens of seconds (e.g. first-run mic
      // permission); guard so a second hotkey press or the auto-record prompt
      // can't fire a concurrent duplicate start.
      if (startInFlightRef.current) return;
      startInFlightRef.current = true;
      try {
        const result = await api.post("/api/recording/start", {
          title: opts.title || "",
          calendar_event_id: opts.calendarEventId || null,
          template_id: opts.templateId || selectedTemplateRef.current || null,
        });
        setRecording({ active: true, meetingId: result.meeting_id });
        await refreshMeetings();
        selectMeeting(result.meeting_id);
        return result;
      } catch (err) {
        const raw = err.message || i18n.t("store.toast.recordingFailed");
        // Every start failure is about the audio input, so offer the way to fix it.
        const toMic = {
          duration: 9000,
          action: { label: i18n.t("store.toast.micSettings"), onAction: () => openSettings("recording") },
        };
        if (/portaudio|input.?stream|undefined error.*-50|audio.*unavailable|unavailable.*audio/i.test(raw)) {
          showToast(i18n.t("store.toast.micDenied"), "error", toMic);
        } else {
          showToast(raw, "error", toMic);
        }
        throw err;
      } finally {
        startInFlightRef.current = false;
      }
    },
    [refreshMeetings, selectMeeting, showToast, openSettings]
  );

  const joinMeeting = useCallback(
    async (eventId) => {
      try {
        const result = await api.post(`/api/calendar/events/${encodeURIComponent(eventId)}/join`);
        if (result.join_url) await openExternal(result.join_url);
        setUpcomingWarning(null);
        if (result.watching) showToast(i18n.t("store.toast.joinWatching"), "info");
      } catch (err) {
        showToast(err.message || i18n.t("store.toast.joinFailed"), "error");
      }
    },
    [showToast]
  );

  const stopRecording = useCallback(async () => {
    try {
      await api.post("/api/recording/stop");
      setRecording({ active: false, meetingId: null });
      setRecordingLevel(0);
      await refreshMeetings();
    } catch (err) {
      showToast(err.message, "error");
    }
  }, [refreshMeetings, showToast]);

  // Global shortcuts forwarded from the main process
  const recordingRef = useRef(recording);
  recordingRef.current = recording;
  useEffect(() => {
    const off = window.jotva?.onShortcut?.((name) => {
      if (name === "toggle-record") {
        if (recordingRef.current.active) stopRecording();
        else startRecording().catch(() => {});
      } else if (name === "ambient-start") {
        if (!recordingRef.current.active) startRecording().catch(() => {});
      } else if (name === "drop-marker") {
        if (recordingRef.current.active) {
          api.post("/api/recording/marker").catch(() => {});
        }
      }
    });
    return typeof off === "function" ? off : undefined;
  }, [startRecording, stopRecording]);

  // Keep the tray pulse in sync with recording state
  useEffect(() => {
    window.jotva?.setRecordingState?.(recording.active);
  }, [recording.active]);

  // Feature 3: poll for active video-call apps every 30 seconds
  const activeCallDismissed = useRef(new Set());
  useEffect(() => {
    if (!ready) return;
    const poll = async () => {
      try {
        const r = await api.get("/api/system/active-calls");
        const calls = r.active_calls || [];
        const newCall = calls.find((c) => !activeCallDismissed.current.has(c.app));
        setActiveCall(newCall || null);
      } catch {
        // ignore — backend may not support yet
      }
    };
    poll();
    const id = setInterval(poll, 30000);
    return () => clearInterval(id);
  }, [ready]);

  const dismissActiveCall = useCallback((appName) => {
    activeCallDismissed.current.add(appName);
    setActiveCall(null);
  }, []);

  // After the user opens the Stripe checkout URL, poll the license server (via
  // the local backend's /api/license/refresh) every 10s for up to 10 minutes,
  // stopping as soon as the license upgrades to Pro.
  const startProUpgradePolling = useCallback(() => {
    if (proPollRef.current) clearInterval(proPollRef.current);
    const deadline = Date.now() + 10 * 60 * 1000;
    const stop = () => {
      if (proPollRef.current) {
        clearInterval(proPollRef.current);
        proPollRef.current = null;
      }
    };
    proPollRef.current = setInterval(async () => {
      if (Date.now() > deadline) {
        stop();
        return;
      }
      try {
        const status = await api.post("/api/license/refresh");
        if (status?.tier === "pro") {
          stop();
          refreshLicense();
        }
      } catch {
        // ignore transient errors; keep polling until the deadline
      }
    }, 10000);
  }, [refreshLicense]);

  useEffect(
    () => () => {
      if (proPollRef.current) clearInterval(proPollRef.current);
    },
    []
  );

  const installUpdate = useCallback(async () => {
    const result = await window.jotva?.installUpdate?.();
    if (result?.reason === "recording") showToast(i18n.t("update.afterRecording"));
  }, [showToast]);
  useEffect(() => {
    const announce = (info) => {
      if (!info?.version) return;
      setUpdateReady(info);
      showToast(i18n.t("update.ready", { version: info.version }), "info", {
        duration: 20000,
        action: { label: i18n.t("update.restart"), onAction: installUpdate },
      });
    };
    window.jotva?.updateStatus?.().then(announce).catch(() => {});
    return window.jotva?.onUpdateReady?.(announce);
  }, [installUpdate, showToast]);

  // Freemium: Pro features check license.features before calling the backend and
  // open the upgrade prompt instead. A 402 from the backend is the backstop.
  const [upgradeFeature, setUpgradeFeature] = useState(null);
  const openUpgrade = useCallback((feature = "unlimited_notes") => setUpgradeFeature(feature), []);
  const closeUpgrade = useCallback(() => setUpgradeFeature(null), []);
  const hasFeature = useCallback(
    (feature) => (license?.features ? license.features[feature] !== false : true),
    [license]
  );
  const proGuard = useCallback(
    (feature, fn) => (...args) => (hasFeature(feature) ? fn(...args) : openUpgrade(feature)),
    [hasFeature, openUpgrade]
  );
  const handleError = useCallback(
    (e) => (e?.status === 402 ? openUpgrade(e.feature) : showToast(e?.message || String(e), "error")),
    [openUpgrade, showToast]
  );
  const startCheckout = useCallback(async () => {
    const { url } = await api.post("/api/license/checkout");
    openExternal(url);
    startProUpgradePolling();
  }, [startProUpgradePolling]);

  // Passive background license poll: every 5 minutes, re-validate against the
  // license server so a Pro upgrade is reflected even without any user action.
  useEffect(() => {
    if (!ready) return;
    const id = setInterval(async () => {
      try {
        const status = await api.post("/api/license/refresh");
        if (status?.tier === "pro" && licenseRef.current?.tier !== "pro") {
          refreshLicense();
        }
      } catch {
        // swallow — background poll must never surface errors
      }
    }, 5 * 60 * 1000);
    return () => clearInterval(id);
  }, [ready, refreshLicense]);

  // Safety net: re-fetch upcoming meetings every 2 minutes in case a
  // calendar_synced WebSocket push was missed (e.g. a dropped socket).
  useEffect(() => {
    if (!ready) return;
    const id = setInterval(() => {
      api.get("/api/calendar/upcoming").then(setUpcoming).catch(() => {});
    }, 2 * 60 * 1000);
    return () => clearInterval(id);
  }, [ready]);

  // Feature 4: load workspace on boot
  const refreshWorkspace = useCallback(
    () => api.get("/api/workspace").then((r) => setWorkspace(r)).catch(() => {}),
    []
  );

  useEffect(() => {
    if (ready) refreshWorkspace();
  }, [ready, refreshWorkspace]);

  const toggleMute = useCallback(async () => {
    try {
      const r = await api.post("/api/recording/mute", { muted: !muted });
      setMuted(r.muted);
    } catch (err) {
      showToast(err.message, "error");
    }
  }, [muted, showToast]);

  const togglePause = useCallback(async () => {
    try {
      const r = await api.post("/api/recording/pause", { paused: !paused });
      setPaused(r.paused);
    } catch (err) {
      showToast(err.message, "error");
    }
  }, [paused, showToast]);

  const dropMarker = useCallback(async () => {
    try {
      await api.post("/api/recording/marker");
      showToast(i18n.t("store.toast.momentFlagged"));
    } catch (err) {
      showToast(err.message, "error");
    }
  }, [showToast]);

  const value = {
    ready,
    connectionFailed,
    health,
    theme,
    setTheme,
    avatar,
    setAvatar,
    nav,
    setNav,
    meetings,
    refreshMeetings,
    selectedId,
    selectMeeting,
    meetingDetail,
    refreshDetail,
    deleteMeeting,
    license,
    refreshLicense,
    startProUpgradePolling,
    upgradeFeature,
    openUpgrade,
    closeUpgrade,
    hasFeature,
    proGuard,
    handleError,
    startCheckout,
    myWork,
    refreshMyWork,
    recording,
    recordingLevel,
    startRecording,
    stopRecording,
    calendarStatus,
    refreshCalendar,
    upcoming,
    prompt,
    setPrompt,
    upcomingWarning,
    setUpcomingWarning,
    joinMeeting,
    settings,
    setSettings,
    settingsOpen,
    setSettingsOpen,
    settingsSection,
    openSettings,
    progress,
    toasts,
    showToast,
    dismissToast,
    templates,
    refreshTemplates,
    selectedTemplate,
    setSelectedTemplate,
    coachData,
    coachOpen,
    setCoachOpen,
    brief,
    setBrief,
    muted,
    toggleMute,
    paused,
    togglePause,
    processingId,
    setProcessingId,
    readyMeetingId,
    setReadyMeetingId,
    captureOpen,
    setCaptureOpen,
    liveNotes,
    meetingLiveNotes,
    updateReady,
    installUpdate,
    emailVersion,
    markerCount,
    dropMarker,
    liveTranscriptChunks,
    activeCall,
    dismissActiveCall,
    workspace,
    refreshWorkspace,
  };

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>;
}

export function useStore() {
  return useContext(StoreContext);
}

// Theme-aware in-app logo: green seed outline is identical everywhere; only the
// waveform bars switch (dark on light themes, white on dark themes).
export function useLogo() {
  const { theme } = useStore();
  return DARK_THEMES.has(theme) ? logoPrimaryDark : logoPrimary;
}
