// Verified brand marks for the Integrations tab — inline SVG, 22×22 inside
// the 40×40 badge. `tint` is the brand primary at ~8% opacity for the badge
// background. Notion ships no tint here: its theme-aware background lives in
// styles.css (.integration-badge.brand-notion) and the mark uses currentColor
// so it stays legible on dark themes.
import React from "react";

export const BRAND_LOGOS = {
  slack: {
    tint: "rgba(54, 197, 240, 0.08)",
    svg: (
      <svg width="22" height="22" viewBox="0 0 60 60" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
        <path d="M22,12 a6,6 0 1 1 6,-6 v6z M22,16 a6,6 0 0 1 0,12 h-16 a6,6 0 1 1 0,-12" fill="#36C5F0"/>
        <path d="M48,22 a6,6 0 1 1 6,6 h-6z M32,6 a6,6 0 1 1 12,0v16a6,6 0 0 1 -12,0z" fill="#2EB67D"/>
        <path d="M38,48 a6,6 0 1 1 -6,6 v-6z M54,32 a6,6 0 0 1 0,12 h-16 a6,6 0 1 1 0,-12" fill="#ECB22E"/>
        <path d="M12,38 a6,6 0 1 1 -6,-6 h6z M16,38 a6,6 0 1 1 12,0v16a6,6 0 0 1 -12,0z" fill="#E01E5A"/>
      </svg>
    ),
  },
  notion: {
    tint: null, // theme-aware: see .integration-badge.brand-notion in styles.css
    color: "var(--text)",
    svg: (
      <svg width="22" height="22" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg" fill="currentColor" aria-hidden="true">
        <path d="M6.6 7.2C10.3 10.2 11.7 9.9 19 9.4L75.2 5.8c1.4 0 0.2-1.4-0.2-1.6L64.7 0.2C62.6-1.4 59.5-0.8 52.7 0.4L8.5 3.9C6.1 4.1 5.6 5.4 6.6 7.2zm4.2 16.2V85c0 3.7 1.9 5.1 6.1 4.9l59.6-3.4c4.2-0.2 4.7-2.8 4.7-5.8V22c0-3-1.2-4.6-3.7-4.4L14.5 21.1c-2.8 0.2-3.7 1.6-3.7 4.6v-2.3zm57 3.7c0.5 2.1 0 4.2-2.1 4.4l-3.5 0.7v51.3c-3 1.6-5.8 2.6-8.2 2.6c-3.7 0-4.7-1.2-7.4-4.7L26.5 42.7v34.8l6 1.4s0 4.2-5.8 4.2L10.1 84.1c-0.5-0.9 0-3.3 1.6-3.7l4.2-1.2V35L10.1 34.5c-0.5-2.1 0.7-5.1 4-5.3l17.2-1.2L55.9 64V31.5l-5.4-0.5c-0.5-2.6 1.4-4.4 3.7-4.7L57 26.1z"/>
      </svg>
    ),
  },
  linear: {
    tint: "rgba(94, 106, 210, 0.08)",
    svg: (
      <svg width="22" height="22" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" fill="#5E6AD2" aria-hidden="true">
        <path d="M2.886 4.18A11.982 11.982 0 0 1 11.99 0C18.624 0 24 5.376 24 12.009c0 3.64-1.62 6.903-4.18 9.105L2.887 4.18ZM1.817 5.626l16.556 16.556c-.524.33-1.075.62-1.65.866L.951 7.277c.247-.575.537-1.126.866-1.65ZM.322 9.163l14.515 14.515c-.71.172-1.443.282-2.195.322L0 11.358a12 12 0 0 1 .322-2.195Zm-.17 4.862 9.823 9.824a12.02 12.02 0 0 1-9.824-9.824Z"/>
      </svg>
    ),
  },
  jira: {
    tint: "rgba(0, 82, 204, 0.08)",
    svg: (
      <svg width="22" height="22" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" fill="#0052CC" aria-hidden="true">
        <path d="M11.571 11.513H0a5.218 5.218 0 0 0 5.232 5.215h2.13v2.057A5.215 5.215 0 0 0 12.575 24V12.518a1.005 1.005 0 0 0-1.005-1.005zm5.723-5.756H5.736a5.215 5.215 0 0 0 5.215 5.214h2.129v2.058a5.218 5.218 0 0 0 5.215 5.214V6.758a1.001 1.001 0 0 0-1.001-1.001zM23.013 0H11.455a5.215 5.215 0 0 0 5.215 5.215h2.129v2.057A5.215 5.215 0 0 0 24 12.483V1.005A1.001 1.001 0 0 0 23.013 0Z"/>
      </svg>
    ),
  },
  hubspot: {
    tint: "rgba(255, 122, 89, 0.08)",
    svg: (
      <svg width="22" height="22" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" fill="#FF7A59" aria-hidden="true">
        <path d="M18.164 7.931V5.053a2.286 2.286 0 001.312-2.06 2.285 2.285 0 10-4.57 0c0 .9.522 1.674 1.284 2.06v2.878a6.499 6.499 0 00-3.083 1.352L4.8 3.998a2.547 2.547 0 10-.79 1.197l8.124 5.23A6.457 6.457 0 0011.5 12.5a6.5 6.5 0 003.908 5.944l-.898 2.709a2 2 0 101.346.448l.897-2.707A6.5 6.5 0 0018.164 7.931zm-2.414 9.069a3.5 3.5 0 110-7 3.5 3.5 0 010 7z"/>
      </svg>
    ),
  },
  salesforce: {
    tint: "rgba(0, 161, 224, 0.08)",
    svg: (
      <svg width="22" height="22" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" fill="#00A1E0" aria-hidden="true">
        <path d="M9.972 4.805a4.2 4.2 0 013.032-1.305c1.55 0 2.9.818 3.662 2.051a5.09 5.09 0 011.922-.375c2.832 0 5.162 2.108 5.162 4.77 0 2.66-2.21 4.778-5.162 4.778-.337 0-.666-.033-.984-.097a3.903 3.903 0 01-3.448 2.107c-.787 0-1.516-.228-2.13-.62a4.98 4.98 0 01-4.459 2.811C4.71 18.925 2 16.215 2 12.845c0-1.665.647-3.178 1.703-4.29A4.494 4.494 0 013.5 7.305C3.5 4.85 5.5 2.85 7.955 2.85c.785 0 1.523.208 2.157.572l-.14-.617z"/>
      </svg>
    ),
  },
  google_drive: {
    tint: "rgba(66, 133, 244, 0.06)",
    svg: (
      <svg width="22" height="22" viewBox="0 0 87.3 78" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
        <path d="m6.6 66.85 3.85 6.65c.8 1.4 1.95 2.5 3.3 3.3l13.75-23.8h-27.5c0 1.55.4 3.1 1.2 4.5z" fill="#0066da"/>
        <path d="m43.65 25-13.75-23.8c-1.35.8-2.5 1.9-3.3 3.3l-25.4 44a9.06 9.06 0 0 0 -1.2 4.5h27.5z" fill="#00ac47"/>
        <path d="m73.55 76.8c1.35-.8 2.5-1.9 3.3-3.3l1.6-2.75 7.65-13.25c.8-1.4 1.2-2.95 1.2-4.5h-27.502l5.852 11.5z" fill="#ea4335"/>
        <path d="m43.65 25 13.75-23.8c-1.35-.8-2.9-1.2-4.5-1.2h-18.5c-1.6 0-3.15.45-4.5 1.2z" fill="#00832d"/>
        <path d="m59.8 53h-32.3l-13.75 23.8c1.35.8 2.9 1.2 4.5 1.2h50.8c1.6 0 3.15-.45 4.5-1.2z" fill="#2684fc"/>
        <path d="m73.4 26.5-12.7-22c-.8-1.4-1.95-2.5-3.3-3.3l-13.75 23.8 16.15 28h27.45c0-1.55-.4-3.1-1.2-4.5z" fill="#ffba00"/>
      </svg>
    ),
  },
  zapier: {
    tint: "rgba(255, 74, 0, 0.08)",
    svg: (
      <svg width="22" height="22" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" fill="#FF4A00" aria-hidden="true">
        <path d="M24 10.5H14.862l6.51-6.51-2.121-2.121-6.751 6.752V0h-3v8.62L2.75 1.87.629 3.99l6.511 6.51H0v3h7.14L.63 17.01l2.121 2.121 6.749-6.75V24h3v-8.619l6.75 6.75 2.121-2.121-6.51-6.51H24z"/>
      </svg>
    ),
  },
};

