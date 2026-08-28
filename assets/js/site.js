/* Honest placeholder behaviour: the newsletter has no backend yet, so
   this tells a real or keyboard/screen-reader user that plainly instead
   of silently doing nothing. Swap for a real form action (e.g. a
   Formspree endpoint) once a provider is connected. */
(function(){
var f=document.querySelector('.cud-nl-form');
if(f){
f.addEventListener('submit',function(e){
e.preventDefault();
var s=document.querySelector('.cud-nl-status');
var isPl=(document.documentElement.lang||'').toLowerCase().indexOf('pl')===0;
if(s)s.textContent=isPl?'Dzi\u0119kujemy! Zapisy nie s\u0105 jeszcze aktywne \u2014 zajrzyj tu wkr\u00f3tce.':'Thanks! Sign-ups aren\u2019t live yet \u2014 please check back soon.';
});
}
/* Copyright year keeps itself current without ever needing an edit. */
var y=document.getElementById('cud-year');
if(y){y.textContent=new Date().getFullYear();}

/* Mobile nav: hamburger toggles the existing <ul> as a full-screen menu. */
var navs=document.querySelectorAll('.cud-nav');
navs.forEach(function(nav){
var btn=nav.querySelector('.cud-menu-btn');
if(!btn)return;
function closeMenu(){
nav.classList.remove('cud-nav-open');
btn.setAttribute('aria-expanded','false');
document.body.style.overflow='';
}
btn.addEventListener('click',function(){
var open=nav.classList.toggle('cud-nav-open');
btn.setAttribute('aria-expanded',open?'true':'false');
document.body.style.overflow=open?'hidden':'';
});
nav.querySelectorAll('ul a').forEach(function(a){
a.addEventListener('click',closeMenu);
});
document.addEventListener('keydown',function(e){
if(e.key==='Escape')closeMenu();
});
});
})();
