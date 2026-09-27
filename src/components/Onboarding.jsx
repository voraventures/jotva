import React, { useState } from "react";
import wiselyHello from "../assets/wisely/hello.webm";
import wiselyIdle from "../assets/wisely/idle.webm";
import wiselyStill from "../assets/wisely/still.png";
import { useTranslation } from "react-i18next";
import { api } from "../api.js";
import { useStore } from "../store.jsx";
import { MicIcon, SparkIcon, CheckIcon } from "./icons.jsx";

// First-launch demo meeting — created via POST /api/meetings, which derives
// actions/decisions/topics from notes_markdown (same as the recording pipeline).
const DEMO_MEETING = {
  title: "Q2 Product Planning — Demo",
  date: new Date().toISOString(),
  attendees: ["Sarah Chen", "Marcus Rodriguez", "You"],
  source: "recorded",
  duration_seconds: 1847,
  context:
    "The team met to review Q2 priorities and align on the product roadmap. Key focus areas include the mobile app launch, enterprise tier pricing, and reducing onboarding time from 14 minutes to under 3.",
  key_discussions:
    "**Mobile App Timeline**: Sarah confirmed the iOS build is on track for a June 30 soft launch. Beta testers have been identified. **Enterprise Pricing**: Marcus proposed a $99/seat/month tier with SSO and audit logs. The team agreed to validate with 3 pilot customers before committing. **Onboarding Optimization**: Current median onboarding time is 14 minutes. Target is under 3 minutes. Proposed solution: interactive demo content on first launch.",
  decisions: [
    "Proceed with June 30 iOS soft launch targeting 50 beta users",
    "Pilot enterprise tier with 3 existing customers before public launch",
    "Ship onboarding demo content in next release",
  ],
  action_items: [
    { action: "Finalize beta tester list and send invites", owner: "Sarah Chen", due_date: "2026-06-20" },
    { action: "Draft enterprise pricing one-pager for pilot customers", owner: "Marcus Rodriguez", due_date: "2026-06-18" },
    { action: "Reduce onboarding flow to under 3 minutes", owner: "TBD", due_date: "2026-06-25" },
  ],
  notes_markdown:
    "## Executive Summary\nThe team aligned on Q2 priorities with a focus on mobile launch, enterprise expansion, and onboarding improvement.\n\n## Key Discussions\n**Mobile App Timeline**: iOS build on track for June 30 soft launch.\n**Enterprise Pricing**: $99/seat/month tier proposed, pilot with 3 customers first.\n**Onboarding**: Target under 3 minutes from current 14 minutes.\n\n## Decisions Made\n- June 30 iOS soft launch with 50 beta users\n- Enterprise pilot before public launch\n- Ship onboarding demo content\n\n## Action Items\n| Owner | Action | Due Date |\n|-------|--------|----------|\n| Sarah Chen | Finalize beta tester list | 2026-06-20 |\n| Marcus Rodriguez | Enterprise pricing one-pager | 2026-06-18 |\n| TBD | Reduce onboarding flow | 2026-06-25 |\n\n## Next Steps\n1. Sarah sends beta invites by June 20\n2. Marcus delivers pricing one-pager by June 18\n3. Team reviews onboarding metrics next week\n\n## Compliance Flags\nNone identified.",
};

// keys under onboarding.callouts.*
const CALLOUTS = [
  { Icon: MicIcon, key: "local" },
  { Icon: SparkIcon, key: "ai" },
  { Icon: CheckIcon, key: "offline" },
];

// Wisely, the Agent, greets new users: he waves once, then settles into his idle loop.
// The clips have a transparent background, so he stands freely on the page. A still
// image when the Mac asks for reduced motion.
function WiselyHello() {
  const { t } = useTranslation();
  const [clip, setClip] = useState("hello");
  const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  return (
    <figure className="onboarding-wisely">
      <div className="onboarding-wisely-stage">
        {still ? (
          <img src={wiselyStill} alt="" />
        ) : (
          <video key={clip} src={clip === "hello" ? wiselyHello : wiselyIdle} poster={wiselyStill}
            autoPlay muted playsInline loop={clip === "idle"} onEnded={() => setClip("idle")} aria-hidden="true" />
        )}
      </div>
      <figcaption>{t("onboarding.wiselyHi")}</figcaption>
    </figure>
  );
}

export default function Onboarding({ onDone }) {
  const { t } = useTranslation();
  const { refreshMeetings, selectMeeting, showToast } = useStore();
  const [loading, setLoading] = useState(false);

  const markOnboarded = () => localStorage.setItem("jotva_onboarded", "true");

  const loadDemo = () => {
    setLoading(true);
    api
      .post("/api/meetings", DEMO_MEETING)
      .then(async (res) => {
        markOnboarded();
        onDone?.();
        await refreshMeetings();
        selectMeeting(res.id);
      })
      .catch((e) => {
        showToast(e.message, "error");
        setLoading(false);
      });
  };

  const skip = () => {
    markOnboarded();
    onDone?.();
  };

  return (
    <div className="detail-panel">
      <div className="onboarding">
        <WiselyHello />
        <h1 className="onboarding-title">
          {t("onboarding.titlePrefix")} <em>{t("onboarding.titleEmphasis")}</em>{" "}
          {t("onboarding.titleSuffix")}
        </h1>
        <div className="onboarding-sub">{t("onboarding.sub")}</div>
        <button className="onboarding-cta" disabled={loading} onClick={loadDemo}>
          {loading ? t("onboarding.loading") : t("onboarding.loadDemo")}
        </button>
        <div className="onboarding-callouts">
          {CALLOUTS.map(({ Icon, key }) => (
            <div className="onboarding-callout" key={key}>
              <span className="onboarding-callout-icon">
                <Icon size={18} />
              </span>
              <div className="onboarding-callout-title">{t(`onboarding.callouts.${key}.title`)}</div>
              <div className="onboarding-callout-desc">{t(`onboarding.callouts.${key}.desc`)}</div>
            </div>
          ))}
        </div>
        <button className="onboarding-skip" onClick={skip}>
          {t("onboarding.skip")}
        </button>
      </div>
    </div>
  );
}
