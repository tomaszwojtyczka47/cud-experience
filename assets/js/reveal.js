/* ---- LOADER ------------------------------------------------------------
   The C.U.D. mark overlay is for slow loads only. It stays invisible (CSS)
   and a page that is ready quickly never shows it - the overlay is simply
   removed. It is switched on only when the photos of the first screen (the
   hero, or any image that is mostly in view) are still arriving SHOW_AFTER
   ms after the navigation began, and then stays up until they are in. Once
   shown it stays at least MIN_VISIBLE ms so it never just flashes, and at
   most MAX_VISIBLE ms so a stalled request never traps a visitor. Without
   JavaScript, or with prefers-reduced-motion, it is never shown. -------- */
(function(){
var loader = document.getElementById('cud-loader');
if(!loader) return;
var root = document.documentElement;
if(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches){
loader.remove();
return;
}
/* 2s: on the connections measured (Wi-Fi, LTE, 4G, even a throttled slow-4G
   phone) the hero is in within ~0.1-1.5s, so only a clearly slow load
   reaches it. */
var SHOW_AFTER = 2000;
var MIN_VISIBLE = 600;
var MAX_VISIBLE = 2500;
var showTimer = 0;
var shownAt = 0;
var finished = false;
var pending = 0;

var finish = function(){
if(finished) return;
finished = true;
clearTimeout(showTimer);
if(!shownAt){ loader.remove(); return; }
loader.classList.add('is-done');
root.classList.remove('cud-loading');
setTimeout(function(){ if(loader.parentNode) loader.remove(); },650);
};
var show = function(){
if(finished || shownAt) return;
shownAt = Date.now();
root.classList.add('cud-loading');
loader.classList.add('is-on');
setTimeout(finish, MAX_VISIBLE);
};
var ready = function(){
if(finished) return;
var wait = shownAt ? MIN_VISIBLE - (Date.now() - shownAt) : 0;
if(wait > 0){ setTimeout(finish, wait); } else { finish(); }
};

/* "Ready" means the photos the visitor sees first are in, not the window
   load event: load also waits for analytics, the consent banner and every
   lazy image already requested. */
var vw = window.innerWidth || root.clientWidth;
var vh = window.innerHeight || root.clientHeight;
var onFirstScreen = function(img){
var r = img.getBoundingClientRect();
if(!r.width || !r.height) return false;
var w = Math.min(r.right, vw) - Math.max(r.left, 0);
var h = Math.min(r.bottom, vh) - Math.max(r.top, 0);
return w > 0 && h > 0 && (w * h) / (r.width * r.height) >= 0.5;
};
Array.prototype.forEach.call(document.images, function(img){
if(img.complete || !onFirstScreen(img)) return;
pending++;
var settled = false;
var settle = function(){
if(settled) return;
settled = true;
pending--;
if(!pending) ready();
};
img.addEventListener('load', function(){
if(img.decode){ img.decode().then(settle, settle); } else { settle(); }
});
img.addEventListener('error', settle);
});

if(!pending){
finish();
} else {
var elapsed = window.performance && performance.now ? performance.now() : 0;
var delay = SHOW_AFTER - elapsed;
if(delay > 0){ showTimer = setTimeout(show, delay); } else { show(); }
}
})();

/* ---- SCROLL REVEAL -----------------------------------------------------
   Sections fade/rise into place as they near the viewport, the same
   IntersectionObserver pattern already used for photo loading and GA4
   section_view tracking. Skipped for prefers-reduced-motion. ------------ */
(function(){
var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
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
