/* ---- LOADER + SCROLL REVEAL --------------------------------------------
   Loader: the C.U.D. mark stays on screen (CSS shows it from first paint,
   no flash) until the window's load event fires, then fades out - capped
   at 2.5s so a slow connection never traps a visitor behind it, and never
   shown for less than ~500ms so it doesn't just flicker on a fast one.
   Scroll reveal: sections fade/rise into place as they near the viewport,
   the same IntersectionObserver pattern already used for photo loading
   and GA4 section_view tracking. Both are skipped for prefers-reduced-
   motion, and the loader is skipped entirely if the page was restored
   from the browser's back/forward cache (nothing to wait for). --------- */
(function(){
var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

var loader = document.getElementById('cud-loader');
if(loader){
if(reduceMotion){
loader.remove();
} else {
document.documentElement.classList.add('cud-loading');
var shownAt = Date.now();
var minVisible = 500;
var maxWait = 2500;
var done = false;
var hide = function(){
if(done) return;
done = true;
loader.classList.add('is-hidden');
document.documentElement.classList.remove('cud-loading');
setTimeout(function(){ if(loader.parentNode) loader.remove(); },650);
};
var hideRespectingMinimum = function(){
var elapsed = Date.now() - shownAt;
if(elapsed >= minVisible){ hide(); } else { setTimeout(hide, minVisible - elapsed); }
};
if(document.readyState === 'complete'){
hideRespectingMinimum();
} else {
window.addEventListener('load', hideRespectingMinimum);
}
setTimeout(hide, maxWait);
}
}

if(!reduceMotion && 'IntersectionObserver' in window){
var els = document.querySelectorAll('.cud-reveal');
var io = new IntersectionObserver(function(entries, obs){
entries.forEach(function(en){
if(en.isIntersecting){
en.target.classList.add('is-visible');
obs.unobserve(en.target);
}
});
},{threshold:0.15, rootMargin:'0px 0px -60px 0px'});
els.forEach(function(el){ io.observe(el); });
}
})();
