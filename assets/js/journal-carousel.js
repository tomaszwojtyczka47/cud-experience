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
var track = root.querySelector('.cud-jrl-track');
var prevBtn = root.querySelector('.cud-jrl-prev');
var nextBtn = root.querySelector('.cud-jrl-next');
var n = items.length;

items.forEach(function(item){ track.appendChild(makeCard(item)); });

var index = 0;
var cardWidth = 0;
var paused = false;
var timer = null;

function measure(){
cardWidth = track.children[0].getBoundingClientRect().width;
}

function setPosition(animate){
track.style.transition = animate ? '' : 'none';
track.style.transform = 'translateX(' + (-index * cardWidth) + 'px)';
if(!animate){
void track.offsetHeight; // force reflow so the next move re-enables the transition
track.style.transition = '';
}
}

/* index is kept in range with modulo, not by comparing against an
   exact boundary value - a modulo always produces a valid 0..n-1
   result no matter how far index has drifted for any reason, so
   there's nothing here that timing, a missed event, or an unexpected
   extra call could ever desync. The one move that visually wraps
   (last card back to first, or first back to last) jumps instantly
   instead of animating, since sliding the CSS transform the "short
   way" across the wrap wouldn't traverse the real cards in between -
   it would either jump immediately (no animation to skip) or, if
   forced to animate, visibly race backward across the whole strip.
   An instant cut once per lap reads as an intentional loop point
   rather than a glitch. */
function go(dir){
var wrapping = (dir > 0 && index === n-1) || (dir < 0 && index === 0);
index = ((index + dir) % n + n) % n;
setPosition(!wrapping);
}

function startAutoplay(){
if(reduceMotion || n<2) return;
stopAutoplay();
timer = setInterval(function(){ if(!paused) go(1); }, AUTOPLAY_MS);
}
function stopAutoplay(){
if(timer){ clearInterval(timer); timer = null; }
}

prevBtn.addEventListener('click', function(){ go(-1); startAutoplay(); });
nextBtn.addEventListener('click', function(){ go(1); startAutoplay(); });
if(n<2){ prevBtn.hidden = true; nextBtn.hidden = true; }

root.addEventListener('mouseenter', function(){ paused = true; });
root.addEventListener('mouseleave', function(){ paused = false; });
root.addEventListener('focusin', function(){ paused = true; });
root.addEventListener('focusout', function(){ paused = false; });

window.addEventListener('resize', function(){ measure(); setPosition(false); });

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
startAutoplay();
}
})();
