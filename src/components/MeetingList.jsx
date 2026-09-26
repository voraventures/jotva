import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useGlassLens } from "../glassLens.js";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { api } from "../api.js";
import { useStore } from "../store.jsx";
import { calendarDate, eligibleUpcoming, groupRecordings, localDayKey, meetingDuration, scheduledTime } from "../meetingCards.js";
import { DotsIcon, MicIcon, SearchIcon } from "./icons.jsx";
import { Confirm } from "./ui.jsx";

function MeetingOptions({ target, onClose, onDelete }) {
  const { t } = useTranslation();
  const ref = useRef(null);
  const [position, setPosition] = useState({ top: 0, left: 0 });
  useLayoutEffect(() => {
    const rect = target.trigger.getBoundingClientRect();
    const menu = ref.current.getBoundingClientRect();
    setPosition({
      left: Math.max(8, Math.min(rect.right - menu.width, window.innerWidth - menu.width - 8)),
      top: rect.bottom + menu.height + 8 > window.innerHeight ? Math.max(8, rect.top - menu.height - 6) : rect.bottom + 6,
    });
    ref.current.querySelector("button").focus();
  }, [target]);
  useEffect(() => {
    const outside = e => {
      if (!ref.current?.contains(e.target) && !target.trigger.contains(e.target)) onClose(false);
    };
    const reposition = () => onClose(true);
    document.addEventListener("pointerdown", outside);
    // A scroll would detach the menu from its card; dismiss without hiding controls.
    document.addEventListener("scroll", reposition, true);
    window.addEventListener("resize", reposition);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("scroll", reposition, true);
      window.removeEventListener("resize", reposition);
    };
  }, [target, onClose]);
  return createPortal(
    <div ref={ref} id="meeting-options" className="meeting-options-menu" role="menu" aria-label={t("list.menu.options")}
      style={position} onKeyDown={e => {
        if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); onClose(true); }
        if (["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) { e.preventDefault(); ref.current.querySelector("button").focus(); }
        if (e.key === "Tab") { e.preventDefault(); onClose(true); }
      }}>
      <button role="menuitem" onClick={() => onDelete(target)}>{t("list.menu.delete")}</button>
    </div>, document.body
  );
}

