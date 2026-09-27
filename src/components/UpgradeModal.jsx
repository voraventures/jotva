// Upgrade prompt for the freemium plan. Opened with openUpgrade(feature) from the
// store whenever a free user reaches for a Pro feature or runs out of the month's
// AI notes; the headline speaks to what they just tried to do.
import React, { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { useLogo, useStore } from "../store.jsx";
import { CheckIcon } from "./icons.jsx";

const PERKS = ["unlimited_notes", "live_notes", "ask_all", "auto_record", "higher_quality", "followup", "mcp"];

export default function UpgradeModal() {
  const { t, i18n } = useTranslation();
  const { upgradeFeature, closeUpgrade, startCheckout, license, showToast } = useStore();
  const logo = useLogo();
  const [busy, setBusy] = useState(false);
  const upgradeRef = useRef(null);

  useEffect(() => {
    if (!upgradeFeature) return undefined;
    upgradeRef.current?.focus();
    const onKey = (e) => e.key === "Escape" && closeUpgrade();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [upgradeFeature, closeUpgrade]);

  if (!upgradeFeature) return null;
  const feature = t(`upgrade.feature.${upgradeFeature}.title`, { defaultValue: "" }) ? upgradeFeature : "default";
  const resets = license?.ai_notes_resets_on
    ? new Intl.DateTimeFormat(i18n.language, { month: "long", day: "numeric" }).format(new Date(`${license.ai_notes_resets_on}T00:00:00`))
    : "";

  const upgrade = async () => {
    setBusy(true);
    try {
      await startCheckout();
      closeUpgrade();
    } catch (e) {
      showToast(e.message || t("settings.toast.checkoutFailed"), "error");
    } finally {
      setBusy(false);
    }
  };

  return createPortal(
    <div className="modal-backdrop upgrade-backdrop" onMouseDown={(e) => e.target === e.currentTarget && closeUpgrade()}>
      <div className="upgrade-card" role="dialog" aria-modal="true" aria-labelledby="upgrade-title">
        <img className="upgrade-logo" src={logo} alt="" />
        <span className="upgrade-eyebrow">{t("upgrade.eyebrow")}</span>
        <h2 id="upgrade-title" className="upgrade-title">{t(`upgrade.feature.${feature}.title`)}</h2>
        <p className="upgrade-sub">
          {t(`upgrade.feature.${feature}.body`, { limit: license?.ai_notes_limit ?? 10, date: resets })}
        </p>
        <ul className="upgrade-perks">
          {PERKS.map((p) => (
            <li key={p} className={p === upgradeFeature ? "is-current" : ""}>
              <CheckIcon size={14} aria-hidden="true" />
              {t(`upgrade.perk.${p}`)}
            </li>
          ))}
        </ul>
        <div className="upgrade-actions">
          <button className="btn secondary" onClick={closeUpgrade}>{t("upgrade.notNow")}</button>
          <button ref={upgradeRef} className="btn upgrade-cta" disabled={busy} onClick={upgrade}>
            {busy ? t("settings.license.starting") : t("upgrade.cta")}
          </button>
        </div>
        <p className="upgrade-foot">{t("upgrade.foot")}</p>
      </div>
    </div>,
    document.body
  );
}
