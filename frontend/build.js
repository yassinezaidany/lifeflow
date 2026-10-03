/*
 * Frontend asset build (no bundler needed):
 *   - copies vendored libraries (Alpine.js, Chart.js) into static/vendor
 *   - copies the Inter variable font into static/fonts
 *   - builds an SVG sprite from Lucide icons listed in frontend/icons.json
 * Tailwind CSS is compiled separately by the `build:css` npm script.
 */
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const nm = (p) => path.join(root, "node_modules", p);
const out = (p) => path.join(root, "static", p);

function copy(src, dest) {
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.copyFileSync(src, dest);
  console.log("copied", path.relative(root, dest));
}

copy(nm("alpinejs/dist/cdn.min.js"), out("vendor/alpine.min.js"));
copy(nm("@alpinejs/focus/dist/cdn.min.js"), out("vendor/alpine-focus.min.js"));
copy(nm("@alpinejs/collapse/dist/cdn.min.js"), out("vendor/alpine-collapse.min.js"));
copy(nm("chart.js/dist/chart.umd.js"), out("vendor/chart.umd.min.js"));
copy(nm("@fontsource-variable/inter/files/inter-latin-wght-normal.woff2"), out("fonts/inter-latin-wght-normal.woff2"));
copy(nm("@fontsource-variable/inter/files/inter-latin-ext-wght-normal.woff2"), out("fonts/inter-latin-ext-wght-normal.woff2"));

const icons = JSON.parse(fs.readFileSync(path.join(__dirname, "icons.json"), "utf8"));
const names = [...new Set([...icons.ui, ...icons.picker])].sort();
const symbols = names.map((name) => {
  const file = nm(`lucide-static/icons/${name}.svg`);
  if (!fs.existsSync(file)) throw new Error(`Unknown icon: ${name}`);
  const svg = fs.readFileSync(file, "utf8");
  const inner = svg.replace(/<!--[\s\S]*?-->/g, "").replace(/^[\s\S]*?<svg[^>]*>/, "").replace(/<\/svg>\s*$/, "").trim();
  return `<symbol id="i-${name}" viewBox="0 0 24 24">${inner.replace(/\s*\n\s*/g, "")}</symbol>`;
});
const sprite = `<svg xmlns="http://www.w3.org/2000/svg">${symbols.join("")}</svg>\n`;
fs.mkdirSync(out("icons"), { recursive: true });
fs.writeFileSync(out("icons/sprite.svg"), sprite);
console.log(`sprite: ${names.length} icons`);
