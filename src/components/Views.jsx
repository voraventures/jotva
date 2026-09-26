// Secondary destinations: Today, Search, Meeting Zero, Digest.
// Each is a single calm page — no dashboards, no tiles (HIG 9).
import React, { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api.js";
import { useStore, useLogo } from "../store.jsx";
import Markdown from "./Markdown.jsx";
import { SearchIcon } from "./icons.jsx";

function timeOfDay(iso) {
  if (!iso) return "";
  const d = iso.length === 10 ? new Date(iso + "T00:00:00") : new Date(iso);
  if (isNaN(d)) return "";
  return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function isToday(iso) {
  if (!iso) return false;
  const d = new Date(iso.length === 10 ? iso + "T00:00:00" : iso);
  const n = new Date();
  return (
    d.getFullYear() === n.getFullYear() &&
    d.getMonth() === n.getMonth() &&
    d.getDate() === n.getDate()
  );
}

/* ---------- Today ---------- */
export function TodayView() {
  const { t } = useTranslation();
  const { upcoming, meetings, setNav, selectMeeting, startRecording, recording } = useStore();
  const todaysEvents = upcoming.filter((e) => !e.cancelled && isToday(e.start));
  const todaysMeetings = meetings.filter((m) => isToday(m.started_at));

  const open = (id) => {
    setNav("meetings");
    selectMeeting(id);
  };

  const dateLabel = new Date().toLocaleDateString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
  });

  return (
    <div className="view">
      <div className="view-inner">
        <div className="view-title">{t("today.title")}</div>
        <div className="view-sub">{dateLabel}</div>

        {todaysEvents.length === 0 && todaysMeetings.length === 0 && (
          <div className="empty-state" style={{ height: "auto", padding: "80px 0" }}>
            <div className="empty-title">{t("today.emptyHead")}</div>
            <div className="empty-sub">{t("today.emptySub")}</div>
          </div>
        )}

        {todaysEvents.length > 0 && (
          <>
            <div className="view-section-title">{t("today.onCalendar")}</div>
            {todaysEvents.map((e) => (
              <div className="event-row" key={e.id}>
                <span className="event-time">{timeOfDay(e.start)}</span>
                <span className="event-title">{e.title}</span>
                {e.attendees?.length > 0 && (
                  <span className="event-meta">
                    {t("today.attendeeCount", { count: e.attendees.length })}
                  </span>
                )}
                {e.recorded_meeting_id ? (
                  <button className="event-action" onClick={() => open(e.recorded_meeting_id)}>
                    {t("today.openNotes")}
                  </button>
                ) : (
                  !recording.active && (
                    <button
                      className="event-action"
                      onClick={() => startRecording({ title: e.title, calendarEventId: e.id })}
                    >
                      {t("today.record")}
                    </button>
                  )
                )}
              </div>
            ))}
          </>
        )}

        {todaysMeetings.length > 0 && (
          <>
            <div className="view-section-title">{t("today.captured")}</div>
            {todaysMeetings.map((m) => (
              <button className="event-row" key={m.id} onClick={() => open(m.id)}>
                <span className="event-time">{timeOfDay(m.started_at)}</span>
                <span className="event-title">{m.title}</span>
                {(m.open_actions ?? 0) > 0 && (
                  <span className="event-meta">
                    {t("today.openActions", { count: m.open_actions })}
                  </span>
                )}
              </button>
            ))}
          </>
        )}
      </div>
    </div>
  );
}

