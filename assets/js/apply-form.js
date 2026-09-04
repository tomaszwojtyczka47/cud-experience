/* C.U.D. Origins application form — submits to the Cloudflare Worker at
   /api/apply (same origin, no CORS/CSP changes needed). Field ids below
   map 1:1 onto the Airtable column names the Worker expects — keep both
   in sync if a question is ever added, removed or reworded. */
(function () {
  var form = document.querySelector('.cud-form');
  if (!form) return;

  var isPl = (document.documentElement.lang || '').toLowerCase().indexOf('pl') === 0;
  var errorBox = document.querySelector('.cud-form-error');
  var submitBtn = form.querySelector('.cud-form-submit .cud-btn');

  var FIELD_MAP = {
    firstName: 'First Name',
    lastName: 'Last Name',
    email: 'Email',
    phone: 'Phone',
    ageRange: 'Age Range',
    travellingFrom: 'Travelling From',
    travellingWith: 'Travelling With',
    withWhom: 'With Whom (detail)',
    q1: 'Q1', q2: 'Q2', q3: 'Q3', q4: 'Q4', q5: 'Q5', q6: 'Q6',
    q7: 'Q7', q7why: 'Q7 Why', q8: 'Q8', q9: 'Q9', q10: 'Q10',
    q11: 'Q11', q12: 'Q12', q13: 'Q13', q14: 'Q14', q15: 'Q15',
    q16: 'Q16', q17: 'Q17', q18: 'Q18'
  };
  var CHECKBOX_MAP = {
    confirm1: 'Confirmation 1', confirm2: 'Confirmation 2',
    confirm3: 'Confirmation 3', confirm4: 'Confirmation 4',
    confirm5: 'Confirmation 5', privacyConsent: 'Privacy Consent'
  };

  function valueOf(id) {
    var els = form.querySelectorAll('[name="' + id + '"]');
    if (!els.length) return '';
    if (els.length === 1 && els[0].tagName !== 'INPUT') return els[0].value.trim();
    if (els[0].type === 'radio') {
      for (var i = 0; i < els.length; i++) { if (els[i].checked) return els[i].value; }
      return '';
    }
    return els[0].value.trim();
  }

  function showError() {
    if (!errorBox) return;
    errorBox.textContent = isPl
      ? 'Nie udało się wysłać aplikacji. Sprawdź połączenie i spróbuj ponownie, albo napisz bezpośrednio na contact@cudexperience.com.'
      : 'Something went wrong sending your application. Please check your connection and try again, or email contact@cudexperience.com directly.';
    errorBox.classList.add('is-visible');
    errorBox.scrollIntoView({ block: 'nearest' });
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    if (errorBox) errorBox.classList.remove('is-visible');

    if (form.querySelector('[name="website"]').value) {
      // Honeypot filled -> silently pretend success, never call the API.
      window.location.href = 'thank-you/';
      return;
    }

    var turnstileToken = window.turnstile ? window.turnstile.getResponse() : '';
    if (!turnstileToken) {
      var turnstileEl = form.querySelector('[name="cf-turnstile-response"]');
      turnstileToken = turnstileEl ? turnstileEl.value : '';
    }
    if (!turnstileToken) {
      showError();
      return;
    }

    var payload = { Language: isPl ? 'PL' : 'EN' };
    Object.keys(FIELD_MAP).forEach(function (id) { payload[FIELD_MAP[id]] = valueOf(id); });
    Object.keys(CHECKBOX_MAP).forEach(function (id) {
      var el = form.querySelector('[name="' + id + '"]');
      payload[CHECKBOX_MAP[id]] = !!(el && el.checked);
    });
    payload.website = valueOf('website');
    payload.turnstileToken = turnstileToken;

    form.classList.add('cud-form-submitting');
    if (submitBtn) submitBtn.setAttribute('aria-disabled', 'true');

    fetch('/api/apply', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    }).then(function (res) {
      return res.json().then(function (body) { return { ok: res.ok && body.ok, body: body }; });
    }).then(function (result) {
      if (result.ok) {
        window.location.href = 'thank-you/';
      } else {
        form.classList.remove('cud-form-submitting');
        if (submitBtn) submitBtn.removeAttribute('aria-disabled');
        if (window.turnstile) window.turnstile.reset();
        showError();
      }
    }).catch(function () {
      form.classList.remove('cud-form-submitting');
      if (submitBtn) submitBtn.removeAttribute('aria-disabled');
      if (window.turnstile) window.turnstile.reset();
      showError();
    });
  });
})();
