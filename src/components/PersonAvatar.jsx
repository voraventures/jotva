// A person's circle (speaker, action owner, attendee, email sender): their photo if the user
// added one, otherwise the initials passed as children. Editable circles open a small menu to
// add, change or remove the photo; photos stay on this Mac (see /api/people/photos).
import React, { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { imageFileToAvatar, personKey } from "../avatar.js";
import { useStore } from "../store.jsx";

export default function PersonAvatar({ name, email, className, style, children, editable = false }) {
  const { t } = useTranslation();
  const { peoplePhotos, setPersonPhoto, showToast } = useStore();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const boxRef = useRef(null);
  const fileRef = useRef(null);
  const names = [name, email].filter(Boolean);
  const photo = names.map((n) => peoplePhotos?.[personKey(n)]).find(Boolean);

  useEffect(() => {
    if (!open) return undefined;
    const close = (e) => { if (!boxRef.current?.contains(e.target)) setOpen(false); };
    const esc = (e) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", esc); };
  }, [open]);

  const face = (
    <span className={`${className || ""}${photo ? " has-photo" : ""}`} style={photo ? { ...style, background: "none" } : style}
      aria-hidden={editable ? undefined : "true"}>
      {photo ? <img className="person-photo" src={photo} alt="" draggable="false" /> : children}
    </span>
  );
  if (!editable || !setPersonPhoto || !names.length) return face;

  const choose = async (file) => {
    if (!file) return;
    setOpen(false); setBusy(true);
    try {
      await setPersonPhoto(names, await imageFileToAvatar(file));
      showToast(t("people.saved", { name: name || email }));
    } catch (e) {
      showToast(e.message === "invalid-image" ? t("settings.general.photoInvalid") : e.message, "error");
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };
  const remove = async () => {
    setOpen(false);
    try { await setPersonPhoto(names, null); showToast(t("people.removed")); }
    catch (e) { showToast(e.message, "error"); }
  };

  return (
    <span className="person-avatar-wrap" ref={boxRef} onClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.stopPropagation()}>
      <button type="button" className="person-avatar-btn" aria-haspopup="menu" aria-expanded={open} disabled={busy}
        aria-label={t(photo ? "people.changePhotoOf" : "people.addPhotoOf", { name: name || email })}
        title={t(photo ? "people.changePhotoOf" : "people.addPhotoOf", { name: name || email })}
        onClick={() => setOpen((v) => !v)}>
        {face}
      </button>
      {open && (
        <div className="speaker-picker person-menu" role="menu">
          <div className="speaker-picker-title">{name || email}</div>
          <button type="button" role="menuitem" className="menu-item" onClick={() => fileRef.current?.click()}>
            {t(photo ? "people.changePhoto" : "people.addPhoto")}
          </button>
          {photo && (
            <button type="button" role="menuitem" className="menu-item" onClick={remove}>{t("people.removePhoto")}</button>
          )}
        </div>
      )}
      <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp,image/gif" hidden
        onChange={(e) => choose(e.target.files?.[0])} />
    </span>
  );
}
