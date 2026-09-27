// Development-only, isolated presentation fixtures. Never initializes the backend.
import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import { StoreContext } from "../../src/store.jsx";
import { api } from "../../src/api.js";
import { normalizeSettingsSection } from "../../src/navigation.js";
import App from "../../src/App.jsx";
import "../../src/i18n.js";
import "../../src/fonts.css";
import "../../src/styles.css";
import "../../src/screen-type.css";
import "../../src/green-glass.css";
import "../../src/jotva-theme.css";

if (!import.meta.env.DEV) throw new Error("Design fixtures are development-only");
// Each gallery frame gets its own in-memory preferences; no cross-frame races
// and no writes to the browser's real localStorage.
const memory = new Map();
const storage = { getItem: key => memory.get(key) ?? null, setItem: (key, value) => memory.set(key, String(value)), removeItem: key => memory.delete(key), clear: () => memory.clear() };
Object.defineProperty(window, "localStorage", { configurable: true, value: storage });
if (globalThis !== window) Object.defineProperty(globalThis, "localStorage", { configurable: true, value: storage });
const params = new URLSearchParams(location.search);
const state = params.get("state") || "meeting";
if (params.has("panel")) localStorage.setItem("jotva_list_width", params.get("panel"));
localStorage.setItem("jotva_onboarded", state === "onboarding" ? "false" : "true");
localStorage.setItem("jotva_tour_done", "true");
localStorage.setItem("jotva_language", "en");
const noop = async () => ({});
// Fail closed even for legacy code that bypasses api.js: preview never contacts a service.
window.fetch = async () => { throw new Error("Network disabled in synthetic preview"); };
window.open = () => null;
window.jotva = { platform: "darwin", getAutoLaunch: async () => ({ enabled: false }), setAutoLaunch: noop, openExternal: noop, speakerSetup: async () => ({zoom: 'experimental', meet: 'host_registered', qualified: false}) };
const date = new Date(); date.setHours(9, 0, 0, 0);
const meeting = {
  id: "synthetic-design-meeting", title: "Making room for what matters", status: "ready", is_demo: 1, audio_path: "synthetic-not-playable.wav",
  started_at: date.toISOString(), ended_at: new Date(+date + 32 * 60000).toISOString(),
  attendees: ["Maya Chen", "Alex Rivera", "You"],
  notes: { sections: {
    "Executive Summary": "We aligned on a simpler first-run experience and a focused September release. The team will prioritize *capture confidence*, make ownership clearer, and bring the new workspace to a small pilot group before launch.",
    "Key Discussions": "### A calmer workspace\nKeep meeting content in focus. Navigation should feel effortless, with the tools you need one click away.\n\n### A confident first recording\nMake selected audio inputs visible and explain how to check both sides of a conversation.",
    "Next Steps": "1. Share the revised onboarding flow with the team.\n2. Schedule five pilot sessions.\n3. Review feedback together next Tuesday.",
    ...(["banners", "cards"].includes(state) ? { "Compliance Flags": "Synthetic compliance notice — this existing risk treatment should remain unchanged." } : {}),
  } },
  intelligence: {
    actions: [
      { id: "a", action: "Refine the first-run recording experience", owner: "Maya Chen", due: "2026-09-15", status: "open" },
      { id: "b", action: "Invite five customers to the workspace pilot", owner: "Alex Rivera", due: "2026-09-18", status: "open" },
      { id: "c", action: "Publish the updated release checklist", owner: "TBD", due: "2026-09-21", status: "open" },
    ], decisions: [{ id: "d1", text: "Ship the focused desktop experience first" }, { id: "d2", text: "Validate the capture setup before expanding the pilot" }],
    topics: ["Product experience", "September release", "Customer feedback"], participants: ["Maya Chen", "Alex Rivera", "You"], heads_up: ["One action needs an owner before the next check-in."],
  },
  transcript: { duration_sec: 1920, _segments: Array.from({ length: 24 }, (_, i) => ({ start: i * 40, end: i * 40 + 32, speaker: `Speaker ${i % 2 + 1}`, text: ["Let's keep the next release focused. I want people to feel confident that their meeting has been captured, without interrupting the conversation.", "Agreed. The pilot feedback should help us decide which changes matter most. I'll organize those sessions and share a short summary with the team."][i % 2] })) },
  markers: [80],
  jot_notes: "capture confidence!!\nwho owns the pilot?",
};
const meetings = [meeting, { ...meeting, id: "synthetic-long", title: "Customer discovery — a deliberately long meeting title to verify wrapping, alignment, and reading comfort", started_at: new Date(+date - 86400000).toISOString(), ended_at: new Date(+date - 86400000 + 32 * 60000).toISOString() }, { ...meeting, id: "synthetic-3", title: "Design team / weekly check-in", started_at: new Date(+date - 2 * 86400000).toISOString(), ended_at: new Date(+date - 2 * 86400000 + 32 * 60000).toISOString() }];
const cardFixtures = [
  ...meetings,
  ...["recording", "transcribing", "generating", "error"].map((status, i) => ({ ...meeting, id: `status-${status}`, title: ["Live product conversation", "Preparing the transcript", "Writing meeting notes", "A recording that needs attention"][i], is_demo: 0, status, ended_at: null })),
  { ...meeting, id: "missing-date", title: "Imported meeting without a date", is_demo: 0, started_at: null, ended_at: "invalid" },
  { ...meeting, id: "invalid-date", title: "Meeting with unavailable timing", is_demo: 0, started_at: "invalid", ended_at: "invalid" },
];
const visibleMeetings = state === "empty" ? [] : state === "no-today" ? meetings.slice(1) : state === "cards" ? cardFixtures : meetings;
const futureEvent = { id: "future-1", title: "A little space for the next big idea", start: new Date(Date.now() + 90 * 60000).toISOString() };
const upcomingFixtures = state === "cards" ? [
  { ...futureEvent, id: "future-2", title: "Team planning", start: new Date(Date.now() + 150 * 60000).toISOString() },
  { ...futureEvent, id: "cancelled", title: "Must not appear: cancelled", cancelled: true },
  { ...futureEvent, id: "recorded", title: "Must not appear: already recorded", recorded_meeting_id: meeting.id },
  { ...futureEvent, id: "past", title: "Must not appear: past", start: new Date(Date.now() - 60000).toISOString() },
  { ...futureEvent, id: "invalid", title: "Must not appear: invalid", start: "invalid" }, futureEvent,
] : ["empty", "no-today"].includes(state) ? [] : [futureEvent];
const templates = ["Default", "Sales Call (MEDDIC)", "1-on-1", "Product Discovery", "Board Meeting", "Interview", "Sprint Planning", "Customer Success"].map((name, i) => ({ id: i ? `builtin-${i}` : "builtin-default", name, builtin: true, description: "A focused structure for useful meeting notes.", sections: ["Executive Summary", "Key Discussions", "Decisions Made", "Action Items", "Next Steps"] }));
if (state.startsWith('speakers')) {
  meeting.transcript.speaker_analysis = {status: state === 'speakers-failed' ? 'failed' : 'ready', version: 'synthetic', named_speakers: state === 'speakers-failed' ? 0 : 2};
  for (const seg of meeting.transcript._segments) {
    if (state === 'speakers-failed') continue;
    seg.speaker_id = seg.speaker === 'Speaker 1' ? 'speaker_1' : 'speaker_2';
    seg.speaker = seg.speaker_id === 'speaker_1' ? 'Maya Chen' : 'Alex Rivera';
    seg.speaker_name = seg.speaker; seg.speaker_source = 'meet';
  }
}
api.get = async path => {
  if (path.includes('/speakers/status')) return {models: {state: 'ready', runtime_available: true, progress: 1}, platforms_qualified: false};
  if (path.includes("user-name")) return { user_name: "Alex Rivera" };
  if (path.includes("integrations/status")) return { secrets: {} };
  if (path.includes("email/accounts")) return { accounts: [{ id: "a1", provider: "gmail", address: "luis@vora.co", last_sync: "2026-09-27T10:00:00Z", last_error: null }] };
  if (path.includes("email/waiting")) return { threads: [
    { id: "a1:t1", account: "luis@vora.co", provider: "gmail", counterpart_name: "Sarah Lee", counterpart_email: "sarah@acme.com", subject: "Q4 budget — need your sign-off", reason: "Asks you to approve the Q4 budget by Tuesday", urgency: "high", last_at: new Date(Date.now() - 26 * 36e5).toISOString(), last_message_id: "q1@acme", tasks: [] },
    { id: "a1:t2", account: "luis@vora.co", provider: "gmail", counterpart_name: "Marcus Diaz", counterpart_email: "marcus@vora.co", subject: "Vendor shortlist", reason: "Wants your pick of the three vendors", urgency: "normal", last_at: new Date(Date.now() - 5 * 36e5).toISOString(), last_message_id: "v1@vora", tasks: [] },
    { id: "a1:t3", account: "luis@vora.co", provider: "gmail", counterpart_name: "Emily Chen", counterpart_email: "emily@partner.io", subject: "Intro: Dana from Northwind", reason: "Introduction waiting for your reply", urgency: "low", last_at: new Date(Date.now() - 3 * 864e5).toISOString(), last_message_id: "i1@partner", tasks: [] },
  ] };
  if (path.includes("recording/devices")) return { devices: [{ index: 0, name: "MacBook Pro Microphone" }], default_input: { name: "MacBook Pro Microphone", is_loopback_like: false } };
  if (path.includes("mobile/sessions")) return [];
  if (path.includes("intelligence/digest")) return state === "empty" ? {} : { meetings, meeting_count: 3, total_minutes: 96, range_start: date.toISOString(), range_end: date.toISOString(), recurring_topics: [{ name: "Product experience", count: 3 }], open_actions: meeting.intelligence.actions, decisions: meeting.intelligence.decisions };
  if (path.includes("search")) return visibleMeetings.filter(m => m.title.toLowerCase().includes(new URL(path, "http://fixture").searchParams.get("q").toLowerCase()));
  return {};
};
api.post = api.patch = api.delete = async () => { throw new Error("Writes disabled in synthetic preview"); };

