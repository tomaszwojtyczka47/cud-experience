/* Journal carousel (journal/index.html, pl/journal/index.html) — fetches
   the Worker-proxied TravelPixieFreak "Shades of Human Life" feed
   (see worker/journal.js) and renders it as an auto-advancing, looping
   carousel. If the fetch fails or returns no items, the page's existing
   static "First stories coming soon" panel is left exactly as-is — this
   file never touches it unless real articles are available. Card text
   is inserted via textContent (not innerHTML): the feed is third-party
   content, so it's treated as untrusted data, never as markup. */
(function(){
var root = document.querySelector('[data-journal-carousel]');
var fallback = document.querySelector('[data-journal-fallback]');
if(!root) return;

var isPl = (document.documentElement.lang||'').toLowerCase().indexOf('pl')===0;
var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
var AUTOPLAY_MS = 5000;

fetch('/api/journal').then(function(r){
if(!r.ok) throw new Error('bad status');
return r.json();
}).then(function(data){
var items = (data && data.items) || [];
if(!items.length) return;
build(items);
}).catch(function(){ /* leave the static fallback panel untouched */ });

function truncate(s, n){
if(!s) return '';
s = s.trim();
if(s.length<=n) return s;
var cut = s.slice(0,n);
var lastSpace = cut.lastIndexOf(' ');
return (lastSpace>40 ? cut.slice(0,lastSpace) : cut) + '…';
}

function formatDate(pubDate){
var d = new Date(pubDate);
if(isNaN(d.getTime())) return '';
return d.toLocaleDateString(isPl?'pl-PL':'en-US', {year:'numeric', month:'long', day:'numeric'});
}

function makeCard(item){
var a = document.createElement('a');
a.className = 'cud-jrl-card';
a.href = item.link;
a.target = '_blank';
a.rel = 'noopener';

var inner = document.createElement('span');
inner.className = 'cud-jrl-card-in';

var date = document.createElement('span');
date.className = 'cud-jrl-date';
date.textContent = formatDate(item.pubDate);

var h = document.createElement('span');
h.className = 'cud-jrl-h';
h.textContent = item.title;

var ex = document.createElement('span');
ex.className = 'cud-jrl-ex';
ex.textContent = truncate(item.excerpt, 140);

var link = document.createElement('span');
link.className = 'cud-jrl-link';
link.textContent = (isPl ? 'Czytaj na TravelPixieFreak' : 'Read on TravelPixieFreak') + ' →';

inner.appendChild(date);
inner.appendChild(h);
inner.appendChild(ex);
inner.appendChild(link);
a.appendChild(inner);
return a;
}

function build(items){
var viewport = root.querySelector('.cud-jrl-viewport');
var track = root.querySelector('.cud-jrl-track');
var prevBtn = root.querySelector('.cud-jrl-prev');
var nextBtn = root.querySelector('.cud-jrl-next');
var n = items.length;

items.forEach(function(item){ track.appendChild(makeCard(item)); });

var index = 0;
var cardWidth = 0;
var maxIndex = 0; // last index that still shows a full row of real cards - see measure()
var paused = false;
var timer = null;

/* The CSS shows 1/2/3 cards at once depending on breakpoint
   (.cud-jrl-card is 100%/50%/33.3333% wide - see style.css). Stepping
   the index all the way to n-1 like a single-card carousel would, on
   a 3-per-view layout, leave the last 1-2 slots trailing off the end
   of the track with nothing to show - real, reported bug: after the
   final real card ("Shades of Human Life #4" in the current 10-item
   feed) the following slide(s) render blank instead of wrapping.
   maxIndex stops advancing once one more step would no longer have a
   full row of real cards behind it, so every position the carousel
   can reach is always fully populated. */
function measure(){
cardWidth = track.children[0].getBoundingClientRect().width;
var perView = cardWidth ? Math.max(1, Math.round(viewport.getBoundingClientRect().width / cardWidth)) : 1;
maxIndex = Math.max(0, n - perView);
if(index > maxIndex) index = maxIndex;
}

function setPosition(animate){
track.style.transition = animate ? '' : 'none';
track.style.transform = 'translateX(' + (-index * cardWidth) + 'px)';
if(!animate){
void track.offsetHeight; // force reflow so the next move re-enables the transition
track.style.transition = '';
}
}

/* Wraps at maxIndex/0 (the real usable range - see measure()) rather
   than n-1/0, so the carousel never scrolls past the last full row of
   real cards. The wrapping move (last position back to first, or
   first back to last) jumps instantly instead of animating, since
   sliding the CSS transform the "short way" across the wrap wouldn't
   traverse the real cards in between - it would either jump
   immediately (no animation to skip) or, if forced to animate,
   visibly race backward across the whole strip. An instant cut once
   per lap reads as an intentional loop point rather than a glitch. */
function go(dir){
if(maxIndex <= 0) return;
var wrapping = (dir > 0 && index >= maxIndex) || (dir < 0 && index <= 0);
if(wrapping){
index = dir > 0 ? 0 : maxIndex;
} else {
index += dir;
}
setPosition(!wrapping);
}

function startAutoplay(){
if(reduceMotion || maxIndex<=0) return;
stopAutoplay();
timer = setInterval(function(){ if(!paused) go(1); }, AUTOPLAY_MS);
}
function stopAutoplay(){
if(timer){ clearInterval(timer); timer = null; }
}

/* maxIndex depends on how many cards fit per view, which changes
   across the 1/2/3-per-view breakpoints - so whether prev/next make
   sense at all can change on resize too (e.g. all 10 cards might fit
   in one row on a very wide screen). */
function updateNavVisibility(){
var canScroll = maxIndex > 0;
prevBtn.hidden = !canScroll;
nextBtn.hidden = !canScroll;
}

prevBtn.addEventListener('click', function(){ go(-1); startAutoplay(); });
nextBtn.addEventListener('click', function(){ go(1); startAutoplay(); });

root.addEventListener('mouseenter', function(){ paused = true; });
root.addEventListener('mouseleave', function(){ paused = false; });
root.addEventListener('focusin', function(){ paused = true; });
root.addEventListener('focusout', function(){ paused = false; });

window.addEventListener('resize', function(){ measure(); setPosition(false); updateNavVisibility(); startAutoplay(); });

/* Un-hide first, then measure: getBoundingClientRect() on a card that's
   still inside a hidden ancestor always reports 0 width (a [hidden]
   subtree isn't rendered), and a requestAnimationFrame callback is the
   wrong way to sequence around that - rAF is paused for backgrounded
   tabs (e.g. a link opened in a new background tab), which would leave
   the carousel permanently hidden behind the fallback panel for that
   visitor. Reading layout geometry forces a synchronous reflow on its
   own, so no rAF/timeout is needed here at all. */
root.hidden = false;
if(fallback) fallback.hidden = true;
measure();
setPosition(false);
updateNavVisibility();
startAutoplay();
}
})();
