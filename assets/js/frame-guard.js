/* ---- CLICKJACKING DEFENSE-IN-DEPTH --------------------------------
   Cloudflare now sends real X-Frame-Options and CSP frame-ancestors
   response headers in front of this origin, so this script is a
   redundant second layer, not the only defense. Kept in case the site
   is ever reached with those headers stripped (e.g. a misconfigured
   proxy). Not equivalent to a real header on its own - it can be
   bypassed by framing the page inside a sandboxed iframe that blocks
   scripts - but still stops the common case. Runs as early as
   possible, before the rest of <head> parses. ------------------------ */
(function(){
try {
  if (window.top !== window.self) {
    window.top.location.href = window.self.location.href;
  }
} catch (e) {
  document.documentElement.style.display = 'none';
}
})();
