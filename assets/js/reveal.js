(function(){
var loader = document.getElementById('cud-loader');
if(!loader) return;
var root = document.documentElement;
if(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches){
loader.remove();
return;
}
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
