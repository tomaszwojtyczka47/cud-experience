(function(){
var root = document.querySelector('[data-journal-carousel]');
var fallback = document.querySelector('[data-journal-fallback]');
if(!root) return;

var isPl = (document.documentElement.lang||'').toLowerCase().indexOf('pl')===0;
var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
var AUTOPLAY_MS = 5000;

fetch('/api/journal?lang=' + (isPl ? 'pl' : 'en')).then(function(r){
if(!r.ok) throw new Error('bad status');
return r.json();
}).then(function(data){
var items = (data && data.items) || [];
if(!items.length) return;
build(items);
}).catch(function(){});

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
var maxIndex = 0;
var paused = false;
var timer = null;

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
void track.offsetHeight;
track.style.transition = '';
}
}

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

function updateNavVisibility(){
var canScroll = maxIndex > 0;
prevBtn.hidden = !canScroll;
nextBtn.hidden = !canScroll;
}

prevBtn.addEventListener('click', function(){ go(-1); startAutoplay(); });
nextBtn.addEventListener('click', function(){ go(1); startAutoplay(); });

var swipeX = 0, swipeY = 0, swiping = false;
viewport.addEventListener('touchstart', function(e){
if(e.touches.length !== 1){ swiping = false; return; }
swipeX = e.touches[0].clientX; swipeY = e.touches[0].clientY; swiping = true; paused = true;
}, {passive: true});
viewport.addEventListener('touchend', function(e){
if(!swiping) return;
swiping = false;
var t = e.changedTouches[0];
var dx = t.clientX - swipeX, dy = t.clientY - swipeY;
if(Math.abs(dx) > 40 && Math.abs(dx) > Math.abs(dy) * 1.3){ go(dx < 0 ? 1 : -1); startAutoplay(); }
}, {passive: true});
viewport.addEventListener('touchcancel', function(){ swiping = false; }, {passive: true});

root.addEventListener('mouseenter', function(){ paused = true; });
root.addEventListener('mouseleave', function(){ paused = false; });
root.addEventListener('focusin', function(){ paused = true; });
root.addEventListener('focusout', function(){ paused = false; });

window.addEventListener('resize', function(){ measure(); setPosition(false); updateNavVisibility(); startAutoplay(); });

root.hidden = false;
if(fallback) fallback.hidden = true;
measure();
setPosition(false);
updateNavVisibility();
startAutoplay();
}
})();
