/*
 * C.U.D. Experience — newsletter sign-up receiver.
 *
 * Deployed as a Cloudflare Worker on Route: cudexperience.com/api/newsletter
 * (same origin as the site — no CORS handling needed, and the existing
 * per-page CSP `connect-src 'self'` already covers the browser fetch()).
 *
 * Receives the small JSON payload built by the newsletter form handler in
 * assets/js/site.js (home page, EN + PL), verifies the Turnstile token,
 * and writes one subscriber record into Airtable — the same base the
 * application form uses (worker/apply.js), but its own table.
 *
 * Signing up twice with the same address is harmless: the Worker looks
 * the address up first and, if it is already on the list, replies with
 * success without creating a second record (and without revealing to the
 * browser whether the address was already subscribed).
 *
 * Required Worker Secrets (set via the Cloudflare dashboard, never in this
 * file or in git): AIRTABLE_TOKEN, AIRTABLE_BASE_ID, AIRTABLE_NEWSLETTER_TABLE,
 * TURNSTILE_SECRET_KEY. AIRTABLE_TOKEN / AIRTABLE_BASE_ID / TURNSTILE_SECRET_KEY
 * can hold the same values as the apply Worker's; the token needs
 * data.records:read + data.records:write on the base.
 *
 * Airtable columns this expects to already exist in the newsletter table
 * (names must match exactly):
 *   Email          — Email (primary field)
 *   Language       — Single select: EN, PL
 *   Source         — Single line text (page path the form was sent from)
 *   Consent        — Checkbox
 *   Subscribed At  — Date with time (ISO 8601, UTC)
 *   Status         — Single select: Subscribed, Unsubscribed
 */

const MAX_EMAIL_LENGTH = 254;
// Deliberately permissive: one "@", no whitespace, a dot in the domain.
// The browser's type="email" check runs first; this only stops garbage.
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function json(body, status) {
  return new Response(JSON.stringify(body), {
    status: status || 200,
    headers: { "Content-Type": "application/json" }
  });
}

function tableUrl(env) {
  return "https://api.airtable.com/v0/" + env.AIRTABLE_BASE_ID + "/" + encodeURIComponent(env.AIRTABLE_NEWSLETTER_TABLE);
}

export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return json({ ok: false, error: "method_not_allowed" }, 405);
    }

    let data;
    try {
      data = await request.json();
    } catch (e) {
      return json({ ok: false, error: "invalid_json" }, 400);
    }

    // Honeypot: a real visitor never fills this hidden field. Reply 200 so
    // the bot doesn't learn anything, but never write a record.
    if (data.website) {
      return json({ ok: true });
    }

    const email = String(data.email || "").trim().toLowerCase();
    if (!email || email.length > MAX_EMAIL_LENGTH || !EMAIL_RE.test(email)) {
      return json({ ok: false, error: "invalid_email" }, 400);
    }

    if (!data.turnstileToken) {
      return json({ ok: false, error: "missing_turnstile_token" }, 400);
    }

    const verifyRes = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        secret: env.TURNSTILE_SECRET_KEY,
        response: data.turnstileToken,
        remoteip: request.headers.get("CF-Connecting-IP") || ""
      })
    });
    const verifyBody = await verifyRes.json();
    if (!verifyBody.success) {
      return json({ ok: false, error: "turnstile_failed" }, 403);
    }

    const authHeaders = {
      "Authorization": "Bearer " + env.AIRTABLE_TOKEN,
      "Content-Type": "application/json"
    };

    // Already on the list? Airtable formulas quote strings with "…", so
    // escape backslashes and quotes in the address before embedding it.
    const quoted = '"' + email.replace(/\\/g, "\\\\").replace(/"/g, '\\"') + '"';
    const lookupUrl = tableUrl(env) + "?maxRecords=1&fields%5B%5D=Email&filterByFormula=" +
      encodeURIComponent("LOWER({Email})=" + quoted);

    let lookupRes;
    try {
      lookupRes = await fetch(lookupUrl, { headers: authHeaders });
    } catch (e) {
      return json({ ok: false, error: "airtable_unreachable" }, 502);
    }
    if (!lookupRes.ok) {
      return json({ ok: false, error: "airtable_rejected", status: lookupRes.status }, 502);
    }
    const lookupBody = await lookupRes.json();
    if (lookupBody.records && lookupBody.records.length) {
      return json({ ok: true });
    }

    const source = String(data.source || "").slice(0, 200);
    const fields = {
      "Email": email,
      "Language": data.language === "PL" ? "PL" : "EN",
      "Source": source,
      "Consent": true,
      "Subscribed At": new Date().toISOString(),
      "Status": "Subscribed"
    };

    let airtableRes;
    try {
      airtableRes = await fetch(tableUrl(env), {
        method: "POST",
        headers: authHeaders,
        body: JSON.stringify({ fields, typecast: true })
      });
    } catch (e) {
      return json({ ok: false, error: "airtable_unreachable" }, 502);
    }

    if (!airtableRes.ok) {
      return json({ ok: false, error: "airtable_rejected", status: airtableRes.status }, 502);
    }

    return json({ ok: true });
  }
};
