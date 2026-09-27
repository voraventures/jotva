import React, { useEffect, useRef, useState } from "react";
import SettingsPanel from "./SettingsPanel.jsx";
import SpeakerSettings from "./SpeakerSettings.jsx";
import { settingsLabel } from "../navigation.js";
import { useTranslation } from "react-i18next";
import i18n, { setLanguage } from "../i18n.js";
import { api, openExternal } from "../api.js";
import { THEMES, useStore } from "../store.jsx";
import { SparkIcon, UsersIcon, XIcon } from "./icons.jsx";
import { Select } from "./ui.jsx";
import { AppleCalendarLogo, BRAND_LOGOS, GoogleCalendarLogo, OutlookCalendarLogo } from "./brandLogos.jsx";
import { imageFileToAvatar, initialsOf } from "../avatar.js";

// Template glyphs (14px, stroke-based) — scoped to Settings only.
const TI = ({ size = 14, children }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    {children}
  </svg>
);
const DocIcon = (p) => (
  <TI {...p}>
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <path d="M14 2v6h6" />
    <line x1="8" y1="13" x2="16" y2="13" />
    <line x1="8" y1="17" x2="13" y2="17" />
  </TI>
);
const ChartIcon = (p) => (
  <TI {...p}>
    <line x1="6" y1="20" x2="6" y2="12" />
    <line x1="12" y1="20" x2="12" y2="4" />
    <line x1="18" y1="20" x2="18" y2="9" />
  </TI>
);
const BulbIcon = (p) => (
  <TI {...p}>
    <path d="M9 18h6" />
    <path d="M10 22h4" />
    <path d="M15.1 14c.2-1 .7-1.7 1.4-2.5A4.65 4.65 0 0 0 18 8 6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.8 1.2 1.5 1.4 2.5" />
  </TI>
);
const BuildingIcon = (p) => (
  <TI {...p}>
    <rect x="4" y="2" width="16" height="20" rx="2" />
    <path d="M9 22v-4h6v4" />
    <path d="M9 6h.01M15 6h.01M9 10h.01M15 10h.01M9 14h.01M15 14h.01" />
  </TI>
);
const UserCheckIcon = (p) => (
  <TI {...p}>
    <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
    <circle cx="9" cy="7" r="4" />
    <polyline points="16 11 18 13 22 9" />
  </TI>
);
const SprintIcon = (p) => (
  <TI {...p}>
    <polygon points="5 3 19 12 5 21 5 3" />
  </TI>
);
const HeartIcon = (p) => (
  <TI {...p}>
    <path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.6l-1-1a5.5 5.5 0 0 0-7.8 7.8l1 1L12 21l7.8-7.6 1-1a5.5 5.5 0 0 0 0-7.8z" />
  </TI>
);
const StarIcon = (p) => (
  <TI {...p}>
    <polygon points="12 2 15.1 8.6 22 9.3 17 14 18.2 21 12 17.6 5.8 21 7 14 2 9.3 8.9 8.6 12 2" />
  </TI>
);

// Builtin template id -> glyph. Custom templates fall back to the star.
const TEMPLATE_ICONS = {
  "builtin-default": DocIcon,
  "builtin-sales": ChartIcon,
  "builtin-oneonone": UsersIcon,
  "builtin-discovery": BulbIcon,
  "builtin-board": BuildingIcon,
  "builtin-interview": UserCheckIcon,
  "builtin-sprint": SprintIcon,
  "builtin-cs": HeartIcon,
};
const templateIcon = (t) => TEMPLATE_ICONS[t.id] || StarIcon;

// The shared tail sections every template is composed with (mirrors the
// backend's SHARED_TAIL) so chips reflect what's actually generated.
// Keychain secret holding each AI provider's own API key.
const AI_KEY_NAMES = { anthropic: "anthropic_api_key", openai: "openai_api_key", google: "google_api_key" };

const TAIL_SECTIONS = ["Decisions Made", "Action Items", "Next Steps"];

// Derive the section chips from a template's markdown body (## headers),
// splicing in the shared tail wherever the {SHARED_TAIL} placeholder sits.
function templateSections(body) {
  if (!body) return [];
  const out = [];
  const parts = body.split("{SHARED_TAIL}");
  parts.forEach((part, i) => {
    for (const m of part.matchAll(/^##\s+(.+)$/gm)) out.push(m[1].trim());
    if (i < parts.length - 1) out.push(...TAIL_SECTIONS);
  });
  return out;
}

// Per-setting glyphs for the card layout (FIX 2) — scoped to Settings only.
const PaletteIcon = (p) => (
  <TI {...p}>
    <circle cx="13.5" cy="6.5" r="1.2" />
    <circle cx="17" cy="11" r="1.2" />
    <circle cx="8.5" cy="7" r="1.2" />
    <circle cx="6.5" cy="12.5" r="1.2" />
    <path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.9 0 1.5-.7 1.5-1.5 0-.4-.2-.7-.4-1-.2-.2-.4-.6-.4-1 0-.8.7-1.5 1.5-1.5H16c3.3 0 6-2.7 6-6 0-4.4-4.5-8-10-8z" />
  </TI>
);
const TextSizeIcon = (p) => (
  <TI {...p}>
    <polyline points="4 7 4 4 20 4 20 7" />
    <line x1="9" y1="20" x2="15" y2="20" />
    <line x1="12" y1="4" x2="12" y2="20" />
  </TI>
);
const ActivityIcon = (p) => (
  <TI {...p}>
    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
  </TI>
);
const PowerIcon = (p) => (
  <TI {...p}>
    <path d="M18.4 6.6a9 9 0 1 1-12.8 0" />
    <line x1="12" y1="2" x2="12" y2="12" />
  </TI>
);
const KeyboardIcon = (p) => (
  <TI {...p}>
    <rect x="2" y="6" width="20" height="12" rx="2" />
    <path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10" />
  </TI>
);
const CalendarClockIcon = (p) => (
  <TI {...p}>
    <path d="M21 7.5V6a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h6" />
    <line x1="16" y1="2" x2="16" y2="6" />
    <line x1="8" y1="2" x2="8" y2="6" />
    <line x1="3" y1="10" x2="21" y2="10" />
    <circle cx="17.5" cy="16.5" r="4" />
    <path d="M17.5 15v1.5l1 .8" />
  </TI>
);
const MicrophoneIcon = (p) => (
  <TI {...p}>
    <rect x="9" y="2" width="6" height="12" rx="3" />
    <path d="M5 10a7 7 0 0 0 14 0" />
    <line x1="12" y1="19" x2="12" y2="22" />
  </TI>
);
const VolumeIcon = (p) => (
  <TI {...p}>
    <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
    <path d="M15.5 8.5a5 5 0 0 1 0 7M19 5a9 9 0 0 1 0 14" />
  </TI>
);
const CpuIcon = (p) => (
  <TI {...p}>
    <rect x="4" y="4" width="16" height="16" rx="2" />
    <rect x="9" y="9" width="6" height="6" />
    <path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3" />
  </TI>
);
const KeyIcon = (p) => (
  <TI {...p}>
    <circle cx="7.5" cy="15.5" r="4.5" />
    <path d="M10.7 12.3 21 2M16 7l3 3M14 9l2 2" />
  </TI>
);
const ShieldIcon = (p) => (
  <TI {...p}>
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
  </TI>
);
function RedactIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  );
}
const BanIcon = (p) => (
  <TI {...p}>
    <circle cx="12" cy="12" r="10" />
    <line x1="4.93" y1="4.93" x2="19.07" y2="19.07" />
  </TI>
);
const TrashIcon = (p) => (
  <TI {...p}>
    <polyline points="3 6 5 6 21 6" />
    <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
    <path d="M10 11v6M14 11v6" />
    <path d="M9 6V4a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2" />
  </TI>
);
const SpreadsheetIcon = (p) => (
  <TI {...p}>
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <path d="M14 2v6h6" />
    <path d="M8 13h8M8 17h8M12 13v4" />
  </TI>
);
const FileTextIcon = (p) => (
  <TI {...p}>
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <path d="M14 2v6h6" />
    <line x1="8" y1="13" x2="16" y2="13" />
    <line x1="8" y1="17" x2="16" y2="17" />
    <line x1="8" y1="9" x2="10" y2="9" />
  </TI>
);
const LockIcon = (p) => (
  <TI {...p}>
    <rect x="3" y="11" width="18" height="11" rx="2" />
    <path d="M7 11V7a5 5 0 0 1 10 0v4" />
  </TI>
);
const CrownIcon = (p) => (
  <TI {...p}>
    <path d="M2 18h20M3 18l1.5-9 5 5 2.5-7 2.5 7 5-5L21 18" />
  </TI>
);
const CodeIcon = (p) => (
  <TI {...p}>
    <polyline points="16 18 22 12 16 6" />
    <polyline points="8 6 2 12 8 18" />
  </TI>
);
const RefreshIcon = (p) => (
  <TI {...p}>
    <polyline points="23 4 23 10 17 10" />
    <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
  </TI>
);
const CalendarIcon = (p) => (
  <TI {...p}>
    <rect x="3" y="4" width="18" height="18" rx="2" />
    <line x1="16" y1="2" x2="16" y2="6" />
    <line x1="8" y1="2" x2="8" y2="6" />
    <line x1="3" y1="10" x2="21" y2="10" />
  </TI>
);
function ToggleSwitch({ checked, onChange, label }) {
  return (
    <button
      className={`set-toggle${checked ? " on" : ""}`}
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
    >
      <span className="set-toggle-thumb" />
    </button>
  );
}