/* ---------- Search ---------- */
export function SearchView() {
  const { t } = useTranslation();
  const { setNav, selectMeeting, hasFeature, openUpgrade, handleError } = useStore();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState(null);
  const [askResults, setAskResults] = useState(null);
  const [asking, setAsking] = useState(false);

  useEffect(() => {
    setAskResults(null);
    if (!query.trim()) {
      setResults(null);
      return;
    }
    const tmr = setTimeout(() => {
      api
        .get(`/api/meetings/search?q=${encodeURIComponent(query.trim())}`)
        .then(setResults)
        .catch(() => setResults([]));
    }, 250);
    return () => clearTimeout(tmr);
  }, [query]);

  const ask = () => {
    const q = query.trim();
    if (q.length < 3 || asking) return;
    if (!hasFeature("ask_all")) return openUpgrade("ask_all");
    setAsking(true);
    setAskResults(null);
    api
      .post("/api/search/ask", { query: q })
      .then((r) => setAskResults(r.results))
      .catch((e) => {
        if (e?.status === 402) handleError(e);
        setAskResults([]);
      })
      .finally(() => setAsking(false));
  };

  const open = (id) => {
    setNav("meetings");
    selectMeeting(id);
  };

  return (
    <div className="view">
      <div className="view-inner">
        <div className="view-title">{t("search.title")}</div>
        <div className="view-sub">{t("search.sub")}</div>
        <div className="search-hero">
          <div className="list-search">
            <SearchIcon size={16} />
            <input
              autoFocus
              placeholder={t("search.placeholder")}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && ask()}
              spellCheck={false}
            />
          </div>
        </div>

        {asking && (
          <div className="ask-thinking" aria-label={t("ask.thinking")}>
            <span />
            <span />
            <span />
          </div>
        )}
        {askResults && (
          <>
            <div className="ask-kicker">
              {askResults.length ? t("search.fromMeetings") : t("search.noAnswer")}
            </div>
            {askResults.map((r, i) => (
              <button key={i} className="ask-result" onClick={() => open(r.meeting_id)}>
                {r.answer && <div className="ask-answer">{r.answer}</div>}
                <div className="ask-excerpt">"{r.excerpt}"</div>
                <div className="intel-sub">
                  {r.title} · {new Date(r.date).toLocaleDateString()}
                </div>
              </button>
            ))}
          </>
        )}

        {results && (
          <>
            <div className="ask-kicker">{t("search.matches", { count: results.length })}</div>
            {results.length === 0 && !askResults && (
              <div className="list-no-match">{t("list.noMatch", { query })}</div>
            )}
            {results.map((m) => (
              <button className="event-row" key={m.id} onClick={() => open(m.id)}>
                <span className="event-time">
                  {new Date(m.started_at).toLocaleDateString([], { month: "short", day: "numeric" })}
                </span>
                <span className="event-title">{m.title}</span>
              </button>
            ))}
            {results.length > 0 && query.trim().length >= 3 && !askResults && !asking && (
              <button className="empty-cta" style={{ marginTop: 20 }} onClick={ask}>
                {t("search.askCta", { query: query.trim() })}
                {!hasFeature("ask_all") && <span className="pro-badge">{t("upgrade.badge")}</span>}
              </button>
            )}
          </>
        )}

        {!results && !askResults && !asking && (
          <div className="empty-state" style={{ height: "auto", padding: "60px 0" }}>
            <div className="empty-sub">{t("search.hint")}</div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ---------- Meeting Zero (pre-meeting preparation) ---------- */
export function MeetingZeroView() {
  const { t } = useTranslation();
  const { upcoming, setNav, selectMeeting } = useStore();
  const next = upcoming.find((e) => !e.cancelled && !e.recorded_meeting_id);
  const [brief, setBriefData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setBriefData(null);
    if (!next?.id) return;
    setLoading(true);
    api
      .get(`/api/calendar/brief/${encodeURIComponent(next.id)}`)
      .then(setBriefData)
      .catch(() => setBriefData(null))
      .finally(() => setLoading(false));
  }, [next?.id]);

  const open = (id) => {
    setNav("meetings");
    selectMeeting(id);
  };

  return (
    <div className="view">
      <div className="view-inner">
        <div className="view-title">{t("zero.title")}</div>
        <div className="view-sub">{t("zero.sub")}</div>

        {!next && (
          <div className="empty-state" style={{ height: "auto", padding: "80px 0" }}>
            <div className="empty-title">{t("zero.emptyHead")}</div>
            <div className="empty-sub">{t("zero.emptySub")}</div>
          </div>
        )}

        {next && (
          <>
            <div className="surface summary">
              <div className="surface-title">{next.title}</div>
              <div className="section-body">
                <p>
                  {new Date(next.start).toLocaleString([], {
                    weekday: "long",
                    month: "short",
                    day: "numeric",
                    hour: "numeric",
                    minute: "2-digit",
                  })}
                  {next.attendees?.length
                    ? ` · ${t("today.attendeeCount", { count: next.attendees.length })}`
                    : ""}
                </p>
              </div>
            </div>
            {loading && (
              <div className="skeleton-rows" aria-hidden="true">
                {[70, 55, 62].map((w, i) => (
                  <div key={i} className="skeleton" style={{ height: 44, width: `${w}%` }} />
                ))}
              </div>
            )}
            {brief?.talking_points?.length > 0 && (
              <div className="surface">
                <div className="surface-title">{t("brief.talkingPoints")}</div>
                <div className="section-body">
                  <ul>
                    {brief.talking_points.map((p, i) => (
                      <li key={i}>{p}</li>
                    ))}
                  </ul>
                </div>
              </div>
            )}
            {brief?.open_actions?.length > 0 && (
              <div className="surface actions">
                <div className="surface-title">{t("brief.openActions")}</div>
                {brief.open_actions.map((a) => (
                  <div className="action-row" key={a.id}>
                    <span className={`owner-chip${a.owner === "TBD" ? " tbd" : ""}`}>{a.owner}</span>
                    <span className="action-text">{a.action}</span>
                    {a.due && <span className="action-due">{a.due}</span>}
                  </div>
                ))}
              </div>
            )}
            {brief?.decisions?.length > 0 && (
              <div className="surface decisions">
                <div className="surface-title">{t("brief.standingDecisions")}</div>
                <div className="section-body">
                  <ul>
                    {brief.decisions.slice(0, 6).map((d) => (
                      <li key={d.id}>{d.text}</li>
                    ))}
                  </ul>
                </div>
              </div>
            )}
            {brief?.meetings?.length > 0 && (
              <div className="surface">
                <div className="surface-title">{t("brief.previousMeetings")}</div>
                {brief.meetings.slice(0, 5).map((m) => (
                  <button key={m.id} className="related-row" onClick={() => open(m.id)}>
                    <span className="related-title">{m.title}</span>
                    <span className="intel-sub">
                      {new Date(m.started_at).toLocaleDateString()}
                    </span>
                  </button>
                ))}
              </div>
            )}
            {!loading &&
              brief &&
              !brief.talking_points?.length &&
              !brief.open_actions?.length &&
              !brief.decisions?.length &&
              !brief.meetings?.length && (
                <div className="zero-empty">{t("zero.noHistory")}</div>
              )}
          </>
        )}
      </div>
    </div>
  );
}

/* ---------- Digest — Jotva Meeting.dc.html #5j ----------
   Auto-generated rollup: real meetings/topics/actions/decisions in the
   period, reusing the Overview recipe (.summary-hero, .ov-*) rather than
   a new visual system, per the design spec's own "reuse that recipe here". */
const ACTIONS_PREVIEW = 3;

function fmtRange(startIso, endIso) {
  if (!startIso || !endIso) return "";
  const s = new Date(startIso);
  const e = new Date(endIso);
  const sMonth = s.toLocaleDateString([], { month: "short" });
  if (s.getMonth() === e.getMonth()) return `${sMonth} ${s.getDate()} – ${e.getDate()}`;
  const eMonth = e.toLocaleDateString([], { month: "short" });
  return `${sMonth} ${s.getDate()} – ${eMonth} ${e.getDate()}`;
}

export function DigestView() {
  const { t } = useTranslation();
  const { setNav, selectMeeting } = useStore();
  const logoUrl = useLogo();
  const [period, setPeriod] = useState("week");
  const [data, setData] = useState(null);
  const [showAllActions, setShowAllActions] = useState(false);

  useEffect(() => {
    setData(null);
    setShowAllActions(false);
    api
      .get(`/api/intelligence/digest?period=${period}`)
      .then(setData)
      .catch(() => setData({}));
  }, [period]);

  const open = (id) => {
    setNav("meetings");
    selectMeeting(id);
  };

  const meetings = data?.meetings || [];
  const topics = data?.recurring_topics || [];
  const actions = data?.open_actions || [];
  const decisions = data?.decisions || [];
  const visibleActions = showAllActions ? actions : actions.slice(0, ACTIONS_PREVIEW);
  const hiddenActionCount = actions.length - visibleActions.length;
  const topTopic = topics[0]?.name;

  return (
    <div className="view">
      <div className="view-inner digest-inner">
        <div className="ws-header">
          <div className="ws-header-left">
            <h1 className="ws-title">{t("digest.title")}</h1>
            {data && meetings.length > 0 && (
              <div className="ws-meta">
                <span>
                  {t("digest.rangeLabel", {
                    range: fmtRange(data.range_start, data.range_end),
                    count: data.meeting_count,
                    minutes: data.total_minutes,
                  })}
                </span>
              </div>
            )}
          </div>
          <div className="digest-period-toggle">
            <button
              className={period === "week" ? "active" : ""}
              onClick={() => setPeriod("week")}
            >
              {t("digest.weekly")}
            </button>
            <button className={period === "day" ? "active" : ""} onClick={() => setPeriod("day")}>
              {t("digest.daily")}
            </button>
          </div>
        </div>

        {data === null && (
          <div className="skeleton-rows" aria-hidden="true" style={{ marginTop: 24 }}>
            {[70, 55, 62].map((w, i) => (
              <div key={i} className="skeleton" style={{ height: 44, width: `${w}%` }} />
            ))}
          </div>
        )}

        {data && meetings.length === 0 && (
          <div className="empty-state" style={{ height: "auto", padding: "80px 0" }}>
            <div className="empty-title">{t("digest.emptyHead")}</div>
            <div className="empty-sub">{t("digest.emptySub")}</div>
          </div>
        )}

        {data && meetings.length > 0 && (
          <>
            <div className="summary-hero" style={{ marginTop: 24 }}>
              <img className="summary-hero-watermark" src={logoUrl} alt="" aria-hidden="true" />
              <div className="summary-hero-head">
                <img className="logo-img" src={logoUrl} alt="" aria-hidden="true" />
                <span className="summary-eyebrow">{t("digest.summaryBy")}</span>
              </div>
              <p className="summary-body">
                {topTopic
                  ? t("digest.heroSentence", {
                      topic: topTopic,
                      count: actions.length,
                      periodWord: t(`digest.periodWord_${period}`),
                    })
                  : t("digest.heroSentenceNoTopic", { count: actions.length })}
              </p>
            </div>

            <div className="ov-columns" style={{ marginTop: 30 }}>
              <div className="ov-col-left">
                <div className="ov-section-head">
                  <span className="ov-eyebrow">{t("digest.meetings")}</span>
                  <span className="ov-count">{String(meetings.length).padStart(2, "0")}</span>
                </div>
                {meetings.map((m) => (
                  <button className="digest-meeting-row" key={m.id} onClick={() => open(m.id)}>
                    <span className="digest-meeting-dot" />
                    <span className="digest-meeting-title">{m.title}</span>
                    <span className="digest-meeting-dur">
                      {m.duration_min >= 60
                        ? `${Math.floor(m.duration_min / 60)}h ${m.duration_min % 60 ? `${m.duration_min % 60}m` : ""}`.trim()
                        : `${m.duration_min}m`}
                    </span>
                    <span className="digest-meeting-day">{m.day}</span>
                  </button>
                ))}

                {topics.length > 0 && (
                  <>
                    <div className="ov-section-head ov-section-head-spaced">
                      <span className="ov-eyebrow">{t("digest.recurringTopics")}</span>
                    </div>
                    <div className="ov-topic-chips">
                      {topics.map((tp) => (
                        <span className="ov-topic-chip" key={tp.name}>
                          {t("digest.topicCount", { name: tp.name, count: tp.n })}
                        </span>
                      ))}
                    </div>
                  </>
                )}
              </div>

              <div className="ov-col-right">
                <div className="ov-section-head">
                  <span className="ov-eyebrow">{t("digest.openActions")}</span>
                  <span className="ov-count">{String(actions.length).padStart(2, "0")}</span>
                </div>
                {actions.length === 0 ? (
                  <div className="section-empty-note">{t("notes.action.none")}</div>
                ) : (
                  <>
                    {visibleActions.map((a) => (
                      <div className="ov-action-row" key={a.id} title={a.meeting_title}>
                        <span className="ov-check" />
                        <span className="ov-action-text">{a.action}</span>
                        <span className="ov-action-owner">{a.owner}</span>
                      </div>
                    ))}
                    {hiddenActionCount > 0 && (
                      <button className="ov-show-more" onClick={() => setShowAllActions(true)}>
                        {t("notes.action.showMore", { count: hiddenActionCount })}
                      </button>
                    )}
                  </>
                )}

                <div className="ov-section-head ov-section-head-spaced">
                  <span className="ov-eyebrow">{t("notes.section.decisions")}</span>
                  <span className="ov-count">{String(decisions.length).padStart(2, "0")}</span>
                </div>
                {decisions.length === 0 ? (
                  <div className="section-empty-note">{t("notes.decisions.none")}</div>
                ) : (
                  decisions.map((d) => (
                    <div className="ov-decision-row" key={d.id}>
                      <span className="ov-decision-dot" />
                      <span>{d.text}</span>
                    </div>
                  ))
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