function Preview() {
  const [theme, setTheme] = useState(params.get("theme") || "default");
  const [settings, setSettings] = useState({ font_size: params.get("size") || "medium", reduce_motion: params.get("motion") !== "on", ai_provider: "anthropic", claude_model: "claude-haiku-4-5", whisper_model: "base", auto_record_mode: "ask", retention_days: 0 });
  const [nav, setNav] = useState(state === "agent" ? "agent" : "meetings");
  const [selectedId, selectMeeting] = useState(visibleMeetings[0]?.id || null);
  const [deletedIds, setDeletedIds] = useState([]);
  const [settingsOpen, setOpen] = useState(!!params.get("section"));
  const [upgradeFeature, setUpgradeFeature] = useState(params.get("upgrade"));
  const [settingsSection, setSection] = useState(normalizeSettingsSection(params.get("section")));
  const [captureOpen, setCaptureOpen] = useState(state === "capture-idle");
  const [recording, setRecording] = useState({ active: state === "recording", meetingId: meeting.id });
  const [processingId, setProcessingId] = useState(state === "processing" ? meeting.id : null);
  const [readyMeetingId, setReadyMeetingId] = useState(state === "ready" ? meeting.id : null);
  const [paused, setPaused] = useState(false);
  const [toasts, setToasts] = useState([]);
  const openSettings = section => { setSection(normalizeSettingsSection(section)); setOpen(true); };
  document.documentElement.dataset.theme = theme;
  document.documentElement.dataset.fontsize = settings.font_size;
  document.body.classList.toggle("reduce-motion", settings.reduce_motion);
  const value = {
    ready: state !== "boot-loading", connectionFailed: state === "boot-error", theme, setTheme, nav, setNav, settings, setSettings, settingsOpen, settingsSection, openSettings,
    setSettingsOpen: open => open ? openSettings("general") : setOpen(false),
    meetings: visibleMeetings.filter(m => !deletedIds.includes(m.id)).map(m => m.id === meeting.id && ["recording", "error"].includes(state) ? { ...m, status: state, started_at: new Date(Date.now() - 120000).toISOString(), ended_at: null } : m), selectedId, selectMeeting,
    meetingDetail: state === "loading" ? null : { ...(visibleMeetings.find(m => m.id === selectedId) || meeting), status: state === "error" ? "error" : "ready" },
    progress: state === "processing" ? { [meeting.id]: { stage: "transcribing", pct: .45 } }
      : state === "live-notes" ? { [meeting.id]: { stage: "generating", pct: null } } : {},
    meetingLiveNotes: state === "recording" && params.get("live") ? { meetingId: meeting.id, text: "## Key points\n- Sarah finalizes the client deck by Wed 3 p.m.\n- Vendor pricing blocks the cost comparison\n## Action items\n- **Marcus** — subscription review (Thu morning)", at: Date.now() } : null,
    liveNotes: state === "live-notes" ? { [meeting.id]: "## Executive Summary\nLuis assigned weekly responsibilities across five team members with clear deadlines. A critical dependency exists: Emily's vendor pricing must land before Sarah can finalize the\n" } : {},
    recording, recordingLevel: .3, captureOpen, setCaptureOpen, processingId, setProcessingId, readyMeetingId, setReadyMeetingId, paused, muted: false,
    startRecording: async () => { setCaptureOpen(false); setRecording({ active: true, meetingId: meeting.id }); },
    stopRecording: async () => { setRecording({ active: false }); setProcessingId(meeting.id); }, togglePause: () => setPaused(v => !v),
    license: {
      tier: "free", meetings_used: 2, can_record: true, ai_notes_limit: 10, ai_notes_used: 3,
      ai_notes_remaining: 7, ai_notes_resets_on: "2026-10-01",
      features: { unlimited_notes: false, higher_quality: false, ask_all: false, auto_record: false,
                  mcp: false, followup: false, templates: false, integrations: false },
    },
    upcoming: upcomingFixtures, activeCall: null, prompt: null, upcomingWarning: null, brief: null, coachOpen: false, coachData: null,
    calendarStatus: {}, workspace: null, templates, selectedTemplate: "builtin-default", health: {},
    toasts, showToast: message => setToasts([{ id: 1, message, kind: "error" }]), dismissToast: () => setToasts([]),
    refreshCalendar: noop, refreshLicense: noop, refreshMeetings: noop, refreshDetail: noop, refreshMyWork: noop, refreshWorkspace: noop, refreshTemplates: noop,
    deleteMeeting: id => {
      setDeletedIds(ids => [...ids, id]);
      if (id === selectedId) selectMeeting(null);
      setToasts([{ id: "fixture-delete", kind: "info", message: "Meeting deleted", action: { label: "Undo", onAction: () => setDeletedIds(ids => ids.filter(deleted => deleted !== id)) } }]);
    }, setSelectedTemplate: noop, dismissActiveCall: noop, setCoachOpen: noop, startProUpgradePolling: noop,
    emailVersion: 0, updateReady: null, installUpdate: noop,
    upgradeFeature, openUpgrade: (f = "unlimited_notes") => setUpgradeFeature(f), closeUpgrade: () => setUpgradeFeature(null), hasFeature: () => params.get("pro") === "1",
    proGuard: (_f, fn) => fn, handleError: noop, startCheckout: noop,
  };
  return <StoreContext.Provider value={value}><App /></StoreContext.Provider>;
}
export { act } from "react";
export const previewRoot = createRoot(document.getElementById("root"));
previewRoot.render(<Preview />);
