/*
 * C.U.D. Experience — Journal feed proxy.
 *
 * Deployed as a Cloudflare Worker on Route: cudexperience.com/api/journal
 * (same origin as the site — no CORS handling needed, and the existing
 * per-page CSP `connect-src 'self'` already covers the browser fetch()).
 *
 * Fetches TravelPixieFreak's English-language "Shades Of Human Life"
 * WordPress category RSS feed and returns it as a small JSON array for
 * assets/js/journal-carousel.js to render. This is the mechanism behind
 * journal/index.html and pl/journal/index.html's auto-syncing carousel —
 * when a new post is published in that category on travelpixiefreak.com,
 * it appears on cudexperience.com automatically, no redeploy needed.
 *
 * Source feed (verified 2026-09-11 to contain ONLY English posts — the
 * Polish "Odcienie Ludzkiego Życia" posts live in a separate WordPress
 * category and never appear here, so no language filtering is needed):
 *   https://travelpixiefreak.com/category/shades-of-human-life/feed/
 *
 * Response is cached at Cloudflare's edge (Cache API) for CACHE_TTL_
 * SECONDS so the upstream WordPress site is hit at most once per TTL
 * window regardless of visitor traffic on cudexperience.com.
 */

const FEED_URL = "https://travelpixiefreak.com/category/shades-of-human-life/feed/";
const CACHE_TTL_SECONDS = 3600; // 1 hour — new posts show up within an hour, not instantly, without hammering the upstream site on every visit.

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
    // Only accept the real domain's own links — defence in depth in case
    // the upstream feed is ever compromised or misconfigured.
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

    const cache = caches.default;
    const cacheKey = new Request("https://cudexperience.com/api/journal-cache-key");

    const cached = await cache.match(cacheKey);
    if (cached) return cached;

    let items = [];
    try {
      const res = await fetch(FEED_URL, {
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
