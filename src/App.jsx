import React, { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useStore, useLogo } from "./store.jsx";
import i18n from "./i18n.js";
import BriefPanel from "./components/BriefPanel.jsx";
import CaptureFlow from "./components/CaptureFlow.jsx";
import CoachPanel from "./components/CoachPanel.jsx";
import IntelligenceView from "./components/IntelligenceView.jsx";
import MeetingList from "./components/MeetingList.jsx";
import NotesPanel from "./components/NotesPanel.jsx";
import OnboardingTour from "./components/OnboardingTour.jsx";
import PdfPrintRoot from "./components/PdfPrintRoot.jsx";
import RecordPrompt from "./components/RecordPrompt.jsx";
import Settings from "./components/Settings.jsx";
import AppHeader from "./components/AppHeader.jsx";
import Dock from "./components/Dock.jsx";
import Titlebar from "./components/Titlebar.jsx";
import UpcomingToast from "./components/UpcomingToast.jsx";
import UpgradeModal from "./components/UpgradeModal.jsx";
import AgentView from "./components/AgentView.jsx";
import { DigestView, MeetingZeroView, SearchView, TodayView } from "./components/Views.jsx";

const platform = window.jotva?.platform || "darwin";
const MIN_LIST = 260;
const MAX_LIST = 480;

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, info) {
    console.error("[Jotva] Render error caught by ErrorBoundary:", error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="boot">
          <div className="logo">
            <img className="logo-img" src={this.props.logoUrl} alt="" aria-hidden="true" /> <span className="brand-wordmark brand-wordmark-large">Jotva</span>
          </div>
          <h2 style={{ margin: "16px 0 4px", fontSize: 18, fontWeight: 600, color: "var(--text)" }}>
            {i18n.t("app.error.title")}
          </h2>
          <div className="boot-sub">{i18n.t("app.error.restartHint")}</div>
          <button className="btn" style={{ marginTop: 16 }} onClick={() => window.location.reload()}>
            {i18n.t("app.error.restart")}
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function App() {
  const { t } = useTranslation();
  const { ready, connectionFailed, nav, toasts, dismissToast } = useStore();
  const logoUrl = useLogo();
  const [listWidth, setListWidth] = useState(() => {
    const saved = Number(localStorage.getItem("jotva_list_width"));
    return saved >= MIN_LIST && saved <= MAX_LIST ? saved : 300;
  });
  const [dragging, setDragging] = useState(false);
  const [tourActive, setTourActive] = useState(false);
  const dragRef = useRef(null);

  // Start the interactive tour once the app is ready and the welcome onboarding
  // has been completed (separate "jotva_tour_done" flag so the tour and the
  // welcome screen never fight over a single flag).
  useEffect(() => {
    if (!ready) return undefined;
    if (localStorage.getItem("jotva_tour_done") === "true") return undefined;
    const tryStart = () => {
      if (localStorage.getItem("jotva_onboarded") === "true") {
        setTourActive(true);
        return true;
      }
      return false;
    };
    if (tryStart()) return undefined;
    // Poll only while the welcome onboarding can still complete; give up after
    // 10 minutes rather than polling localStorage for the app's whole lifetime.
    let ticks = 0;
    const id = setInterval(() => {
      if (tryStart() || ++ticks > 1500) clearInterval(id);
    }, 400);
    return () => clearInterval(id);
  }, [ready]);

  const onDragStart = useCallback(
    (e) => {
      e.preventDefault();
      setDragging(true);
      const startX = e.clientX;
      const startW = listWidth;
      const onMove = (ev) => {
        const w = Math.min(MAX_LIST, Math.max(MIN_LIST, startW + ev.clientX - startX));
        setListWidth(w);
      };
      const onUp = (ev) => {
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
        setDragging(false);
        const w = Math.min(MAX_LIST, Math.max(MIN_LIST, startW + ev.clientX - startX));
        localStorage.setItem("jotva_list_width", String(w));
      };
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    },
    [listWidth]
  );

  if (connectionFailed) {
    return (
      <div className="boot">
        <div className="logo">
          <img className="logo-img" src={logoUrl} alt="" aria-hidden="true" /> <span className="brand-wordmark brand-wordmark-large">Jotva</span>
        </div>
        <div className="boot-sub">{t("app.engine.unreachable")}</div>
      </div>
    );
  }

  if (!ready) {
    return (
      <div className="boot">
        <div className="logo">
          <img className="logo-img" src={logoUrl} alt="" aria-hidden="true" /> <span className="brand-wordmark brand-wordmark-large">Jotva</span>
        </div>
        <div className="processing-ring" />
        <div className="boot-sub">{t("app.engine.starting")}</div>
      </div>
    );
  }

  const columns = nav === "meetings" ? `${listWidth}px minmax(0, 1fr)` : "minmax(0, 1fr)";

  return (
    <ErrorBoundary logoUrl={logoUrl}>
      {platform === "win32" && <Titlebar />}
      <div className={`app green-glass ${platform}`} style={{ gridTemplateColumns: columns }}>
        <AppHeader />
        {nav === "meetings" && (
          <>
            <MeetingList>
              <div
                className={`resize-handle${dragging ? " dragging" : ""}`}
                ref={dragRef}
                onMouseDown={onDragStart}
                title={t("app.dragResize")}
              />
            </MeetingList>
            <NotesPanel />
          </>
        )}
        {nav === "today" && <TodayView />}
        {nav === "library" && <IntelligenceView />}
        {nav === "search" && <SearchView />}
        {nav === "zero" && <MeetingZeroView />}
        {nav === "digest" && <DigestView />}
        {nav === "agent" && <AgentView />}
        <Settings />
        <Dock />
        <RecordPrompt />
        <UpcomingToast />
        <UpgradeModal />
        <CoachPanel />
        <BriefPanel />
        {toasts.length > 0 && (
          <div className="toast-stack">
            {toasts.map((tst) => (
              <div key={tst.id} className={`toast ${tst.kind}`}>
                <span className="toast-message">{tst.message}</span>
                {tst.action && (
                  <button
                    className="toast-action"
                    onClick={() => {
                      tst.action.onAction();
                      dismissToast(tst.id);
                    }}
                  >
                    {tst.action.label}
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
      {/* The signature capture flow: idle → recording → processing → ready */}
      <CaptureFlow />
      {tourActive && <OnboardingTour onComplete={() => setTourActive(false)} />}
      <PdfPrintRoot />
    </ErrorBoundary>
  );
}
