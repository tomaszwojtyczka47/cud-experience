/*
 * C.U.D. Experience — Journal feed proxy.
 *
 * Deployed as a Cloudflare Worker on Route: cudexperience.com/api/journal
 * (same origin as the site — no CORS handling needed, and the existing
 * per-page CSP `connect-src 'self'` already covers the browser fetch()).
 *
 * Fetches TravelPixieFreak's per-language WordPress category RSS feed and
 * returns it as a small JSON array for assets/js/journal-carousel.js to
 * render. This is the mechanism behind journal/index.html and pl/journal/
 * index.html's auto-syncing carousel — when a new post is published in the
 * matching category on travelpixiefreak.com, it appears on
 * cudexperience.com automatically, no redeploy needed.
 *
 * The English and Polish posts live in two separate WordPress categories
 * (verified 2026-09-23 — each feed contains only its own language, so no
 * text-based language filtering is needed) and journal-carousel.js
 * requests the one matching the page's <html lang> via ?lang=:
 *   en (default): https://travelpixiefreak.com/category/shades-of-human-life/feed/
 *   pl:           https://travelpixiefreak.com/category/odcienie-ludzkiego-zycia/feed/
 *
 * Deliberately kept at WordPress's default 10-most-recent items (the
 * feed's native limit) rather than switching to the REST API's full
 * per_page=100 listing — Piotr chose to keep the carousel to the 10
 * newest posts rather than surface all that exist upstream.
 *
 * Response is cached at Cloudflare's edge (Cache API) for CACHE_TTL_
 * SECONDS, keyed per language, so the upstream WordPress site is hit at
 * most once per TTL window per language regardless of visitor traffic on
 * cudexperience.com.
 */

const FEED_URLS = {
  en: "https://travelpixiefreak.com/category/shades-of-human-life/feed/",
  pl: "https://travelpixiefreak.com/category/odcienie-ludzkiego-zycia/feed/",
};
const CACHE_TTL_SECONDS = 3600; // 1 hour

function stripCdata(s) {
  const m = s.match(/^<!\[CDATA\[([\s\S]*)\]\]>$/);
  return m ? m[1] : s;
}

function decodeEntities(s) {
  return s
    .replace(/&#(\d+);/g, (_, n) => String.fromCharCode(parseInt(n, 10)))
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&nbsp;/g, " ");
}

function tagValue(block, tag) {
  const m = block.match(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)<\\/${tag}>`));
  if (!m) return "";
  return decodeEntities(stripCdata(m[1].trim()).replace(/<[^>]+>/g, "")).trim();
}

function parseItems(xml) {
  const items = [];
  const itemRe = /<item>([\s\S]*?)<\/item>/g;
  let m;
  while ((m = itemRe.exec(xml))) {
    const block = m[1];
    const title = tagValue(block, "title");
    const link = tagValue(block, "link");
    const pubDate = tagValue(block, "pubDate");
    const excerpt = tagValue(block, "description");
    if (title && link && link.indexOf("https://travelpixiefreak.com/") === 0) {
      items.push({ title, link, pubDate, excerpt });
    }
  }
  return items;
}

function json(body, status, extraHeaders) {
  return new Response(JSON.stringify(body), {
    status: status || 200,
    headers: Object.assign(
      { "Content-Type": "application/json; charset=utf-8" },
      extraHeaders || {}
    ),
  });
}

export default {
  async fetch(request, env, ctx) {
    if (request.method !== "GET") {
      return json({ error: "method_not_allowed" }, 405);
    }

    const reqUrl = new URL(request.url);
    const lang = reqUrl.searchParams.get("lang") === "pl" ? "pl" : "en";
    const feedUrl = FEED_URLS[lang];

    const cache = caches.default;
    const cacheKey = new Request("https://cudexperience.com/api/journal-cache-key?lang=" + lang);

    const cached = await cache.match(cacheKey);
    if (cached) return cached;

    let items = [];
    try {
      const res = await fetch(feedUrl, {
        headers: { "User-Agent": "CUDExperienceJournalBot/1.0 (+https://cudexperience.com)" },
      });
      if (res.ok) {
        items = parseItems(await res.text());
      }
    } catch (e) {
      // Upstream unreachable — fall through and return an empty list;
      // the client keeps its existing "coming soon" fallback in that case.
    }

    const response = json(
      { items, fetchedAt: new Date().toISOString() },
      200,
      { "Cache-Control": "public, max-age=" + CACHE_TTL_SECONDS }
    );
    ctx.waitUntil(cache.put(cacheKey, response.clone()));
    return response;
  },
};