// Opt-in MCP access: AI assistants launch Jotva's read-only MCP server themselves.
function McpAccessCard({ enabled, onToggle, showToast, locked }) {
  const { t } = useTranslation();
  const bridge = window.jotva;
  const [busy, setBusy] = useState(false);
  const addToClaude = async () => {
    setBusy(true);
    try {
      const r = await bridge.mcpInstallClaude();
      if (r?.ok) showToast(t("settings.mcp.added"));
      else showToast(t("settings.mcp.addFailed"), "error");
    } finally {
      setBusy(false);
    }
  };
  const copySetup = async () => {
    const server = await bridge.mcpConfig();
    await navigator.clipboard.writeText(JSON.stringify({ mcpServers: { jotva: server } }, null, 2));
    showToast(t("settings.mcp.copied"));
  };
  return (
    <div className="set-card mcp-card">
      <div className="set-card-icon"><SparkIcon size={17} /></div>
      <div className="set-card-main">
        <div className="set-card-name">
          {t("settings.mcp.title")}
          {locked && <span className="pro-badge">{t("upgrade.badge")}</span>}
        </div>
        <div className="set-card-desc">{t("settings.mcp.desc")}</div>
      </div>
      <div className="set-card-control">
        <ToggleSwitch checked={enabled} onChange={onToggle} label={t("settings.mcp.title")} />
      </div>
      {enabled && (
        <div className="mcp-actions">
          {bridge?.mcpInstallClaude && <button className="btn" disabled={busy} onClick={addToClaude}>{t("settings.mcp.addClaude")}</button>}
          {bridge?.mcpConfig && <button className="btn secondary" onClick={copySetup}>{t("settings.mcp.copy")}</button>}
        </div>
      )}
      <p className="mcp-note">{t("settings.mcp.privacy")}</p>
    </div>
  );
}

const THEME_PREVIEW = {
  default: ["#f5f5fb", "#6b58e6", "#16152a"],
  dark: ["#07070d", "#8b7bff", "#eeeef6"],
};

const SECRET_FIELDS = [
  { name: "anthropic_api_key", label: "Anthropic API key", tab: "ai" },
  { name: "slack_webhook_url", label: "Slack webhook URL", tab: "integrations" },
  { name: "notion_token", label: "Notion integration token", tab: "integrations" },
  { name: "notion_database_id", label: "Notion database ID", tab: "integrations" },
  { name: "linear_api_key", label: "Linear API key", tab: "integrations" },
  { name: "jira_base_url", label: "Jira base URL", tab: "integrations" },
  { name: "jira_email", label: "Jira account email", tab: "integrations" },
  { name: "jira_token", label: "Jira API token", tab: "integrations" },
  { name: "hubspot_token", label: "HubSpot private app token", tab: "integrations" },
  { name: "salesforce_instance_url", label: "Salesforce instance URL", tab: "integrations" },
  { name: "salesforce_token", label: "Salesforce access token", tab: "integrations" },
  { name: "zapier_webhook_url", label: "Zapier webhook URL", tab: "integrations" },
];

const INTEGRATIONS = [
  { key: "slack", name: "Slack", desc: "Post a formatted meeting digest to a channel via incoming webhook.", fields: ["slack_webhook_url"] },
  { key: "notion", name: "Notion", desc: "Create a page with the full notes in any Notion database.", fields: ["notion_token", "notion_database_id"] },
  { key: "linear", name: "Linear", desc: "File the meeting notes as a Linear issue in your team.", fields: ["linear_api_key"] },
  { key: "jira", name: "Jira", desc: "Create a Jira task carrying the full notes.", fields: ["jira_base_url", "jira_email", "jira_token"] },
  { key: "hubspot", name: "HubSpot", desc: "Log the meeting as a note on your HubSpot CRM timeline.", fields: ["hubspot_token"] },
  { key: "salesforce", name: "Salesforce", desc: "Save the notes as a Salesforce Note object.", fields: ["salesforce_instance_url", "salesforce_token"] },
  { key: "google_drive", name: "Google Drive", desc: "Upload notes as Markdown. Uses your Google Calendar connection — no extra key.", fields: [], oauth: true },
  { key: "zapier", name: "Zapier", desc: "Send title + notes JSON to any Zap via catch-hook webhook.", fields: ["zapier_webhook_url"] },
];

const FIELD_LABELS = Object.fromEntries(SECRET_FIELDS.map((f) => [f.name, f.label]));

// Maps each secret field name to its i18n suffix under settings.integrations.fields.*
const FIELD_KEYS = {
  anthropic_api_key: "anthropicKey",
  slack_webhook_url: "slackWebhook",
  notion_token: "notionToken",
  notion_database_id: "notionDb",
  linear_api_key: "linearKey",
  jira_base_url: "jiraBase",
  jira_email: "jiraEmail",
  jira_token: "jiraToken",
  hubspot_token: "hubspotToken",
  salesforce_instance_url: "salesforceUrl",
  salesforce_token: "salesforceToken",
  zapier_webhook_url: "zapierWebhook",
};

function SecretField({ name, label, isSet, onSaved }) {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const { showToast, handleError } = useStore();
  const { t } = useTranslation();

  const save = () => {
    if (!value.trim()) return;
    setBusy(true);
    api
      .post("/api/secrets", { name, value: value.trim() })
      .then(() => {
        setValue("");
        showToast(t('settings.toast.savedKeychain', { name: label }));
        onSaved();
      })
      .catch(handleError) // an own AI key on Free opens the Pro prompt
      .finally(() => setBusy(false));
  };

  return (
    <div className="field">
      <label className="field-label">
        {label}{" "}
        {isSet && <span style={{ color: "var(--accent)", fontSize: 10.5 }}>{t('settings.secret.configured')}</span>}
      </label>
      <div style={{ display: "flex", gap: 7 }}>
        <input
          className="text-input"
          type="password"
          placeholder={isSet ? t('settings.secret.savedKeychainPlaceholder') : t('settings.secret.pasteValue')}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && save()}
        />
        <button className="btn" disabled={busy || !value.trim()} onClick={save}>
          {t('settings.secret.save')}
        </button>
      </div>
    </div>
  );
}

// Credential editor for the Integrations detail panel (FIX 1). Saves each
// field to the keychain via the existing /api/secrets endpoint; Disconnect
// clears them via the existing DELETE /api/secrets/{name} endpoint.
function IntegrationConfig({ ig, secrets, onSaved }) {
  const { showToast } = useStore();
  const { t } = useTranslation();
  const [values, setValues] = useState({});
  const [busy, setBusy] = useState(false);

  const connected = ig.fields.length > 0 && ig.fields.every((f) => secrets[f]);

  const save = () => {
    const entries = ig.fields
      .map((f) => [f, (values[f] || "").trim()])
      .filter(([, v]) => v.length > 0);
    if (entries.length === 0) return;
    setBusy(true);
    Promise.all(entries.map(([name, value]) => api.post("/api/secrets", { name, value })))
      .then(() => {
        setValues({});
        showToast(t('settings.toast.savedKeychain', { name: ig.name }));
        onSaved();
      })
      .catch((e) => showToast(e.message, "error"))
      .finally(() => setBusy(false));
  };

  const disconnect = () => {
    setBusy(true);
    Promise.all(ig.fields.map((name) => api.delete(`/api/secrets/${name}`)))
      .then(() => {
        showToast(t('settings.toast.disconnected', { name: ig.name }));
        onSaved();
      })
      .catch((e) => showToast(e.message, "error"))
      .finally(() => setBusy(false));
  };

  return (
    <>
      <div className="tpl-sections-label">{t('settings.secret.configuration')}</div>
      {ig.fields.map((f) => (
        <div className="ig-field" key={f}>
          <label className="ig-field-label">{FIELD_KEYS[f] ? t('settings.integrations.fields.' + FIELD_KEYS[f]) : (FIELD_LABELS[f] || f)}</label>
          <input
            className="text-input"
            type="password"
            placeholder={secrets[f] ? t('settings.secret.savedKeychainPlaceholder') : t('settings.secret.pasteValue')}
            value={values[f] || ""}
            onChange={(e) => setValues((s) => ({ ...s, [f]: e.target.value }))}
            onKeyDown={(e) => e.key === "Enter" && save()}
          />
        </div>
      ))}
      <button className="tpl-use-btn" disabled={busy} onClick={save}>
        {busy ? t('settings.secret.saving') : t('settings.secret.save')}
      </button>
      {connected && (
        <button className="ig-disconnect" disabled={busy} onClick={disconnect}>
          {t('settings.secret.disconnect')}
        </button>
      )}
    </>
  );
}

// Email accounts for "Waiting on you" (Pro). App passwords go to the Keychain via
// the backend and are never shown again; the mailbox is only ever read.
const EMAIL_PROVIDERS = {
  gmail: { help: "https://myaccount.google.com/apppasswords" },
  icloud: { help: "https://account.apple.com/account/manage" },
  imap: { help: null },
};

