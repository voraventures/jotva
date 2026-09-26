// Shared UI primitives: styled Select (replaces native <select>) and Confirm
// dialog (replaces window.confirm). Plain React + CSS, no dependencies.
import React, { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";

// Styled listbox. options: [{ value, label }]. Values are compared with ===,
// so pass the same types in `value` and `options`.
export function Select({ value, onChange, options, className = "", ariaLabel }) {
  const [open, setOpen] = useState(false);
  const [hi, setHi] = useState(-1); // highlighted index while open
  const rootRef = useRef(null);
  const listRef = useRef(null);

  const selectedIdx = options.findIndex((o) => o.value === value);
  const selectedLabel = options[selectedIdx]?.label ?? "";

  useEffect(() => {
    if (!open) return;
    setHi(selectedIdx >= 0 ? selectedIdx : 0);
    const onDocDown = (e) => {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onDocDown);
    return () => document.removeEventListener("mousedown", onDocDown);
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  // Keep the highlighted option scrolled into view.
  useEffect(() => {
    if (!open || hi < 0) return;
    listRef.current?.children[hi]?.scrollIntoView({ block: "nearest" });
  }, [open, hi]);

  const commit = (idx) => {
    const opt = options[idx];
    if (opt) onChange(opt.value);
    setOpen(false);
  };

  const onKeyDown = (e) => {
    if (!open) {
      if (["Enter", " ", "ArrowDown", "ArrowUp"].includes(e.key)) {
        e.preventDefault();
        setOpen(true);
      }
      return;
    }
    if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); setOpen(false); }
    else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      commit(hi);
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setHi((h) => Math.min(options.length - 1, h + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHi((h) => Math.max(0, h - 1));
    } else if (e.key === "Home") { e.preventDefault(); setHi(0); }
    else if (e.key === "End") { e.preventDefault(); setHi(options.length - 1); }
  };

  return (
    <div className={`select ${className}`} ref={rootRef} onKeyDown={onKeyDown}>
      <button
        type="button"
        className="select-trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="select-value">{selectedLabel}</span>
        <svg className="select-chevron" width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
          <path d="M2 3.5 5 6.5 8 3.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {open && (
        <div className="select-menu" role="listbox" ref={listRef}>
          {options.map((o, i) => (
            <button
              type="button"
              key={String(o.value)}
              role="option"
              aria-selected={o.value === value}
              className={`select-option${o.value === value ? " selected" : ""}${i === hi ? " highlighted" : ""}`}
              onMouseEnter={() => setHi(i)}
              onClick={() => commit(i)}
            >
              {o.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// Styled confirmation dialog. Render conditionally: {target && <Confirm …/>}.
export function Confirm({ title, body, confirmLabel, danger, onConfirm, onCancel }) {
  const { t } = useTranslation();
  const confirmRef = useRef(null);

  useEffect(() => {
    confirmRef.current?.focus();
    const onKey = (e) => {
      if (e.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);

  // Portaled to <body>: a glass ancestor (backdrop-filter) would otherwise clip it.
  return createPortal(
    <div
      className="modal-backdrop"
      style={{ zIndex: 90 }}
      onMouseDown={(e) => e.target === e.currentTarget && onCancel()}
    >
      <div className="confirm-card" role="alertdialog" aria-modal="true" aria-label={title}>
        <div className="confirm-title">{title}</div>
        {body && <div className="confirm-body">{body}</div>}
        <div className="confirm-actions">
          <button className="btn secondary" onClick={onCancel}>
            {t("common.cancel")}
          </button>
          <button
            ref={confirmRef}
            className={`btn${danger ? " danger" : ""}`}
            onClick={onConfirm}
          >
            {confirmLabel || t("common.confirm")}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
