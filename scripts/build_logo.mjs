// Generates every static Jotva logo SVG from src/logoGeometry.js.
// Run: node scripts/build_logo.mjs
import { writeFileSync } from "node:fs";
import { BACK, VIEWBOX, sheetPath, COLORS } from "../src/logoGeometry.js";

const front = sheetPath(undefined, 0);
const [mid, back] = BACK.map((m) => sheetPath(m, 1));

const grad = (id, stops) =>
  `<linearGradient id="${id}" x1="1" y1="0" x2="0" y2="1">${stops
    .map(([o, c]) => `<stop offset="${o}" stop-color="${c}"/>`).join("")}</linearGradient>`;

function color({ dark }) {
  const shadow = dark ? 0.75 : 0.3;
  const bloom = dark
    ? `<g filter="url(#bloom)" opacity=".45"><path d="${back}" fill="#7a3df6"/><path d="${mid}" fill="#3452f6"/><path d="${front}" fill="#4e90f8"/></g>`
    : "";
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${VIEWBOX}" role="img" aria-label="Jotva">
<defs>${grad("f", COLORS.front)}${grad("m", COLORS.mid)}${grad("b", COLORS.back)}
<linearGradient id="rim" x1="1" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".85"/><stop offset=".5" stop-color="#fff" stop-opacity=".18"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
<filter id="sh" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="-8" dy="10" stdDeviation="16" flood-color="#03021a" flood-opacity="${shadow}"/></filter>
${dark ? '<filter id="bloom" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="22"/></filter>' : ""}
</defs>${bloom}
<path d="${back}" fill="url(#b)" stroke="url(#rim)" stroke-width="3" filter="url(#sh)"/>
<path d="${mid}" fill="url(#m)" stroke="url(#rim)" stroke-width="3" filter="url(#sh)"/>
<path d="${front}" fill="url(#f)" stroke="url(#rim)" stroke-width="3" filter="url(#sh)"/>
</svg>
`;
}

// Flat single-colour version: layered opacity keeps the three sheets readable.
const mono = (fill) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${VIEWBOX}" role="img" aria-label="Jotva">
<path d="${back}" fill="${fill}" fill-opacity=".38"/>
<path d="${mid}" fill="${fill}" fill-opacity=".62"/>
<path d="${front}" fill="${fill}"/>
</svg>
`;

// No filters: favicons render at 16–32px where blur is just mud.
const flat = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${VIEWBOX}">
<defs>${grad("f", COLORS.front)}${grad("m", COLORS.mid)}${grad("b", COLORS.back)}</defs>
<path d="${back}" fill="url(#b)"/><path d="${mid}" fill="url(#m)"/><path d="${front}" fill="url(#f)"/>
</svg>
`;

const out = {
  "logo-primary.svg": color({ dark: false }),
  "logo-primary-dark.svg": color({ dark: true }),
  "logo-monochrome.svg": mono("#111111"),
  "logo-reversed.svg": mono("#ffffff"),
};
for (const dir of ["src/assets", "design-reference"]) {
  for (const [name, svg] of Object.entries(out)) writeFileSync(`${dir}/${name}`, svg);
}
for (const name of ["logo-primary.svg", "logo-monochrome.svg", "logo-reversed.svg"]) {
  writeFileSync(`electron/assets/${name}`, out[name]);
}
writeFileSync("electron/assets/favicon.svg", flat);
console.log("wrote logo SVGs");