// Calendar provider marks, drawn to read at ~22px inside a settings card icon.
export function GoogleCalendarLogo({ size = 22 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <rect width="24" height="24" rx="3.5" fill="#ffffff" />
      <path d="M3.5 0H19v4.5H4.5V19H0V3.5A3.5 3.5 0 0 1 3.5 0z" fill="#4285F4" />
      <path d="M19 0h1.5A3.5 3.5 0 0 1 24 3.5V19h-5z" fill="#FBBC04" />
      <path d="M0 19h19v5H3.5A3.5 3.5 0 0 1 0 20.5z" fill="#34A853" />
      <path d="M19 19h5l-5 5z" fill="#EA4335" />
      <text x="11.75" y="15.6" textAnchor="middle" fontSize="8.2" fontWeight="700"
        fontFamily="-apple-system, BlinkMacSystemFont, sans-serif" fill="#4285F4">31</text>
    </svg>
  );
}

export function OutlookCalendarLogo({ size = 22 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <rect x="7" y="4" width="16" height="16" rx="2.5" fill="#28A8EA" />
      <path d="M7.5 8.5 15 13.5l7.5-5" fill="none" stroke="#0364B8" strokeWidth="1.4" strokeLinejoin="round" />
      <rect x="1" y="6" width="12" height="12" rx="2.2" fill="#0078D4" />
      <ellipse cx="7" cy="12" rx="2.7" ry="3.4" fill="none" stroke="#ffffff" strokeWidth="1.9" />
    </svg>
  );
}

export function AppleCalendarLogo({ size = 22, date = new Date() }) {
  const day = date.toLocaleDateString("en-US", { weekday: "short" }).toUpperCase();
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <rect width="24" height="24" rx="5" fill="#ffffff" />
      <text x="12" y="8.2" textAnchor="middle" fontSize="5.4" fontWeight="600" letterSpacing=".2"
        fontFamily="-apple-system, BlinkMacSystemFont, sans-serif" fill="#FF3B30">{day}</text>
      <text x="12" y="19.6" textAnchor="middle" fontSize="11.5" fontWeight="400"
        fontFamily="-apple-system, BlinkMacSystemFont, sans-serif" fill="#1c1c1e">{date.getDate()}</text>
    </svg>
  );
}
