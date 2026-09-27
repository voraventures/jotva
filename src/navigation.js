// One registry for dock navigation, deep-linked settings, and coverage tests.
export const SETTINGS_SECTIONS = ["general", "appearance", "recording", "templates", "ai", "calendars", "integrations", "privacy", "export", "workspace", "license"];
export const DOCK_GROUPS = [
  { id: "meetings", label: "Meetings", items: [
    { label: "Meeting library", nav: "meetings" }, { label: "Digest", nav: "digest" },
  ] },
  { id: "record", label: "Record", items: [
    { label: "Start recording", action: "record" }, { label: "Recording settings", section: "recording" },
  ] },
  { id: "agent", label: "Agent", items: [
    { label: "Waiting on you", nav: "agent" },
  ] },
  { id: "ai", label: "AI", items: [
    { label: "Provider & model", section: "ai" }, { label: "Templates", section: "templates" },
  ] },
  { id: "connections", label: "Connections", items: [
    { label: "Calendars", section: "calendars" }, { label: "Integrations", section: "integrations" }, { label: "Workspace", section: "workspace" },
  ] },
  { id: "settings", label: "Settings", items: [
    { label: "General", section: "general" }, { label: "Appearance", section: "appearance" },
    { label: "Privacy", section: "privacy" }, { label: "Export & backup", section: "export" }, { label: "Subscription", section: "license" },
  ] },
];
export const normalizeSettingsSection = (section) => SETTINGS_SECTIONS.includes(section) ? section : "general";
export const settingsLabel = (section) => DOCK_GROUPS.flatMap(g => g.items).find(i => i.section === section)?.label || "General";