function EmailAccountsCard({ hasFeature, openUpgrade, showToast, handleError }) {
  const { t } = useTranslation();
  const [accounts, setAccounts] = useState([]);
  const [form, setForm] = useState(null); // { provider, address, password, host, port }
  const [busy, setBusy] = useState(false);
  const load = () => api.get("/api/email/accounts").then((r) => setAccounts(r.accounts)).catch(() => {});
  useEffect(() => { load(); }, []);
  const start = (provider) => (hasFeature("email") ? setForm({ provider, address: "", password: "", host: "", port: 993 }) : openUpgrade("email"));
  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const body = { provider: form.provider, address: form.address, password: form.password };
      if (form.provider === "imap") Object.assign(body, { host: form.host, port: Number(form.port) || 993 });
      await api.post("/api/email/accounts", body);
      setForm(null);
      showToast(t("settings.email.connected"));
      load();
    } catch (err) {
      handleError(err);
    } finally {
      setBusy(false);
    }
  };
  const remove = (id) => api.delete(`/api/email/accounts/${id}`).then(load).catch(handleError);
  return (
    <div className="set-card stack email-card">
      <div className="set-card-icon"><SparkIcon size={17} /></div>
      <div className="set-card-main">
        <div className="set-card-name">
          {t("settings.email.title")}
          {!hasFeature("email") && <span className="pro-badge">{t("upgrade.badge")}</span>}
        </div>
        <div className="set-card-desc">{t("settings.email.desc")}</div>
      </div>
      {accounts.map((a) => (
        <div key={a.id} className="email-account-row">
          <span>{a.address}</span>
          <span className={a.last_error ? "email-account-error" : "email-account-ok"}>
            {a.last_error ? t("settings.email.error") : a.last_sync ? t("settings.email.synced") : t("settings.email.syncing")}
          </span>
          <button className="btn compact secondary" onClick={() => remove(a.id)}>{t("settings.email.remove")}</button>
        </div>
      ))}
      {form ? (
        <form className="email-form" onSubmit={save}>
          <div className="email-form-title">{t(`settings.email.providers.${form.provider}`)}</div>
          <p className="set-card-desc">
            {t(`settings.email.howto.${form.provider}`)}{" "}
            {EMAIL_PROVIDERS[form.provider].help && (
              <button type="button" className="link-btn" onClick={() => openExternal(EMAIL_PROVIDERS[form.provider].help)}>
                {t("settings.email.createPassword")}
              </button>
            )}
          </p>
          <input className="text-input" type="email" required autoFocus placeholder={t("settings.email.address")}
            value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
          <input className="text-input" type="password" required placeholder={t("settings.email.appPassword")}
            autoComplete="off" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
          {form.provider === "imap" && (
            <div className="email-form-row">
              <input className="text-input" required placeholder={t("settings.email.server")}
                value={form.host} onChange={(e) => setForm({ ...form, host: e.target.value })} />
              <input className="text-input" type="number" required min={1} max={65535} style={{ width: 90 }}
                value={form.port} onChange={(e) => setForm({ ...form, port: e.target.value })} />
            </div>
          )}
          <p className="set-card-desc">{t("settings.email.privacy")}</p>
          <div className="email-form-row">
            <button type="button" className="btn secondary" onClick={() => setForm(null)}>{t("common.cancel")}</button>
            <button className="btn" disabled={busy}>{busy ? t("settings.email.checking") : t("settings.email.connect")}</button>
          </div>
        </form>
      ) : (
        <div className="email-providers">
          {["gmail", "icloud", "imap"].map((p) => (
            <button key={p} className="btn secondary" onClick={() => start(p)}>{t(`settings.email.providers.${p}`)}</button>
          ))}
          <button className="btn secondary" disabled title={t("settings.email.soon")}>{t("settings.email.providers.microsoft")}</button>
        </div>
      )}
    </div>
  );
}

// Free plan: this month's bundled-AI notes (hidden when unlimited: Pro or own key).
function AiAllowance({ license }) {
  const { t, i18n } = useTranslation();
  if (!license || license.ai_notes_limit == null) return null;
  const { ai_notes_limit: limit, ai_notes_remaining: remaining } = license;
  const resets = new Intl.DateTimeFormat(i18n.language, { month: "long", day: "numeric" }).format(
    new Date(`${license.ai_notes_resets_on}T00:00:00`)
  );
  return (
    <div className="ai-allowance">
      <div className="ai-allowance-row">
        <span>{t("aiAllowance.left", { remaining, limit })}</span>
        <span>{t("aiAllowance.resets", { date: resets })}</span>
      </div>
      <div className="ai-allowance-bar" role="progressbar" aria-valuemin={0} aria-valuemax={limit} aria-valuenow={limit - remaining}>
        <span style={{ width: `${Math.min(100, ((limit - remaining) / limit) * 100)}%` }} />
      </div>
    </div>
  );
}

// Setting values only Pro may turn on (mirrors _PRO_SETTING_VALUES in routes/misc.py).
const PRO_SETTING_VALUES = {
  "mcp_enabled:true": "mcp",
  "recording_mode:all": "auto_record",
  "ai_quality:pro": "higher_quality",
  "ai_provider:openai": "own_key",
  "ai_provider:google": "own_key",
};

