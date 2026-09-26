import React, { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useLogo, useStore } from "../store.jsx";
import { api } from "../api.js";
import { CalendarIcon, ChevronDownIcon } from "./icons.jsx";

export default function AppHeader() {
  const { t } = useTranslation();
  const { upcoming, activeCall, recording, startRecording, dismissActiveCall, openSettings, license, avatar } = useStore();
  const logo = useLogo();
  const [name, setName] = useState("");
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    api.get("/api/settings/user-name").then(r => setName(r.user_name || "")).catch(() => {});
    const timer = setInterval(() => setNow(Date.now()), 15000);
    return () => clearInterval(timer);
  }, []);
  const next = upcoming.filter(e => !e.cancelled && !e.recorded_meeting_id && e.join_url)
    .map(e => ({ ...e, minutes: Math.round((new Date(e.start) - now) / 60000) }))
    .filter(e => e.minutes >= 0 && e.minutes <= 60).sort((a, b) => a.minutes - b.minutes)[0];
  const initials = (name || "A").split(/\s+/).map(s => s[0]).join("").slice(0, 2).toUpperCase();
  return <header className="app-header">
    <div className="app-brand"><img src={logo} alt="" /><span className="brand-wordmark">Jotva</span></div>
    <div className="header-status">
      {activeCall && !recording.active ? <div className="header-call">
        <span>{t("sidebar.call.prompt", { app: activeCall.app })}</span>
        <button className="btn" onClick={() => { dismissActiveCall(activeCall.app); startRecording({ title: t("sidebar.call.title", { app: activeCall.app }) }); }}>{t("sidebar.call.record")}</button>
        <button className="btn secondary" onClick={() => dismissActiveCall(activeCall.app)}>{t("sidebar.call.dismiss")}</button>
      </div> : next ? <span className="header-upcoming" title={next.title}>
        <CalendarIcon size={16} aria-hidden="true" /><span>{next.title}</span><strong>{next.minutes} {t("sidebar.autoRecord.min")}</strong>
      </span> : null}
    </div>
    <button className="header-account" onClick={() => openSettings("license")} aria-label={t("dock.account", { defaultValue: "Account and subscription" })}>
      <span className="avatar">{avatar ? <img src={avatar} alt="" /> : initials}</span><span>{license?.tier === "pro" ? "Pro" : t("sidebar.account.upgrade")}</span><ChevronDownIcon size={14} aria-hidden="true" />
    </button>
  </header>;
}
