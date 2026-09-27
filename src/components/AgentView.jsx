// Jotva Agent (Pro): conversations waiting on the user, newest verdicts from the
// email triage. Read-only on the mailbox: "Open" jumps to the message in Gmail
// or Apple Mail; Done / Snooze / Not needed only change Jotva's own list.
import React, { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, openExternal } from "../api.js";
import { useStore } from "../store.jsx";
import { CheckIcon, RefreshIcon, SparkIcon } from "./icons.jsx";

function openLink(thread) {
  const id = thread.last_message_id;
  if (thread.account?.endsWith("@gmail.com") || thread.provider === "gmail" || thread.provider === "google") {
    return `https://mail.google.com/mail/u/${encodeURIComponent(thread.account)}/#search/rfc822msgid%3A${encodeURIComponent(id)}`;
  }
  return `message://%3C${encodeURIComponent(id)}%3E`; // Apple Mail
}

function waited(iso, lang) {
  const hours = Math.max(0, (Date.now() - new Date(iso).getTime()) / 36e5);
  const rtf = new Intl.RelativeTimeFormat(lang, { numeric: "auto" });
  return hours < 24 ? rtf.format(-Math.round(hours), "hour") : rtf.format(-Math.round(hours / 24), "day");
}

export default function AgentView() {
  const { t, i18n } = useTranslation();
  const { hasFeature, openUpgrade, openSettings, emailVersion, handleError, showToast } = useStore();
  const pro = hasFeature("email");
  const [accounts, setAccounts] = useState(null);
  const [threads, setThreads] = useState([]);
  const [syncing, setSyncing] = useState(false);
  const [drafting, setDrafting] = useState(null); // { id, text, busy }

  const load = useCallback(() => {
    api.get("/api/email/accounts").then((r) => setAccounts(r.accounts)).catch(() => setAccounts([]));
    if (pro) api.get("/api/email/waiting").then((r) => setThreads(r.threads)).catch(() => {});
  }, [pro]);
  useEffect(load, [load, emailVersion]);

  const setStatus = (thread, status, snooze_hours) => {
    setThreads((list) => list.filter((x) => x.id !== thread.id));
    api.patch(`/api/email/threads/${encodeURIComponent(thread.id)}`, { status, snooze_hours }).catch(handleError);
  };
  const draftReply = async (thread) => {
    setDrafting({ id: thread.id, text: "", busy: true });
    try {
      const { text } = await api.post(`/api/email/threads/${encodeURIComponent(thread.id)}/draft`);
      setDrafting({ id: thread.id, text, busy: false });
    } catch (e) {
      setDrafting(null);
      handleError(e);
    }
  };
  const finish = async (thread, how) => {
    const text = drafting?.text?.trim();
    if (!text) return;
    if (how === "copy") {
      await navigator.clipboard.writeText(text);
      showToast(t("agent.copied"));
      openExternal(openLink(thread));
      return;
    }
    setDrafting({ ...drafting, busy: true });
    try {
      await api.post(`/api/email/threads/${encodeURIComponent(thread.id)}/${how === "send" ? "send" : "save-draft"}`, { text });
      showToast(t(how === "send" ? "agent.sent" : "agent.savedDraft"));
      setDrafting(null);
      if (how === "send") setThreads((list) => list.filter((x) => x.id !== thread.id));
    } catch (e) {
      setDrafting({ ...drafting, busy: false });
      handleError(e);
    }
  };
  const syncNow = () => {
    setSyncing(true);
    api.post("/api/email/sync").then(() => showToast(t("agent.checking"))).catch(handleError)
      .finally(() => setTimeout(() => setSyncing(false), 4000));
  };

  return (
    <div className="view agent-view">
      <div className="view-inner">
        <div className="agent-head">
          <div>
            <div className="view-title">{t("agent.title")}</div>
            <div className="view-sub">{t("agent.sub")}</div>
          </div>
          {pro && accounts?.length > 0 && (
            <button className="btn secondary" onClick={syncNow} disabled={syncing}>
              <RefreshIcon size={14} /> {t(syncing ? "agent.checkingShort" : "agent.checkNow")}
            </button>
          )}
        </div>

        {!pro ? (
          <div className="agent-empty">
            <SparkIcon size={22} />
            <div className="empty-title">{t("agent.upsellTitle")}</div>
            <div className="empty-sub">{t("agent.upsellBody")}</div>
            <button className="btn upgrade-cta" onClick={() => openUpgrade("email")}>{t("upgrade.cta")}</button>
          </div>
        ) : accounts && !accounts.length ? (
          <div className="agent-empty">
            <SparkIcon size={22} />
            <div className="empty-title">{t("agent.connectTitle")}</div>
            <div className="empty-sub">{t("agent.connectBody")}</div>
            <button className="btn upgrade-cta" onClick={() => openSettings("integrations")}>{t("agent.connect")}</button>
          </div>
        ) : (
          <>
            <div className="view-section-title">
              {t("agent.waiting")} <span className="agent-count">{threads.length}</span>
            </div>
            {!threads.length ? (
              <div className="agent-clear"><CheckIcon size={16} /> {t("agent.allClear")}</div>
            ) : (
              <ul className="agent-list">
                {threads.map((th) => (
                  <li key={th.id} className={`agent-item urgency-${th.urgency}`}>
                    <span className="agent-avatar" aria-hidden="true">
                      {(th.counterpart_name || th.counterpart_email || "?").trim()[0].toUpperCase()}
                    </span>
                    <div className="agent-main">
                      <div className="agent-line">
                        <strong>{th.counterpart_name || th.counterpart_email}</strong>
                        {th.urgency === "high" && <span className="agent-urgent">{t("agent.urgent")}</span>}
                        <span className="agent-age">{waited(th.last_at, i18n.language)}</span>
                      </div>
                      <div className="agent-subject">{th.subject || t("agent.noSubject")}</div>
                      {th.reason && <div className="agent-reason">{th.reason}</div>}
                      {drafting?.id === th.id && (
                        <div className="agent-draft">
                          {drafting.busy && !drafting.text ? (
                            <div className="agent-draft-busy"><span className="live-dot" /> {t("agent.writing")}</div>
                          ) : (
                            <>
                              <textarea aria-label={t("agent.draftLabel")} value={drafting.text} rows={6}
                                onChange={(e) => setDrafting({ ...drafting, text: e.target.value })} />
                              <div className="agent-actions">
                                {th.provider === "google" ? (
                                  <>
                                    <button className="btn compact" disabled={drafting.busy} onClick={() => finish(th, "draft")}>{t("agent.saveDraft")}</button>
                                    <button className="btn compact secondary" disabled={drafting.busy} onClick={() => finish(th, "send")}>{t("agent.send")}</button>
                                  </>
                                ) : (
                                  <button className="btn compact" onClick={() => finish(th, "copy")}>{t("agent.copyOpen")}</button>
                                )}
                                <button className="btn compact secondary" onClick={() => setDrafting(null)}>{t("common.cancel")}</button>
                              </div>
                              <div className="agent-draft-note">{t("agent.draftNote")}</div>
                            </>
                          )}
                        </div>
                      )}
                      <div className="agent-actions">
                        <button className="btn compact" onClick={() => draftReply(th)} disabled={drafting?.id === th.id}>{t("agent.draft")}</button>
                        <button className="btn compact secondary" onClick={() => openExternal(openLink(th))}>{t("agent.open")}</button>
                        <button className="btn compact secondary" onClick={() => setStatus(th, "done")}>{t("agent.done")}</button>
                        <button className="btn compact secondary" onClick={() => setStatus(th, "snoozed", 24)}>{t("agent.snooze")}</button>
                        <button className="btn compact secondary" onClick={() => setStatus(th, "dismissed")}>{t("agent.notNeeded")}</button>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            {accounts?.some((a) => a.last_error) && (
              <div className="agent-error" role="status">
                {t("agent.syncError")} <button className="btn compact secondary" onClick={() => openSettings("integrations")}>{t("agent.fix")}</button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
