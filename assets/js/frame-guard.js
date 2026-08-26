/* ---- CLICKJACKING DEFENSE-IN-DEPTH --------------------------------
   GitHub Pages serves no custom HTTP headers, so a real
   "Content-Security-Policy: frame-ancestors" (or X-Frame-Options)
   response header isn't possible here - only a <meta> CSP, and
   browsers explicitly ignore frame-ancestors when it appears in a
   meta tag. This client-side check is not equivalent to a real header
   (it can be bypassed by framing the page inside a sandboxed iframe
   that blocks scripts) but still stops the common case of the site
   being loaded inside someone else's frame. Runs as early as possible,
   before the rest of <head> parses. ---------------------------------- */
(function(){
try {
  if (window.top !== window.self) {
    window.top.location.href = window.self.location.href;
  }
} catch (e) {
  document.documentElement.style.display = 'none';
}
})();
