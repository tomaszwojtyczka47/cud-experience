/*
 * C.U.D. Experience — application form receiver.
 *
 * Deployed as a Cloudflare Worker on Route: cudexperience.com/api/apply
 * (same origin as the site — no CORS handling needed, and the existing
 * per-page CSP `connect-src 'self'` already covers the browser fetch()).
 *
 * Receives the JSON payload built by assets/js/apply-form.js, does minimal
 * validation + spam filtering, and writes one record into Airtable.
 *
 * Required Worker Secrets (set via the Cloudflare dashboard, never in this
 * file or in git): AIRTABLE_TOKEN, AIRTABLE_BASE_ID, AIRTABLE_TABLE,
 * TURNSTILE_SECRET_KEY.
 *
 * Airtable field names this expects to already exist in the target table
 * are documented in full in the project plan / CLAUDE.md — every key in
 * `fields` below must match an existing Airtable column name exactly.
 */

const TRIP_LABEL = "C.U.D. Origins — Hoi An, 20-30 March 2027";

const REQUIRED_FIELDS = [
  "First Name", "Last Name", "Email", "Phone", "Age Range",
  "Travelling From", "Travelling With",
  "Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "Q7 Why", "Q8", "Q9", "Q10",
  "Q11", "Q12", "Q13", "Q14", "Q15", "Q16", "Q17",
  "Confirmation 1", "Confirmation 2", "Confirmation 3", "Confirmation 4",
  "Confirmation 5", "Privacy Consent"
];

function json(body, status) {
  return new Response(JSON.stringify(body), {
    status: status || 200,
    headers: { "Content-Type": "application/json" }
  });
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

    // Honeypot: a real applicant never fills this hidden field. Bots that
    // blindly fill every input do. Reply 200 so the bot doesn't learn
    // anything, but never write a record.
    if (data.website) {
      return json({ ok: true });
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

    for (const key of REQUIRED_FIELDS) {
      if (!data[key] || String(data[key]).trim() === "") {
        return json({ ok: false, error: "missing_field", field: key }, 400);
      }
      if (String(data[key]).length > 5000) {
        return json({ ok: false, error: "field_too_long", field: key }, 400);
      }
    }

    const fields = {
      "Trip": TRIP_LABEL,
      "Language": data.Language === "PL" ? "PL" : "EN",
      "First Name": data["First Name"],
      "Last Name": data["Last Name"],
      "Email": data["Email"],
      "Phone": data["Phone"],
      "Age Range": data["Age Range"],
      "Travelling From": data["Travelling From"],
      "Travelling With": data["Travelling With"],
      "With Whom (detail)": data["With Whom (detail)"] || "",
      "Q1": data["Q1"], "Q2": data["Q2"], "Q3": data["Q3"], "Q4": data["Q4"],
      "Q5": data["Q5"], "Q6": data["Q6"], "Q7": data["Q7"],
      "Q7 Why": data["Q7 Why"], "Q8": data["Q8"], "Q9": data["Q9"],
      "Q10": data["Q10"], "Q11": data["Q11"], "Q12": data["Q12"],
      "Q13": data["Q13"], "Q14": data["Q14"], "Q15": data["Q15"],
      "Q16": data["Q16"], "Q17": data["Q17"], "Q18": data["Q18"] || "",
      "Confirmation 1": !!data["Confirmation 1"],
      "Confirmation 2": !!data["Confirmation 2"],
      "Confirmation 3": !!data["Confirmation 3"],
      "Confirmation 4": !!data["Confirmation 4"],
      "Confirmation 5": !!data["Confirmation 5"],
      "Privacy Consent": !!data["Privacy Consent"],
      "Status": "New"
    };

    const airtableUrl = "https://api.airtable.com/v0/" + env.AIRTABLE_BASE_ID + "/" + encodeURIComponent(env.AIRTABLE_TABLE);

    let airtableRes;
    try {
      airtableRes = await fetch(airtableUrl, {
        method: "POST",
        headers: {
          "Authorization": "Bearer " + env.AIRTABLE_TOKEN,
          "Content-Type": "application/json"
        },
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
