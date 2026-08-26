/* ---- GOOGLE CONSENT MODE: DEFAULT DENIED --------------------------
   Must be the very first script on the page, before the consent banner
   and before gtag.js itself. Without this, gtag('config',...) fires
   with no consent state at all and Google Analytics sends a hit
   immediately on page load, before the visitor has made any choice.
   Secure Privacy reads this default and calls gtag('consent','update',
   ...) once the visitor accepts or declines. ----------------------- */
window.dataLayer = window.dataLayer || [];
function gtag(){dataLayer.push(arguments);}
gtag('consent', 'default', {
  'ad_storage': 'denied',
  'ad_user_data': 'denied',
  'ad_personalization': 'denied',
  'analytics_storage': 'denied',
  'wait_for_update': 2000
});