function MeetingCard({ meeting, selected, onSelect, progress, showDate, onOptions, menuId }) {
  const { t, i18n } = useTranslation();
  const ref = useRef(null);
  useEffect(() => {
    if (!selected || !ref.current) return;
    const list = ref.current.closest(".meeting-card-list");
    const reveal = () => {
      const card = ref.current.getBoundingClientRect(), bounds = list.getBoundingClientRect();
      if (card.top < bounds.top) list.scrollTop += card.top - bounds.top - 8;
      else if (card.bottom > bounds.bottom) list.scrollTop += card.bottom - bounds.bottom + 8;
    };
    reveal();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(reveal);
    observer.observe(list);
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, [selected]);
  const stage = progress[meeting.id]?.stage || meeting.status;
  const status = stage === "recording" ? t("list.cards.recording")
    : ["transcribing", "generating", "processing"].includes(stage) ? t("list.cards.processing")
      : ["error", "failed"].includes(stage) ? t("list.cards.failed") : "";
  const metadata = [scheduledTime(meeting.started_at, i18n.language, showDate), meetingDuration(meeting, i18n.language)].filter(Boolean).join(" · ");
  return (
    <article ref={ref} data-meeting-id={meeting.id} className={`meeting-card${selected ? " is-selected" : ""}`}>
      <button className="meeting-card-main" aria-label={meeting.title} aria-current={selected ? "true" : undefined}
        title={meeting.title} onClick={() => onSelect(meeting.id)}>
        <span className="meeting-card-title">{meeting.title}</span>
        {metadata && <span className="meeting-card-meta">{metadata}</span>}
        {(status || !!meeting.is_demo) && <span className="meeting-card-details">
          {status && <span className={`meeting-card-status${["error", "failed"].includes(stage) ? " is-error" : ""}`} role="status">{status}</span>}
          {!!meeting.is_demo && <span className="meeting-sample">{t("list.demoBadge")}</span>}
        </span>}
      </button>
      <button className="meeting-card-overflow" aria-label={`${t("list.menu.options")} — ${meeting.title}`}
        aria-haspopup="menu" aria-expanded={menuId === meeting.id} aria-controls={menuId === meeting.id ? "meeting-options" : undefined}
        onClick={e => onOptions(meeting, e.currentTarget)}
        onKeyDown={e => { if (["ArrowDown", "ArrowUp"].includes(e.key)) { e.preventDefault(); onOptions(meeting, e.currentTarget); } }}>
        <DotsIcon size={16} />
      </button>
    </article>
  );
}

function UpcomingCard({ event, featured, now }) {
  const { t, i18n } = useTranslation();
  return <article className={`upcoming-card${featured ? " is-featured" : ""}`}>
    {featured && <h3 className="up-next-label">{t("list.cards.upNext")}</h3>}
    <div className="meeting-card-title" title={event.title}>{event.title}</div>
    <div className="meeting-card-meta">{scheduledTime(event.start, i18n.language, localDayKey(event.start) !== localDayKey(now))}</div>
  </article>;
}

export default function MeetingList({ children }) {
  const { t, i18n } = useTranslation();
  const { meetings, selectedId, selectMeeting, progress, startRecording, recording, deleteMeeting, upcoming } = useStore();
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [menuTarget, setMenuTarget] = useState(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState(null);
  const [now, setNow] = useState(() => new Date());
  const searchRef = useRef(null);
  const listRef = useRef(null);
  const [listHover, setListHover] = useState(null);
  const lensId = listHover ?? selectedId;
  const listLens = useGlassLens(listRef,
    () => lensId == null ? null : listRef.current?.querySelector(`.meeting-card[data-meeting-id="${String(lensId).replace(/"/g, "")}"]`),
    `${lensId}:${meetings.length}:${query}:${results?.length}`);
  // Frost a day heading only while its section scrolls under it (see .is-stuck in jotva-theme.css).
  useEffect(() => {
    const list = listRef.current;
    if (!list) return undefined;
    let frame = 0;
    const update = () => {
      frame = 0;
      const top = list.getBoundingClientRect().top;
      list.querySelectorAll(".meeting-day-group").forEach((group) => {
        group.querySelector("h3")?.classList.toggle("is-stuck", group.getBoundingClientRect().top < top - 0.5);
      });
    };
    const onScroll = () => { if (!frame) frame = requestAnimationFrame(update); };
    list.addEventListener("scroll", onScroll, { passive: true });
    update();
    return () => { list.removeEventListener("scroll", onScroll); cancelAnimationFrame(frame); };
  }, []);
  const hoverCard = (e) => { const id = e.target.closest?.(".meeting-card")?.dataset.meetingId; if (id) setListHover(id); };

  useEffect(() => {
    const refresh = () => setNow(new Date());
    const timer = window.setInterval(refresh, 60000);
    window.addEventListener("focus", refresh);
    return () => { window.clearInterval(timer); window.removeEventListener("focus", refresh); };
  }, []);
  useEffect(() => {
    let active = true;
    setResults(null);
    if (!query.trim()) return undefined;
    const timer = setTimeout(() => {
      api.get(`/api/meetings/search?q=${encodeURIComponent(query.trim())}`)
        .then(data => { if (active) setResults(data); })
        .catch(() => { if (active) setResults([]); });
    }, 250);
    return () => { active = false; clearTimeout(timer); };
  }, [query]);
  const { today, older } = useMemo(() => groupRecordings(meetings, now), [meetings, now]);
  const upcomingEvents = useMemo(() => eligibleUpcoming(upcoming, now), [upcoming, now]);
  // Search is a snapshot; the library remains authoritative during delete/Undo.
  const libraryById = useMemo(() => new Map(meetings.map(m => [m.id, m])), [meetings]);
  const visibleResults = results?.filter(m => libraryById.has(m.id)).map(m => libraryById.get(m.id));
  const searching = query.trim().length > 0;
  const closeMenu = (restore = false) => {
    if (restore) menuTarget?.trigger.focus({ preventScroll: true });
    setMenuTarget(null);
  };
  const renderMeeting = m => <MeetingCard key={m.id} meeting={m} selected={selectedId === m.id}
    onSelect={id => { setMenuTarget(null); selectMeeting(id); }} progress={progress} showDate={searching}
    menuId={menuTarget?.meeting.id} onOptions={(meeting, trigger) => setMenuTarget(current => current?.meeting.id === meeting.id ? null : { meeting, trigger })} />;
  const dismissDelete = () => {
    deleteTarget?.trigger.focus({ preventScroll: true });
    setDeleteTarget(null);
  };

  return (
    <div className="list-panel" data-tour="meeting-list">
      <div className="list-top">
        <div className="meeting-day-header">
          <h2>{t(searching ? "list.cards.searchResults" : "list.scopeToday")}</h2>
          {!searching && <p>{calendarDate(now, i18n.language, { weekday: "long", year: undefined })}</p>}
        </div>
        <div className="list-search">
          <SearchIcon size={15} />
          <input ref={searchRef} aria-label={t("list.searchPlaceholder")} placeholder={t("list.searchPlaceholder")}
            value={query} onChange={e => { setMenuTarget(null); setQuery(e.target.value); }} spellCheck={false} />
        </div>
      </div>
      <div className="list-scroll meeting-card-list" ref={listRef} onPointerOver={hoverCard} onFocus={hoverCard}
        onPointerLeave={() => setListHover(null)} onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) setListHover(null); }}>
        <span {...listLens} />
        {searching ? <>
          {results === null && <div className="list-no-match" role="status">{t("common.loading")}</div>}
          {visibleResults?.length === 0 && <div className="list-no-match">{t("list.noMatch", { query })}</div>}
          {visibleResults?.map(renderMeeting)}
        </> : <>
          {upcomingEvents[0] && <UpcomingCard event={upcomingEvents[0]} featured now={now} />}
          {upcomingEvents.length > 1 && <section className="meeting-day-group" aria-label={t("list.group.upcoming")}>
            <h3>{t("list.group.upcoming")}</h3>
            {upcomingEvents.slice(1).map(e => <UpcomingCard key={e.id} event={e} now={now} />)}
          </section>}
          <section className="meeting-day-group" aria-label={t("list.cards.recordedToday")}>
            <h3>{t("list.cards.recordedToday")}</h3>
            {today.length ? today.map(renderMeeting) : <p className="no-recordings-today">{t("list.cards.noRecordingsToday")}</p>}
          </section>
          {older.map(group => {
            const label = group.kind === "yesterday" ? t("list.cards.yesterday") : group.kind === "unknown" ? t("list.cards.unknownDate") : calendarDate(group.date, i18n.language);
            return <section className="meeting-day-group" key={group.key} aria-label={label}>
              <h3>{label}</h3>{group.meetings.map(renderMeeting)}
            </section>;
          })}
          {meetings.length === 0 && upcomingEvents.length === 0 && <div className="empty-state">
            <div className="empty-title">{t("list.empty.allHead")}</div>
            <div className="empty-sub">{t("list.empty.allSub")}</div>
            {!recording.active && <button className="empty-cta" onClick={() => startRecording()}>
              <MicIcon size={14} /> {t("list.startRecording")}
            </button>}
          </div>}
        </>}
      </div>
      {menuTarget && <MeetingOptions target={menuTarget} onClose={closeMenu} onDelete={target => { setMenuTarget(null); setDeleteTarget(target); }} />}
      {deleteTarget && <Confirm title={t("list.deleteTitle")} body={t("list.deleteBody", { title: deleteTarget.meeting.title })}
        confirmLabel={t("common.delete")} danger onConfirm={() => {
          deleteMeeting(deleteTarget.meeting.id);
          setDeleteTarget(null);
          searchRef.current?.focus({ preventScroll: true });
        }} onCancel={dismissDelete} />}
      {children}
    </div>
  );
}