export default function Settings() {
  const {
    settingsOpen,
    setSettingsOpen,
    settingsSection,
    openSettings,
    theme,
    setTheme,
    avatar,
    setAvatar,
    settings,
    setSettings,
    calendarStatus,
    refreshCalendar,
    license,
    refreshLicense,
    showToast,
    templates,
    refreshTemplates,
    setSelectedTemplate,
    workspace,
    refreshWorkspace,
    hasFeature,
    openUpgrade,
    handleError,
  } = useStore();
  const { t } = useTranslation();
  const tab = settingsSection || "general";
  const [tplDetailId, setTplDetailId] = useState(null);
  const [secrets, setSecrets] = useState({});
  const [devices, setDevices] = useState({ devices: [] });
  const [msFlow, setMsFlow] = useState(null);
  const [portalLoading, setPortalLoading] = useState(false);
  const [autoLaunch, setAutoLaunch] = useState(false);
  const [userName, setUserName] = useState("");
  const photoInput = useRef(null);
  const [photoBusy, setPhotoBusy] = useState(false);
  const choosePhoto = async (file) => {
    if (!file) return;
    setPhotoBusy(true);
    try {
      const image = await imageFileToAvatar(file);
      await api.post("/api/settings/avatar", { image });
      setAvatar(image);
      showToast(t("settings.general.photoSaved"));
    } catch (e) {
      showToast(e.message === "invalid-image" ? t("settings.general.photoInvalid") : e.message, "error");
    } finally {
      setPhotoBusy(false);
      if (photoInput.current) photoInput.current.value = "";
    }
  };
  const removePhoto = () =>
    api.delete("/api/settings/avatar")
      .then(() => { setAvatar(null); showToast(t("settings.general.photoRemoved")); })
      .catch((e) => showToast(e.message, "error"));
  const [models, setModels] = useState({});
  const [editingTemplate, setEditingTemplate] = useState(null); // {id?,name,description,body}
  const [vaultPassword, setVaultPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [openIntegration, setOpenIntegration] = useState(null);
  const [setupModal, setSetupModal] = useState(null); // "google" | "microsoft" | null
  // Workspace state
  const [wsName, setWsName] = useState("");
  const [wsDisplayName, setWsDisplayName] = useState("");
  const [wsInviteCode, setWsInviteCode] = useState("");
  const [wsSharePath, setWsSharePath] = useState("");
  // Mobile state
  const [mobileSessions, setMobileSessions] = useState([]);
  const isWin = (window.jotva?.platform || "darwin") === "win32";

  const loadSecrets = () =>
    api.get("/api/integrations/status").then((r) => setSecrets(r.secrets)).catch(() => {});

  const loadMobileSessions = () =>
    api.get("/api/mobile/sessions").then(setMobileSessions).catch(() => {});

  useEffect(() => {
    if (settingsOpen) {
      loadSecrets();
      api.get("/api/recording/devices").then(setDevices).catch(() => {});
      api.get("/api/settings/user-name").then((r) => setUserName(r.user_name || "")).catch(() => {});
      refreshCalendar();
      loadMobileSessions();
      window.jotva
        ?.getAutoLaunch?.()
        .then((r) => setAutoLaunch(!!r?.enabled))
        .catch(() => {});
      // Populate share path from current workspace state
      if (workspace?.workspace?.share_path) {
        setWsSharePath(workspace.workspace.share_path);
      }
    }
  }, [settingsOpen]); // eslint-disable-line react-hooks/exhaustive-deps

  // Bring-your-own-key model lists come live from the provider (cached ~6h by the
  // backend); refetch when the provider or its key changes.
  const aiProvider = settings.ai_provider || "anthropic";
  const aiKeySet = !!secrets[AI_KEY_NAMES[aiProvider]];
  useEffect(() => {
    if (!settingsOpen || tab !== "ai") return;
    api
      .get(`/api/ai/models?provider=${encodeURIComponent(aiProvider)}`)
      .then((list) => setModels((m) => ({ ...m, [aiProvider]: list })))
      .catch(() => {});
  }, [settingsOpen, tab, aiProvider, aiKeySet]);

  const toggleAutoLaunch = () => {
    const next = !autoLaunch;
    setAutoLaunch(next);
    window.jotva?.setAutoLaunch?.(next);
    api.post("/api/settings", { key: "auto_launch", value: next }).catch(() => {});
  };

  if (!settingsOpen) return null;

  const saveSetting = (key, value) => {
    const proFeature = PRO_SETTING_VALUES[`${key}:${value}`];
    if (proFeature && !hasFeature(proFeature)) return openUpgrade(proFeature);
    setSettings((s) => ({ ...s, [key]: value }));
    api.post("/api/settings", { key, value }).catch(handleError);
  };

  const connectGoogle = () => {
    api
      .post("/api/calendar/google/connect")
      .then(({ auth_url }) => openExternal(auth_url))
      .catch((e) => showToast(e.message, "error"));
  };

  const connectMicrosoft = () => {
    api
      .post("/api/calendar/microsoft/connect")
      .then((flow) => {
        setMsFlow(flow);
        openExternal(flow.verification_uri);
      })
      .catch((e) => showToast(e.message, "error"));
  };

  const openPortal = () => {
    setPortalLoading(true);
    api
      .get("/api/license/portal-url")
      .then((r) => {
        if (r?.url) {
          openExternal(r.url);
        } else if (r?.error === "no_subscription") {
          showToast(t('settings.toast.noSubscription'), "error");
        } else {
          showToast(t('settings.toast.portalUnavailable'), "error");
        }
      })
      .catch(() => showToast(t('settings.toast.portalUnavailable'), "error"))
      .finally(() => setPortalLoading(false));
  };

  // DEV ONLY: flip the local license tier for testing; the sidebar re-reads
  // license state immediately via refreshLicense(). Backed by /api/dev/set-tier,
  // which is only registered when the backend runs in development.
  const switchTier = (tier) => {
    api
      .post("/api/dev/set-tier", { tier })
      .then(() => {
        refreshLicense();
        showToast(t('settings.toast.switched', { plan: tier === "pro" ? t('settings.license.planPro') : t('settings.license.planFree') }));
      })
      .catch((e) => showToast(e.message, "error"));
  };

  return (
    <div className="settings-layer">
      <SettingsPanel section={tab} title={t(`dock.labels.${settingsLabel(tab)}`, { defaultValue: settingsLabel(tab) })} onClose={() => setSettingsOpen(false)}>
        <div className="settings-layout">
          <div className="modal-body">
          {tab === "general" && (
            <>
              <div className="set-section-label first">{t('settings.general.label')}</div>
              <div className="set-card stack profile-card">
                <button type="button" className="profile-avatar" onClick={() => photoInput.current?.click()}
                  disabled={photoBusy} aria-label={t(avatar ? 'settings.general.photoChange' : 'settings.general.photoUpload')}>
                  {avatar ? <img src={avatar} alt="" /> : initialsOf(userName) || <UsersIcon size={18} />}
                </button>
                <div className="set-card-main">
                  <div className="set-card-name">{t('settings.general.yourName')}</div>
                  <div className="set-card-desc">{t('settings.general.yourNameDesc')}</div>
                  <div className="profile-actions">
                    <button type="button" className="btn secondary compact" disabled={photoBusy} onClick={() => photoInput.current?.click()}>
                      {t(avatar ? 'settings.general.photoChange' : 'settings.general.photoUpload')}
                    </button>
                    {avatar && <button type="button" className="btn secondary compact" onClick={removePhoto}>{t('settings.general.photoRemove')}</button>}
                    <input ref={photoInput} type="file" accept="image/jpeg,image/png,image/webp,image/gif" hidden
                      onChange={(e) => choosePhoto(e.target.files?.[0])} />
                  </div>
                </div>
                <div className="set-card-control">
                  <input
                    className="text-input"
                    value={userName}
                    placeholder={t('settings.general.namePlaceholder')}
                    onChange={(e) => setUserName(e.target.value)}
                    onBlur={() => {
                      const v = userName.trim();
                      if (v)
                        api
                          .post("/api/settings/user-name", { name: v })
                          .then(() => showToast(t('settings.general.nameSaved')))
                          .catch((e) => showToast(e.message, "error"));
                    }}
                  />
                </div>
              </div>
              <div className="set-card stack">
                <div className="set-card-main">
                  <div className="set-card-name">{t('settings.general.language')}</div>
                </div>
                <div className="set-card-control">
                  <Select
                    value={i18n.language}
                    onChange={setLanguage}
                    options={[
                      { value: "en", label: "English" },
                      { value: "es", label: "Español" },
                      { value: "pt", label: "Português" },
                      { value: "fr", label: "Français" },
                      { value: "zh", label: "中文" },
                      { value: "ko", label: "한국어" },
                    ]}
                  />
                </div>
              </div>
            </>
          )}
          {tab === "appearance" && (
            <>
              <div className="set-section-label first">{t('settings.appearance.label')}</div>
              <div className="set-card stack">
                <div className="set-card-icon"><PaletteIcon size={14} /></div>
                <div className="set-card-main">
                  <div className="set-card-name">{t('settings.appearance.theme')}</div>
                  <div className="set-card-desc">{t('settings.appearance.themeDesc')}</div>
                </div>
                <div className="set-card-control">
                  <div className="theme-grid">
                    {THEMES.map((name) => (
                      <button
                        key={name}
                        className={`theme-swatch${theme === name ? " active" : ""}`}
                        onClick={() => setTheme(name)}
                      >
                        <span className="swatch-colors">
                          {THEME_PREVIEW[name].map((c) => (
                            <span key={c} className="swatch-dot" style={{ background: c }} />
                          ))}
                        </span>
                        <span className="swatch-name">
                          {t('settings.appearance.themes.' + name)}
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
              <div className="set-card">
                <div className="set-card-icon"><TextSizeIcon size={14} /></div>
                <div className="set-card-main">
                  <div className="set-card-name">{t('settings.appearance.fontSize')}</div>
                  <div className="set-card-desc">{t('settings.appearance.fontSizeDesc')}</div>
                </div>
                <div className="set-card-control">
                  {(() => {
                    const fontSizes = ["small", "medium", "large"];
                    const fontLabels = [t('settings.appearance.small'), t('settings.appearance.medium'), t('settings.appearance.large')];
                    const currentIndex = fontSizes.indexOf(settings.font_size || "medium");
                    return (
                      <div className="segmented seg-slider" style={{ position: "relative", maxWidth: 300 }}>
                        <div
                          className="seg-pill"
                          style={{
                            position: "absolute",
                            top: 3,
                            bottom: 3,
                            left: `calc(${currentIndex} * (100% / 3) + 3px)`,
                            width: "calc(100% / 3 - 6px)",
                            background: "var(--panel)",
                            borderRadius: 6,
                            boxShadow: "var(--shadow-sm)",
                            transition: "left 0.25s cubic-bezier(0.34, 1.56, 0.64, 1)",
                            pointerEvents: "none",
                            zIndex: 0,
                          }}
                        />
                        {fontLabels.map((label, i) => (
                          <button
                            key={fontSizes[i]}
                            onClick={() => saveSetting("font_size", fontSizes[i])}
                            style={{
                              flex: 1,
                              padding: "6px 0",
                              borderRadius: 6,
                              fontSize: 11.5,
                              fontWeight: 600,
                              color: currentIndex === i ? "var(--accent-ink)" : "var(--muted)",
                              background: "transparent",
                              border: "none",
                              cursor: "pointer",
                              position: "relative",
                              zIndex: 1,
                              transition: "color 0.25s ease",
                            }}
                          >
                            {label}
                          </button>
                        ))}
                      </div>
                    );
                  })()}
                </div>
              </div>
              <div className="set-card">
                <div className="set-card-icon"><ActivityIcon size={14} /></div>
                <div className="set-card-main">
                  <div className="set-card-name">{t('settings.appearance.reduceMotion')}</div>
                  <div className="set-card-desc">{t('settings.appearance.reduceMotionDesc')}</div>
                </div>
                <div className="set-card-control">
                  <button
                    className={`btn${settings.reduce_motion ? "" : " secondary"}`}
                    onClick={() => saveSetting("reduce_motion", !settings.reduce_motion)}
                  >
                    {settings.reduce_motion ? t('settings.appearance.enabled') : t('settings.appearance.disabled')}
                  </button>
                </div>
              </div>
            </>
          )}

          {tab === "recording" && (
            <>
              <div className="set-section-label first">{t('settings.recording.startup')}</div>
              <div className="set-card">
                <div className="set-card-icon"><PowerIcon size={14} /></div>
                <div className="set-card-main">
                  <div className="set-card-name">{t('settings.recording.launchLogin')}</div>
                  <div className="set-card-desc">{t('settings.recording.launchLoginDesc')}</div>
                </div>
                <div className="set-card-control">
                  <button
                    className={`btn${autoLaunch ? "" : " secondary"}`}
                    onClick={toggleAutoLaunch}
                  >
                    {autoLaunch ? t('settings.recording.on') : t('settings.recording.off')}
                  </button>
                </div>
              </div>
              <div className="set-card">
                <div className="set-card-icon"><KeyboardIcon size={14} /></div>
                <div className="set-card-main">
                  <div className="set-card-name">{t('settings.recording.globalShortcut')}</div>
                  <div className="set-card-desc">
                    {t('settings.recording.globalShortcutDesc')}
                  </div>
                </div>
                <div className="set-card-control">
                  <strong>{isWin ? "Ctrl+Shift+R" : "⌘+Shift+R"}</strong>
                </div>
              </div>

              <div className="set-section-label">{t('settings.recording.capture')}</div>
              <div className="set-card">
                <div className="set-card-icon"><CalendarClockIcon size={14} /></div>
                <div className="set-card-main">
                  <div className="set-card-name">{t('settings.recording.autoMode')}</div>
                  <div className="set-card-desc">{t('settings.recording.autoModeDesc')}</div>
                </div>
                <div className="set-card-control">
                  <Select
                    value={settings.recording_mode || "confirm_30s"}
                    onChange={(v) => saveSetting("recording_mode", v)}
                    options={[
                      { value: "all", label: hasFeature("auto_record") ? t('settings.recording.modeAll') : `${t('settings.recording.modeAll')} · ${t('upgrade.badge')}` },
                      { value: "confirm_30s", label: t('settings.recording.mode30') },
                      { value: "manual", label: t('settings.recording.modeManual') },
                      { value: "off", label: t('settings.recording.modeOff') },
                    ]}
                  />
                </div>
              </div>
              <div className="set-card">
                <div className="set-card-icon"><SparkIcon size={14} /></div>
                <div className="set-card-main">
                  <div className="set-card-name">
                    {t('settings.recording.liveNotes')}
                    {!hasFeature("live_notes") && <span className="pro-badge">{t('upgrade.badge')}</span>}
                  </div>
                  <div className="set-card-desc">{t('settings.recording.liveNotesDesc')}</div>
                </div>
                <div className="set-card-control">
                  <ToggleSwitch
                    checked={hasFeature("live_notes") && settings.live_notes_enabled !== false}
                    onChange={(on) => saveSetting("live_notes_enabled", on)}
                    label={t('settings.recording.liveNotes')}
                  />
                </div>
              </div>
              <div className="set-card stack">
                <div className="set-card-icon"><MicrophoneIcon size={14} /></div>
                <div className="set-card-main">
                  <div className="set-card-name">{t('settings.recording.microphone')}</div>
                  <div className="set-card-desc">
                    {settings.mic_device == null && devices.default_input?.name
                      ? t('settings.recording.micDescResolved', { name: devices.default_input.name })
                      : t('settings.recording.micDesc')}
                  </div>
                  {((settings.mic_device == null && devices.default_input?.is_loopback_like) ||
                    devices.devices.find((d) => d.index === settings.mic_device)?.is_loopback_like) && (
                    <div className="set-card-warning">{t('settings.recording.micLoopbackWarning')}</div>
                  )}
                </div>
                <div className="set-card-control">
                  <Select
                    value={settings.mic_device ?? null}
                    onChange={(v) => saveSetting("mic_device", v)}
                    options={[
                      { value: null, label: t('settings.recording.systemDefault') },
                      ...devices.devices.map((d) => ({
                        value: d.index,
                        label: `${d.name}${d.is_loopback_like ? t('settings.recording.loopbackSuffix') : ""}`,
                      })),
                    ]}
                  />
                </div>
              </div>
              <div className="set-card stack">
                <div className="set-card-icon"><VolumeIcon size={14} /></div>
                <div className="set-card-main">
                  <div className="set-card-name">{t('settings.recording.systemAudio')}</div>
                  <div className="set-card-desc">
                    {isWin
                      ? t('settings.recording.winHint')
                      : t('settings.recording.macHint')}
                  </div>
                </div>
                <div className="set-card-control">
                  <Select
                    value={settings.system_device ?? null}
                    onChange={(v) => saveSetting("system_device", v)}
                    options={[
                      { value: null, label: t('settings.recording.none') },
                      ...devices.devices.map((d) => ({
                        value: d.index,
                        label: `${d.name}${d.is_loopback_like ? t('settings.recording.loopbackSuffix') : ""}`,
                      })),
                    ]}
                  />
                </div>
              </div>

              <SpeakerSettings enabled={settings.speaker_identification === true} onSaved={value => setSettings(s => ({...s, speaker_identification: value}))} />
              <div className="set-section-label">{t('settings.recording.transcription')}</div>
              <div className="set-card">
                <div className="set-card-icon"><CpuIcon size={14} /></div>
                <div className="set-card-main">
                  <div className="set-card-name">{t('settings.recording.whisperModel')}</div>
                  <div className="set-card-desc">{t('settings.recording.whisperDesc')}</div>
                </div>
                <div className="set-card-control">
                  <Select
                    value={settings.whisper_model || "small"}
                    onChange={(v) => saveSetting("whisper_model", v)}
                    options={[
                      { value: "tiny", label: t('settings.recording.modelTiny') },
                      { value: "base", label: t('settings.recording.modelBase') },
                      { value: "small", label: t('settings.recording.modelSmall') },
                      { value: "medium", label: t('settings.recording.modelMedium') },
                    ]}
                  />
                </div>
              </div>
            </>
          )}

          {tab === "ai" && (() => {
            const PROVIDERS = [
              { id: "anthropic", name: "Anthropic", keyName: "anthropic_api_key", keyLabel: "Anthropic API key", modelKey: "claude_model", link: "https://console.anthropic.com/" },
              { id: "openai", name: "OpenAI", keyName: "openai_api_key", keyLabel: "OpenAI API key", modelKey: "openai_model", link: "https://platform.openai.com/api-keys" },
              { id: "google", name: "Google", keyName: "google_api_key", keyLabel: "Google API key", modelKey: "gemini_model", link: "https://aistudio.google.com/apikey" },
            ];
            const provider = aiProvider;
            const active = PROVIDERS.find((p) => p.id === provider) || PROVIDERS[0];
            // No Anthropic key = Jotva's bundled AI: offer quality tiers, not model ids.
            const bundled = provider === "anthropic" && !aiKeySet;
            const isPro = license?.tier === "pro";
            const providerModels = Array.isArray(models[provider]) ? models[provider] : [];
            const saved = settings[active.modelKey];
            // A saved alias may be listed only as its dated snapshot (claude-haiku-4-5-20251001).
            const listed =
              providerModels.find((m) => m.id === saved) ||
              providerModels.find((m) => saved && m.id.startsWith(saved + "-")) ||
              (!saved && providerModels.find((m) => m.recommended));
            const selectedModel = listed ? listed.id : saved || "";
            const modelOptions = providerModels.map((m) => ({
              value: m.id,
              label: m.recommended ? t('settings.ai.recommendedLabel', { name: m.name }) : m.name,
            }));
            if (saved && !listed && providerModels.length) modelOptions.push({ value: saved, label: saved });
            const chooseQuality = (v) => saveSetting("ai_quality", v);
            return (
              <>
                <div className="set-section-label first">{t('settings.ai.title')}</div>
                <div className="field-help" style={{ marginBottom: 8 }}>
                  {t('settings.ai.includedNote')}
                </div>
                <div className="set-card stack">
                  <div className="set-card-main">
                    <div className="set-card-name">{t('settings.ai.provider')}</div>
                    <div className="set-card-desc">
                      {t('settings.ai.privacyNote', { name: active.name })}
                    </div>
                  </div>
                  <div className="set-card-control">
                    <div style={{ display: "flex", gap: 6 }}>
                      {PROVIDERS.map((p) => (
                        <button
                          key={p.id}
                          className={`btn${provider === p.id ? "" : " secondary"}`}
                          onClick={() => saveSetting("ai_provider", p.id)}
                        >
                          {p.name}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="set-card stack">
                  <div className="set-card-icon"><KeyIcon size={14} /></div>
                  {!hasFeature("own_key") && (
                    <div className="set-card-desc own-key-pro">
                      <span className="pro-badge">{t('upgrade.badge')}</span> {t('upgrade.feature.own_key.body')}
                    </div>
                  )}
                  <SecretField
                    name={active.keyName}
                    label={t('settings.ai.keyLabel.' + active.id)}
                    isSet={secrets[active.keyName]}
                    onSaved={loadSecrets}
                  />
                </div>
                <div className="field-help" style={{ marginTop: -4 }}>
                  <button
                    onClick={() => openExternal(active.link)}
                    style={{ background: "none", border: "none", color: "var(--accent)", cursor: "pointer", fontSize: 11, padding: 0 }}
                  >
                    {t('settings.ai.getKey', { name: active.name })}
                  </button>
                </div>

                {bundled ? (
                  <div className="set-card stack">
                    <div className="set-card-icon"><StarIcon size={14} /></div>
                    <div className="set-card-main">
                      <div className="set-card-name">{t('settings.ai.quality')}</div>
                      <div className="set-card-desc">{t('settings.ai.qualityDesc')}</div>
                    </div>
                    <div className="set-card-control">
                      <Select
                        value={isPro ? settings.ai_quality || "standard" : "standard"}
                        onChange={chooseQuality}
                        ariaLabel={t('settings.ai.quality')}
                        options={[
                          { value: "standard", label: t('settings.ai.qualityStandard') },
                          { value: "pro", label: t('settings.ai.qualityPro') },
                        ]}
                      />
                    </div>
                  </div>
                ) : (
                  <div className="set-card stack">
                    <div className="set-card-icon"><StarIcon size={14} /></div>
                    <div className="set-card-main">
                      <div className="set-card-name">{t('settings.ai.model')}</div>
                      <div className="set-card-desc">{t('settings.ai.modelDesc', { name: active.name })}</div>
                    </div>
                    <div className="set-card-control">
                      <Select
                        value={selectedModel}
                        onChange={(v) => saveSetting(active.modelKey, v)}
                        ariaLabel={t('settings.ai.model')}
                        options={
                          modelOptions.length === 0
                            ? [{ value: "", label: t('settings.ai.loading') }]
                            : modelOptions
                        }
                      />
                    </div>
                  </div>
                )}
              </>
            );
          })()}

          {tab === "calendars" && (
            <>
              <p className="set-intro">{t('settings.calendars.intro')}</p>
              <div className="set-section-label">{t('settings.calendars.connected')}</div>
              <div className="set-card">
                <div className="set-card-icon cal-logo cal-google"><GoogleCalendarLogo /></div>
                <div className="set-card-main">
                  <div className="set-card-name">{t('settings.calendars.google')}</div>
                  <div className="set-card-desc">
                    {calendarStatus.google ? t('settings.calendars.connectedDot') : t('settings.calendars.googleVia')}
                  </div>
                </div>
                <div className="set-card-control">
                  {calendarStatus.google ? (
                    <button
                      className="btn secondary"
                      onClick={() => api.post("/api/calendar/google/disconnect").then(refreshCalendar)}
                    >
                      {t('settings.calendars.disconnect')}
                    </button>
                  ) : (
                    <button
                      className="btn"
                      onClick={() =>
                        calendarStatus.google_configured ? connectGoogle() : setSetupModal("google")
                      }
                    >
                      {t('settings.calendars.connect')}
                    </button>
                  )}
                </div>
              </div>
              <div className="set-card">
                <div className="set-card-icon cal-logo cal-microsoft"><OutlookCalendarLogo /></div>
                <div className="set-card-main">
                  <div className="set-card-name">{t('settings.calendars.microsoft')}</div>
                  <div className="set-card-desc">
                    {calendarStatus.microsoft ? t('settings.calendars.connectedDot') : t('settings.calendars.msVia')}
                  </div>
                </div>
                <div className="set-card-control">
                  {calendarStatus.microsoft ? (
                    <button
                      className="btn secondary"
                      onClick={() => api.post("/api/calendar/microsoft/disconnect").then(refreshCalendar)}
                    >
                      {t('settings.calendars.disconnect')}
                    </button>
                  ) : (
                    <button
                      className="btn"
                      onClick={() =>
                        calendarStatus.microsoft_configured
                          ? connectMicrosoft()
                          : setSetupModal("microsoft")
                      }
                    >
                      {t('settings.calendars.connect')}
                    </button>
                  )}
                </div>
              </div>
              {msFlow && (
                <div className="section-card" style={{ marginTop: 4 }}>
                  <div className="section-body">
                    <p>
                      {t('settings.calendars.enterCode', { code: msFlow.user_code, uri: msFlow.verification_uri })}
                    </p>
                  </div>
                </div>
              )}
              {!isWin && (
                <div className="set-card">
                  <div className="set-card-icon cal-logo cal-apple"><AppleCalendarLogo /></div>
                  <div className="set-card-main">
                    <div className="set-card-name">{t('settings.calendars.apple')}</div>
                    <div className="set-card-desc">
                      {calendarStatus.apple ? t('settings.calendars.appleEnabled') : t('settings.calendars.appleClick')}
                    </div>
                  </div>
                  <div className="set-card-control">
                    <button
                      className={`btn${calendarStatus.apple ? " secondary" : ""}`}
                      onClick={() =>
                        api
                          .post("/api/calendar/apple/toggle", { enabled: !calendarStatus.apple })
                          .then((resp) => {
                            if (resp?.error === "access_denied") {
                              showToast(
                                t('settings.calendars.accessDenied'),
                                "error"
                              );
                            }
                            refreshCalendar();
                          })
                          .catch((e) => {
                            if (String(e?.message || "").includes("access_denied")) {
                              showToast(
                                t('settings.calendars.accessDenied'),
                                "error"
                              );
                            }
                          })
                      }
                    >
                      {calendarStatus.apple ? t('settings.calendars.disable') : t('settings.calendars.enable')}
                    </button>
                  </div>
                </div>
              )}
              <div className="field-help" style={{ marginTop: 10 }}>
                {t('settings.calendars.pollNote')}
              </div>

              <div className="set-divider" />
              <div className="set-card">
                <div className="set-card-icon"><CalendarClockIcon size={17} /></div>
                <div className="set-card-main">
                  <div className="set-card-name">
                    {t('settings.calendars.autoTranscribe')}
                    {!hasFeature("auto_record") && <span className="pro-badge">{t('upgrade.badge')}</span>}
                  </div>
                  <div className="set-card-desc">{t('settings.calendars.autoTranscribeDesc')}</div>
                </div>
                <div className="set-card-control">
                  <ToggleSwitch
                    checked={(settings.recording_mode || "confirm_30s") === "all"}
                    onChange={(on) => saveSetting("recording_mode", on ? "all" : "confirm_30s")}
                    label={t('settings.calendars.autoTranscribe')}
                  />
                </div>
              </div>
              <div className="set-card">
                <div className="set-card-icon"><ShieldIcon size={17} /></div>
                <div className="set-card-main">
                  <div className="set-card-name">{t('settings.calendars.notify5min')}</div>
                  <div className="set-card-desc">{t('settings.calendars.notify5minDesc')}</div>
                </div>
                <div className="set-card-control">
                  <ToggleSwitch
                    checked={settings.notify_5min !== false}
                    onChange={(on) => saveSetting("notify_5min", on)}
                    label={t('settings.calendars.notify5min')}
                  />
                </div>
              </div>
            </>
          )}

          {tab === "integrations" && (
            <EmailAccountsCard hasFeature={hasFeature} openUpgrade={openUpgrade} showToast={showToast} handleError={handleError} />
          )}
          {tab === "integrations" && (
            <McpAccessCard enabled={settings.mcp_enabled === true} showToast={showToast}
              locked={!hasFeature("mcp")} onToggle={(on) => saveSetting("mcp_enabled", on)} />
          )}
          {tab === "integrations" && (() => {
            const igConnected = (ig) =>
              ig.oauth ? !!calendarStatus.google : ig.fields.every((f) => secrets[f]);
            const activeIg = INTEGRATIONS.find((i) => i.key === openIntegration) || INTEGRATIONS[0];
            const activeConnected = igConnected(activeIg);
            return (
              <div className="tpl-layout">
                <div className="tpl-sidebar">
                  {INTEGRATIONS.map((ig) => (
                    <button
                      key={ig.key}
                      className={`tpl-item${activeIg.key === ig.key ? " active" : ""}`}
                      onClick={() => setOpenIntegration(ig.key)}
                    >
                      <span className="tpl-item-icon ig-logo">{BRAND_LOGOS[ig.key]?.svg}</span>
                      <span className="tpl-item-label">{ig.name}</span>
                      {igConnected(ig) && <span className="ig-dot" />}
                    </button>
                  ))}
                </div>
                <div className="tpl-detail">
                  <div className="ig-detail-header">
                    <span
                      className="ig-detail-badge"
                      style={{
                        ...(BRAND_LOGOS[activeIg.key]?.tint && { background: BRAND_LOGOS[activeIg.key].tint }),
                        color: BRAND_LOGOS[activeIg.key]?.color,
                      }}
                    >
                      {BRAND_LOGOS[activeIg.key]?.svg}
                    </span>
                    <div className="ig-detail-title">{activeIg.name}</div>
                    <span className={`connect-state${activeConnected ? " on" : ""}`}>
                      {activeConnected ? t('settings.integrations.connected') : t('settings.integrations.notConfigured')}
                    </span>
                  </div>
                  <div className="ig-detail-desc">{t('settings.integrations.desc.' + (activeIg.key === "google_drive" ? "googleDrive" : activeIg.key))}</div>
                  {activeIg.oauth ? (
                    activeConnected ? (
                      <div className="field-help">
                        {t('settings.integrations.googleNote')}
                      </div>
                    ) : (
                      <button className="btn" onClick={() => openSettings("calendars")}>
                        {t('settings.integrations.connectGoogle')}
                      </button>
                    )
                  ) : (
                    <IntegrationConfig ig={activeIg} secrets={secrets} onSaved={loadSecrets} />
                  )}
                </div>
              </div>
            );
          })()}

          {tab === "templates" && (
            <>
              {!editingTemplate ? (
                (() => {
                  const activeTpl = templates.find((t) => t.id === tplDetailId) || templates[0];
                  return (
                    <div className="tpl-layout">
                      <div className="tpl-sidebar">
                        {templates.map((t) => {
                          const Icon = templateIcon(t);
                          const active = activeTpl && t.id === activeTpl.id;
                          return (
                            <button
                              key={t.id}
                              className={`tpl-item${active ? " active" : ""}`}
                              onClick={() => setTplDetailId(t.id)}
                            >
                              <span className="tpl-item-icon"><Icon size={14} /></span>
                              <span className="tpl-item-label">{t.name}</span>
                            </button>
                          );
                        })}
                        <div className="tpl-divider" />
                        <button
                          className="tpl-item"
                          onClick={() =>
                            hasFeature("templates")
                              ? setEditingTemplate({
                                  name: "",
                                  description: "",
                                  body: "## Executive Summary\n2-3 sentences.\n\n## My Section\nWhat to capture here. **Bold** key themes.\n\n{SHARED_TAIL}",
                                })
                              : openUpgrade("templates")
                          }
                        >
                          <span className="tpl-item-icon"><StarIcon size={14} /></span>
                          <span className="tpl-item-label">{t('settings.templates.new')}</span>
                          {!hasFeature("templates") && <span className="pro-badge">{t('upgrade.badge')}</span>}
                        </button>
                      </div>
                      <div className="tpl-detail">
                        {activeTpl && (
                          <>
                            <div className="tpl-detail-header">
                              <div className="tpl-detail-title">
                                {activeTpl.name}
                                <span className={`tpl-badge ${activeTpl.builtin ? "builtin" : "custom"}`}>
                                  {activeTpl.builtin ? t('settings.templates.builtin') : t('settings.templates.custom')}
                                </span>
                              </div>
                              {activeTpl.description && (
                                <div className="tpl-detail-desc">{activeTpl.description}</div>
                              )}
                            </div>
                            <div className="tpl-sections-label">{t('settings.templates.sectionsGenerated')}</div>
                            <div className="tpl-chips">
                              {templateSections(activeTpl.body).map((s, i) => (
                                <span className="tpl-chip" key={i}>{s}</span>
                              ))}
                            </div>
                            <button
                              className="tpl-use-btn"
                              onClick={() => {
                                setSelectedTemplate(activeTpl.id);
                                saveSetting("default_template", activeTpl.id);
                                showToast(t('settings.templates.setAsTemplate', { name: activeTpl.name }));
                              }}
                            >
                              {t('settings.templates.use')}
                            </button>
                            {!activeTpl.builtin && (
                              <div className="tpl-detail-actions">
                                <button className="btn secondary" onClick={() => setEditingTemplate(activeTpl)}>
                                  {t('settings.templates.edit')}
                                </button>
                                <button
                                  className="btn secondary"
                                  onClick={() =>
                                    api.delete(`/api/templates/${activeTpl.id}`).then(() => {
                                      setTplDetailId(null);
                                      refreshTemplates();
                                    })
                                  }
                                >
                                  {t('settings.templates.delete')}
                                </button>
                              </div>
                            )}
                          </>
                        )}
                      </div>
                    </div>
                  );
                })()
              ) : (
                <>
                  <div className="field">
                    <label className="field-label">{t('settings.templates.name')}</label>
                    <input
                      className="text-input"
                      value={editingTemplate.name}
                      onChange={(e) => setEditingTemplate({ ...editingTemplate, name: e.target.value })}
                    />
                  </div>
                  <div className="field">
                    <label className="field-label">{t('settings.templates.description')}</label>
                    <input
                      className="text-input"
                      value={editingTemplate.description}
                      onChange={(e) =>
                        setEditingTemplate({ ...editingTemplate, description: e.target.value })
                      }
                    />
                  </div>
                  <div className="field">
                    <label className="field-label">{t('settings.templates.structure')}</label>
                    <textarea
                      className="text-input"
                      style={{ minHeight: 220, resize: "vertical", fontSize: 11.5, lineHeight: 1.55 }}
                      value={editingTemplate.body}
                      onChange={(e) => setEditingTemplate({ ...editingTemplate, body: e.target.value })}
                    />
                    <div className="field-help">
                      {t('settings.templates.structureHint', { token: '{SHARED_TAIL}' })}
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button
                      className="btn"
                      disabled={!editingTemplate.name.trim() || editingTemplate.body.length < 10}
                      onClick={() => {
                        const payload = {
                          name: editingTemplate.name,
                          description: editingTemplate.description,
                          body: editingTemplate.body,
                        };
                        const req = editingTemplate.id
                          ? api.patch(`/api/templates/${editingTemplate.id}`, payload)
                          : api.post("/api/templates", payload);
                        req
                          .then(() => {
                            setEditingTemplate(null);
                            refreshTemplates();
                            showToast(t('settings.templates.saved'));
                          })
                          .catch(handleError);
                      }}
                    >
                      {t('settings.templates.save')}
                    </button>
                    <button className="btn secondary" onClick={() => setEditingTemplate(null)}>
                      {t('settings.templates.cancel')}
                    </button>
                  </div>
                </>
              )}
            </>
          )}

          {tab === "privacy" && (
            <>
              <div className="set-section-label first">{t('settings.privacy.title')}</div>
              <div className="set-card">
                <div className="set-card-icon"><ShieldIcon size={14} /></div>
                <div className="set-card-main">
                  <div className="set-card-name">{t('settings.privacy.coach')}</div>
                  <div className="set-card-desc">{t('settings.privacy.coachDesc')}</div>
                </div>
                <div className="set-card-control">
                  <button
                    className={`btn${settings.coach_enabled !== false ? "" : " secondary"}`}
                    onClick={() => saveSetting("coach_enabled", settings.coach_enabled === false)}
                  >
                    {settings.coach_enabled !== false ? t('settings.recording.on') : t('settings.recording.off')}
                  </button>
                </div>
              </div>
              <div className="set-card stack">
                <div className="set-card-icon icon-redact"><RedactIcon /></div>
                <div className="set-card-main">
                  <div className="set-card-name">{t('settings.privacy.redactedWords')}</div>
                  <div className="set-card-desc">
                    {t('settings.privacy.autoRedacted')}{" "}
                    <span style={{ fontSize: 10, color: "var(--muted)", marginBottom: 4, display: "block" }}>
                      {t('settings.privacy.appearsAs')}
                    </span>
                    {t('settings.privacy.redactNote')}
                  </div>
                </div>
                <div className="set-card-control">
                  <input
                    className="text-input"
                    placeholder={t('settings.privacy.redactPlaceholder')}
                    defaultValue={(settings.redact_words || []).join(", ")}
                    onBlur={(e) =>
                      saveSetting(
                        "redact_words",
                        e.target.value.split(",").map((w) => w.trim()).filter(Boolean).slice(0, 100)
                      )
                    }
                  />
                </div>
              </div>
              <div className="set-card stack">
                <div className="set-card-icon"><BanIcon size={14} /></div>
                <div className="set-card-main">
                  <div className="set-card-name">{t('settings.privacy.neverRecord')}</div>
                  <div className="set-card-desc">
                    {t('settings.privacy.neverRecordDesc')}
                  </div>
                </div>
                <div className="set-card-control">
                  <input
                    className="text-input"
                    placeholder={t('settings.privacy.excludePlaceholder')}
                    defaultValue={(settings.exclude_patterns || []).join(", ")}
                    onBlur={(e) =>
                      saveSetting(
                        "exclude_patterns",
                        e.target.value.split(",").map((w) => w.trim()).filter(Boolean).slice(0, 100)
                      )
                    }
                  />
                </div>
              </div>
              <div className="set-card">
                <div className="set-card-icon"><TrashIcon size={14} /></div>
                <div className="set-card-main">
                  <div className="set-card-name">{t('settings.privacy.autoDelete')}</div>
                  <div className="set-card-desc">{t('settings.privacy.autoDeleteDesc')}</div>
                </div>
                <div className="set-card-control">
                  <Select
                    value={settings.retention_days || 0}
                    onChange={(v) => saveSetting("retention_days", v)}
                    options={[
                      { value: 0, label: t('settings.privacy.retentionNever') },
                      { value: 30, label: t('settings.privacy.d30') },
                      { value: 90, label: t('settings.privacy.d90') },
                      { value: 180, label: t('settings.privacy.d180') },
                      { value: 365, label: t('settings.privacy.y1') },
                    ]}
                  />
                </div>
              </div>
              <div className="field-help">
                {t('settings.privacy.muteNote')}
              </div>
            </>
          )}

          {tab === "export" && (
            <>
              <div className="set-section-label first">{t('settings.export.title')}</div>
              <div className="set-card">
                <div className="set-card-icon"><SpreadsheetIcon size={14} /></div>
                <div className="set-card-main">
                  <div className="set-card-name">{t('settings.export.actionsCsv')}</div>
                  <div className="set-card-desc">{t('settings.export.actionsCsvDesc')}</div>
                </div>
                <div className="set-card-control">
                  <button
                    className="btn secondary"
                    onClick={() =>
                      api.post("/api/export/pack/actions_csv").then(({ path }) => {
                        showToast(t('settings.export.csvExported'));
                        window.jotva?.showInFolder?.(path);
                      }).catch((e) => showToast(e.message, "error"))
                    }
                  >
                    {t('settings.export.export')}
                  </button>
                </div>
              </div>
              <div className="set-card">
                <div className="set-card-icon"><FileTextIcon size={14} /></div>
                <div className="set-card-main">
                  <div className="set-card-name">{t('settings.export.timelinePdf')}</div>
                  <div className="set-card-desc">{t('settings.export.timelinePdfDesc')}</div>
                </div>
                <div className="set-card-control">
                  <button
                    className="btn secondary"
                    onClick={() =>
                      api.post("/api/export/pack/timeline_pdf").then(({ path }) => {
                        showToast(t('settings.export.timelineExported'));
                        window.jotva?.showInFolder?.(path);
                      }).catch((e) => showToast(e.message, "error"))
                    }
                  >
                    {t('settings.export.export')}
                  </button>
                </div>
              </div>

              <div className="set-section-label">{t('settings.export.mobile')}</div>
              <div className="set-card stack">
                <div className="set-card-main">
                  <div className="set-card-name">{t('settings.export.iosSoon')}</div>
                  <div className="set-card-desc">
                    {t('settings.export.mobileBlurb')}
                  </div>
                </div>
                {/* Pairing button removed: the mobile API is unreachable by any
                    phone today (loopback-only bind + desktop-token auth), so
                    the button could only mint tokens that never work. The
                    "coming soon" card above stays as the honest state. */}
              </div>
              {mobileSessions.length > 0 && (
                <div className="set-card stack">
                  <div className="set-card-main">
                    <div className="set-card-name">{t('settings.export.connectedDevices')}</div>
                  </div>
                  <div className="set-card-control" style={{ flexDirection: "column", gap: 6, width: "100%" }}>
                    {mobileSessions.map((s) => (
                      <div key={s.id} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5 }}>
                        <span style={{ flex: 1 }}>{s.device_name || s.device_id}</span>
                        <span style={{ color: "var(--muted)", fontSize: 11 }}>{s.created_at?.slice(0, 10)}</span>
                        {!s.revoked && (
                          <button
                            className="btn secondary"
                            style={{ padding: "2px 8px", fontSize: 11 }}
                            onClick={() =>
                              api
                                .post(`/api/mobile/sessions/${s.id}/revoke`)
                                .then(() => { loadMobileSessions(); showToast(t('settings.export.deviceRevoked')); })
                                .catch((e) => showToast(e.message, "error"))
                            }
                          >
                            {t('settings.export.revoke')}
                          </button>
                        )}
                        {s.revoked && <span style={{ color: "var(--muted)", fontSize: 11 }}>{t('settings.export.revoked')}</span>}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="set-section-label">{t('settings.export.backup')}</div>
              <div className="set-card stack">
                <div className="set-card-icon"><LockIcon size={14} /></div>
                <div className="set-card-main">
                  <div className="set-card-name">{t('settings.export.vault')}</div>
                  <div className="set-card-desc">
                    {t('settings.export.vaultBlurb')}
                  </div>
                </div>
                <div className="set-card-control">
                  <div style={{ display: "flex", gap: 8, width: "100%" }}>
                    <input
                      className="text-input"
                      type="password"
                      placeholder={t('settings.export.vaultPlaceholder')}
                      value={vaultPassword}
                      onChange={(e) => setVaultPassword(e.target.value)}
                    />
                    <button
                      className="btn"
                      disabled={vaultPassword.length < 8 || busy}
                      onClick={() => {
                        setBusy(true);
                        api
                          .post("/api/vault/export", { password: vaultPassword })
                          .then(({ path }) => {
                            setVaultPassword("");
                            showToast(t('settings.export.vaultExported'));
                            window.jotva?.showInFolder?.(path);
                          })
                          .catch((e) => showToast(e.message, "error"))
                          .finally(() => setBusy(false));
                      }}
                    >
                      {busy ? t('settings.export.encrypting') : t('settings.export.exportVault')}
                    </button>
                  </div>
                </div>
              </div>
            </>
          )}

          {tab === "workspace" && (
            <>
              <div className="set-section-label first">{t('settings.workspace.title')}</div>
              {!workspace?.workspace ? (
                <>
                  <div className="set-card stack">
                    <div className="set-card-main">
                      <div className="set-card-name">{t('settings.workspace.create')}</div>
                      <div className="set-card-desc">{t('settings.workspace.createDesc')}</div>
                    </div>
                    <div className="set-card-control" style={{ flexDirection: "column", gap: 6 }}>
                      <input
                        className="text-input"
                        placeholder={t('settings.workspace.namePlaceholder')}
                        value={wsName}
                        onChange={(e) => setWsName(e.target.value)}
                      />
                      <input
                        className="text-input"
                        placeholder={t('settings.workspace.displayNamePlaceholder')}
                        value={wsDisplayName}
                        onChange={(e) => setWsDisplayName(e.target.value)}
                      />
                      <button
                        className="btn"
                        disabled={!wsName.trim() || busy}
                        onClick={() => {
                          setBusy(true);
                          api
                            .post("/api/workspace/create", { name: wsName.trim(), display_name: wsDisplayName.trim() })
                            .then(() => {
                              refreshWorkspace();
                              setWsName("");
                              showToast(t('settings.workspace.created'));
                            })
                            .catch((e) => showToast(e.message, "error"))
                            .finally(() => setBusy(false));
                        }}
                      >
                        {t('settings.workspace.createBtn')}
                      </button>
                    </div>
                  </div>
                  <div className="set-card stack">
                    <div className="set-card-main">
                      <div className="set-card-name">{t('settings.workspace.join')}</div>
                      <div className="set-card-desc">{t('settings.workspace.joinDesc')}</div>
                    </div>
                    <div className="set-card-control" style={{ flexDirection: "column", gap: 6 }}>
                      <input
                        className="text-input"
                        placeholder={t('settings.workspace.invitePlaceholder')}
                        value={wsInviteCode}
                        onChange={(e) => setWsInviteCode(e.target.value.toUpperCase())}
                      />
                      <input
                        className="text-input"
                        placeholder={t('settings.workspace.displayNamePlaceholder')}
                        value={wsDisplayName}
                        onChange={(e) => setWsDisplayName(e.target.value)}
                      />
                      <button
                        className="btn"
                        disabled={wsInviteCode.length < 6 || busy}
                        onClick={() => {
                          setBusy(true);
                          api
                            .post("/api/workspace/join", { invite_code: wsInviteCode, display_name: wsDisplayName.trim() })
                            .then(() => {
                              refreshWorkspace();
                              setWsInviteCode("");
                              showToast(t('settings.workspace.joined'));
                            })
                            .catch((e) => showToast(e.message, "error"))
                            .finally(() => setBusy(false));
                        }}
                      >
                        {t('settings.workspace.joinBtn')}
                      </button>
                    </div>
                  </div>
                </>
              ) : (
                <>
                  <div className="set-card">
                    <div className="set-card-main">
                      <div className="set-card-name">{workspace.workspace.name}</div>
                      <div className="set-card-desc">
                        {t('settings.workspace.inviteCode')} <strong>{workspace.workspace.invite_code}</strong>
                        {" · "}
                        {t('settings.workspace.memberCount', { count: workspace.members?.length ?? 0 })}
                      </div>
                    </div>
                    <div className="set-card-control">
                      <button
                        className="btn secondary"
                        onClick={() => {
                          setBusy(true);
                          api
                            .post("/api/workspace/leave")
                            .then(() => { refreshWorkspace(); showToast(t('settings.workspace.left')); })
                            .catch((e) => showToast(e.message, "error"))
                            .finally(() => setBusy(false));
                        }}
                      >
                        {t('settings.workspace.leave')}
                      </button>
                    </div>
                  </div>
                  {workspace.members && workspace.members.length > 0 && (
                    <div className="set-card stack">
                      <div className="set-card-main">
                        <div className="set-card-name">{t('settings.workspace.members')}</div>
                      </div>
                      <div className="set-card-control" style={{ flexDirection: "column", gap: 4 }}>
                        {workspace.members.map((m, i) => (
                          <div key={i} style={{ fontSize: 12.5 }}>
                            {m.display_name || t('settings.workspace.memberFallback')}{" "}
                            <span style={{ color: "var(--muted)", fontSize: 11 }}>{t('settings.workspace.joinedDate', { date: m.joined_at?.slice(0, 10) })}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  <div className="set-section-label">{t('settings.workspace.syncFolder')}</div>
                  <div className="set-card stack">
                    <div className="set-card-main">
                      <div className="set-card-name">{t('settings.workspace.sharedPath')}</div>
                      <div className="set-card-desc">
                        {t('settings.workspace.syncNote')}
                      </div>
                    </div>
                    <div className="set-card-control" style={{ flexDirection: "column", gap: 6 }}>
                      <input
                        className="text-input"
                        placeholder={t('settings.workspace.syncPlaceholder')}
                        value={wsSharePath}
                        onChange={(e) => setWsSharePath(e.target.value)}
                      />
                      <button
                        className="btn"
                        disabled={!wsSharePath.trim()}
                        onClick={() => {
                          api
                            .post("/api/workspace/share-path", { path: wsSharePath.trim() })
                            .then(() => { refreshWorkspace(); showToast(t('settings.workspace.syncSaved')); })
                            .catch((e) => showToast(e.message, "error"));
                        }}
                      >
                        {t('settings.workspace.savePath')}
                      </button>
                    </div>
                  </div>
                </>
              )}
            </>
          )}

          {tab === "license" && (
            <>
              <div className="set-section-label first">{t('settings.license.title')}</div>
              <div className="set-card plan-card">
                <div className="set-card-icon"><CrownIcon size={14} /></div>
                <div className="set-card-main">
                  <div className="set-card-name">{t('settings.license.currentPlan')}</div>
                </div>
                <div className="set-card-control">
                  <span style={{ color: "var(--accent)", fontWeight: 600 }}>
                    {license?.plan_name || (license?.tier === "pro" ? t('settings.license.planPro') : t('settings.license.planFree'))}
                  </span>
                </div>
                <AiAllowance license={license} />
              </div>
              <div className="set-card">
                <div className="set-card-icon"><RefreshIcon size={14} /></div>
                <div className="set-card-main">
                  <div className="set-card-name">{t('settings.license.manage')}</div>
                  <div className="set-card-desc">{t('settings.license.manageDesc')}</div>
                </div>
                <div className="set-card-control">
                  {license?.tier === "pro" && (
                    <button className="btn secondary" disabled={portalLoading} onClick={openPortal}>
                      {portalLoading ? t('settings.license.opening') : t('settings.license.manage')}
                    </button>
                  )}
                  {license?.tier !== "pro" && (
                    <button className="btn secondary" onClick={() => api.post("/api/license/refresh").then(refreshLicense)}>
                      {t('settings.license.revalidate')}
                    </button>
                  )}
                  {license?.tier !== "pro" && (
                    <button className="btn upgrade-cta" onClick={() => openUpgrade("default")}>
                      {t('settings.license.getPro')}
                    </button>
                  )}
                </div>
              </div>
              {/* DEV ONLY: tier switching for local testing (hidden in production builds) */}
              {import.meta.env.DEV && (
                <div className="dev-testing">
                  <div className="dev-testing-label">
                    <CodeIcon size={11} /> {t('settings.license.devTesting')}
                  </div>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button className="dev-tier-btn" onClick={() => switchTier("free")}>
                      {t('settings.license.switchFree')}
                    </button>
                    <button className="dev-tier-btn" onClick={() => switchTier("pro")}>
                      {t('settings.license.switchPro')}
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
          </div>
        </div>
      </SettingsPanel>
      {setupModal && (
        <div
          className="modal-backdrop"
          style={{ zIndex: 70 }}
          onMouseDown={(e) => e.target === e.currentTarget && setSetupModal(null)}
        >
          <div className="modal" style={{ width: 460 }}>
            <div className="modal-header">
              <div className="modal-title">
                {t('settings.oauth.connectCalendar', { provider: setupModal === "google" ? "Google" : "Microsoft" })}
              </div>
              <button className="icon-btn" onClick={() => setSetupModal(null)}>
                <XIcon size={15} />
              </button>
            </div>
            <div className="modal-body">
              <p style={{ fontSize: 13, lineHeight: 1.65, marginBottom: 12 }}>
                {t('settings.oauth.explain', { provider: setupModal === "google" ? "Google" : "Microsoft" })}
              </p>
              <p style={{ fontSize: 13, lineHeight: 1.65, marginBottom: 12, color: "var(--muted)" }}>
                {t('settings.oauth.setupNote', { provider: setupModal === "google" ? "Google" : "Microsoft" })}
              </p>
              <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
                <button
                  className="btn"
                  onClick={() =>
                    openExternal(
                      setupModal === "google"
                        ? "https://docs.jotva.com/setup/google-calendar"
                        : "https://docs.jotva.com/setup/microsoft-calendar"
                    )
                  }
                >
                  {t('settings.oauth.learnMore')}
                </button>
                <button className="btn secondary" onClick={() => setSetupModal(null)}>
                  {t('settings.oauth.close')}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
