import React, { useEffect, useRef, useState } from "react";
import { useGlassLens } from "../glassLens.js";
import { useTranslation } from "react-i18next";
import { useStore } from "../store.jsx";
import { DOCK_GROUPS } from "../navigation.js";
import { GridIcon, MicIcon, GearIcon, UsersIcon, SlidersIcon, CheckIcon } from "./icons.jsx";

const ICONS = { meetings: GridIcon, record: MicIcon, ai: SlidersIcon, connections: UsersIcon, settings: GearIcon };

export default function Dock() {
  const { t } = useTranslation();
  const { nav, setNav, openSettings, settingsOpen, settingsSection, recording, captureOpen, setCaptureOpen, setSettingsOpen } = useStore();
  const [open, setOpen] = useState(null);
  const root = useRef(null);
  const menu = useRef(null);
  const triggers = useRef({});
  const focusLast = useRef(false);
  const label = (value) => t(`dock.labels.${value}`, { defaultValue: value });
  const isSelected = (group) => settingsOpen ? group.items.some(i => i.section === settingsSection)
    : (recording.active || captureOpen) ? group.id === "record" : group.items.some(i => i.nav === nav);

  // Glass lens glides to the hovered/focused button and rests on the selected one.
  const [hover, setHover] = useState(null);
  const lensTarget = hover || DOCK_GROUPS.find(isSelected)?.id;
  const lens = useGlassLens(root, () => triggers.current[lensTarget], lensTarget);

  useEffect(() => {
    if (!open) return;
    const buttons = menu.current?.querySelectorAll('[role="menuitem"]');
    buttons?.[focusLast.current ? buttons.length - 1 : 0]?.focus();
    const outside = (e) => { if (!root.current?.contains(e.target)) setOpen(null); };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);

  const close = (restore = false) => {
    if (restore) triggers.current[open]?.focus();
    setOpen(null);
  };
  const choose = (item) => {
    close(true);
    if (item.section) openSettings(item.section);
    else {
      setSettingsOpen(false);
      if (item.nav) setNav(item.nav);
      else if (!recording.active) setCaptureOpen(true);
    }
  };
  const menuKey = (e) => {
    const buttons = [...menu.current.querySelectorAll('[role="menuitem"]')];
    const at = buttons.indexOf(document.activeElement);
    const offset = e.key === "ArrowDown" ? 1 : e.key === "ArrowUp" ? -1 : 0;
    if (offset || e.key === "Home" || e.key === "End") {
      e.preventDefault();
      buttons[e.key === "Home" ? 0 : e.key === "End" ? buttons.length - 1 : (at + offset + buttons.length) % buttons.length]?.focus();
    } else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); close(true); }
    else if (e.key === "Tab") { close(true); }
  };

  return <nav className="bottom-dock" aria-label={t("dock.navigation", { defaultValue: "Main navigation" })} data-tour="nav-section" ref={root}
    onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) { setOpen(null); setHover(null); } }}
    onPointerMove={(e) => root.current.style.setProperty("--mx", `${e.clientX - root.current.getBoundingClientRect().left}px`)}
    onPointerLeave={() => setHover(null)}>
    <span {...lens} />
    {DOCK_GROUPS.map(group => {
      const Icon = ICONS[group.id];
      const selected = isSelected(group);
      return <div className="dock-group" key={group.id}>
        {open === group.id && <div className="dock-menu" id={`dock-menu-${group.id}`} role="menu" aria-labelledby={`dock-${group.id}`} ref={menu} onKeyDown={menuKey}>
          <div className="dock-menu-heading" aria-hidden="true">{label(group.label)}</div>
          {group.items.map((item, i) => <button key={item.label} role="menuitem" tabIndex={-1}
            aria-disabled={item.action === "record" && recording.active || undefined}
            onClick={() => { if (!(item.action === "record" && recording.active)) choose(item); }}>
            <span>{label(item.label)}</span>
            {(item.section && settingsOpen && settingsSection === item.section || item.nav === nav) && <CheckIcon size={16} aria-hidden="true" />}
          </button>)}
        </div>}
        <button id={`dock-${group.id}`} className={`dock-button${selected ? " selected" : ""}${open === group.id ? " expanded" : ""}`}
          ref={el => { triggers.current[group.id] = el; }} aria-haspopup="menu" aria-expanded={open === group.id}
          aria-controls={open === group.id ? `dock-menu-${group.id}` : undefined} data-tour={group.id === "record" ? "record-btn" : undefined}
          onPointerEnter={() => setHover(group.id)} onFocus={() => setHover(group.id)}
          onClick={() => { focusLast.current = false; setOpen(open === group.id ? null : group.id); }}
          onKeyDown={e => {
            if (e.key === "ArrowUp" || e.key === "ArrowDown") { e.preventDefault(); focusLast.current = e.key === "ArrowUp"; setOpen(group.id); }
            if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
              e.preventDefault(); const index = DOCK_GROUPS.indexOf(group);
              triggers.current[DOCK_GROUPS[(index + (e.key === "ArrowRight" ? 1 : 4)) % 5].id]?.focus();
            }
          }}>
          <span className="dock-icon"><Icon size={21} aria-hidden="true" />{group.id === "record" && recording.active && <span className="dock-record-dot" />}</span>
          <span>{label(group.label)}</span>
        </button>
      </div>;
    })}
  </nav>;
}
