// Run against a running deployment: node scripts/check-routes.mjs https://agent.lsprai.com
const base = new URL(process.argv[2] ?? "http://127.0.0.1:38000");
const pages = ["/", "/rag", "/kb", "/help", "/contact", "/changelog", "/pricing", "/legal/cookies", "/login", "/register", "/forgot-password"];
const links = new Set();
for (const prefix of ["", "/en", "/pl"]) {
  for (const page of pages) {
    const path = prefix + (page === "/" ? "/" : page);
    const response = await fetch(new URL(path, base));
    if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
    const html = await response.text();
    for (const match of html.matchAll(/<a\b[^>]*href="([^"<>]+)"/g)) {
      const url = new URL(match[1].replaceAll("&amp;", "&"), base);
      if (url.origin === base.origin) links.add(url.pathname + url.search);
    }
  }
}
for (const path of links) {
  const response = await fetch(new URL(path, base));
  if (!response.ok) throw new Error(`Linked destination ${path}: HTTP ${response.status}`);
}
console.log(`PASS: ${pages.length * 3} locale routes and ${links.size} visible link destinations.`);
