// Safe markdown renderer: parses a small markdown subset directly into React
// elements. No innerHTML anywhere, so untrusted note/transcript content can
// never inject markup (C4 — structural XSS prevention).
import React from "react";

function renderInline(text, keyPrefix) {
  // bold (**x**) only; everything else is plain text
  const parts = [];
  let rest = text;
  let i = 0;
  while (rest.length) {
    const start = rest.indexOf("**");
    if (start === -1) {
      parts.push(rest);
      break;
    }
    const end = rest.indexOf("**", start + 2);
    if (end === -1) {
      parts.push(rest);
      break;
    }
    if (start > 0) parts.push(rest.slice(0, start));
    parts.push(
      <strong className="topic-chip" key={`${keyPrefix}-b${i++}`}>
        {rest.slice(start + 2, end)}
      </strong>
    );
    rest = rest.slice(end + 2);
  }
  return parts;
}

export default function Markdown({ text, className = "" }) {
  if (!text) return null;
  const blocks = [];
  const lines = text.split("\n");
  let listBuf = [];
  let key = 0;

  const flushList = () => {
    if (listBuf.length) {
      blocks.push(
        <ul key={`ul${key++}`}>
          {listBuf.map((item, i) => (
            <li key={i}>{renderInline(item, `li${key}-${i}`)}</li>
          ))}
        </ul>
      );
      listBuf = [];
    }
  };

  for (const raw of lines) {
    const line = raw.trim();
    if (!line) {
      flushList();
      continue;
    }
    if (line.startsWith("|")) {
      // tables are rendered by dedicated components; show as plain rows here
      flushList();
      const cells = line
        .replace(/^\||\|$/g, "")
        .split("|")
        .map((c) => c.trim());
      if (cells.every((c) => /^[-: ]*$/.test(c))) continue;
      blocks.push(
        <p key={`tr${key++}`} className="topic-line">
          {renderInline(cells.join("  ·  "), `tr${key}`)}
        </p>
      );
    } else if (line.startsWith("- ") || line.startsWith("* ")) {
      listBuf.push(line.slice(2));
    } else if (line.startsWith("## ")) {
      flushList();
      blocks.push(<h4 key={`h${key++}`} className="md-heading">{renderInline(line.slice(3), `h${key}`)}</h4>);
    } else if (line.startsWith("### ")) {
      flushList();
      blocks.push(
        <p key={`h${key++}`} className="topic-line">
          <strong className="topic-chip">{line.slice(4)}</strong>
        </p>
      );
    } else {
      flushList();
      blocks.push(<p key={`p${key++}`}>{renderInline(line, `p${key}`)}</p>);
    }
  }
  flushList();
  return <div className={`section-body ${className}`}>{blocks}</div>;
}
