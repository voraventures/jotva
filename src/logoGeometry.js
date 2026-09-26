// Jotva mark: three identical sheets sharing a bottom-left tip. The two back sheets
// are the front sheet's control points pushed through a vertical-preserving
// shear/stretch (x' = A·x, y' = C·x + D·y), weighted toward the right so their
// hidden left side stays tucked behind the front sheet. `fan` 0 = stacked, 1 = logo.

export const FRONT = [
  ["M", [0, 0]], ["C", [-40, -4], [-70, -30], [-72, -72]], ["L", [-72, -332]],
  ["C", [-72, -400], [-30, -455], [30, -482]], ["L", [320, -622]],
  ["C", [345, -634], [364, -626], [362, -600]], ["L", [342, -345]],
  ["C", [334, -270], [300, -215], [230, -170]], ["C", [150, -118], [50, -70], [0, 0]], ["Z"],
];

export const BACK = [
  [1.37, 0.33, 1.03],
  [1.68, 0.72, 1.03],
];

export const VIEWBOX = "-90 -648 715 664";

const smooth = (a, b, t) => {
  const x = Math.min(1, Math.max(0, (t - a) / (b - a)));
  return x * x * (3 - 2 * x);
};

export function sheetPath([A, C, D] = [1, 0, 1], fan = 1) {
  return FRONT.map(([cmd, ...pts]) => cmd + pts.map(([x, y]) => {
    const w = fan * smooth(-20, 300, x);
    return (x + w * (A * x - x)).toFixed(1) + "," + (y + w * (C * x + D * y - y)).toFixed(1);
  }).join(" ")).join(" ");
}

export const COLORS = {
  front: [["0", "#d8fcff"], [".42", "#4e90f8"], [".78", "#a98cf6"], ["1", "#ffc2f1"]],
  mid: [["0", "#6f88ff"], [".35", "#3452f6"], ["1", "#110d55"]],
  back: [["0", "#b27dff"], [".35", "#7a3df6"], ["1", "#1b0b52"]],
};
