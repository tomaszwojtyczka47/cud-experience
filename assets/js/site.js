/* Newsletter sign-up: submits to the Cloudflare Worker at /api/newsletter
   (same origin, no CORS/CSP changes needed beyond allow-listing
   challenges.cloudflare.com for the Turnstile widget/script). See
   worker/newsletter.js for the receiving side and required secrets. */
(function(){
var f=document.querySelector('.cud-nl-form');
if(f){
var isPl=(document.documentElement.lang||'').toLowerCase().indexOf('pl')===0;
var s=document.querySelector('.cud-nl-status');
var joinBtn=f.querySelector('.cud-nl-join');
var MSG={
ok:isPl?'Dziękujemy! Zostałeś zapisany.':'Thanks! You’re on the list.',
err:isPl?'Coś poszło nie tak. Spróbuj ponownie za chwilę albo napisz na contact@cudexperience.com.':'Something went wrong. Please try again shortly, or email contact@cudexperience.com.',
turnstile:isPl?'Potwierdź, że nie jesteś robotem, i spróbuj ponownie.':'Please confirm you’re not a robot and try again.'
};
function setStatus(msg){if(s)s.textContent=msg;}
f.addEventListener('submit',function(e){
e.preventDefault();
setStatus('');
var websiteEl=f.querySelector('[name="website"]');
if(websiteEl&&websiteEl.value){
// Honeypot filled -> silently pretend success, never call the API.
setStatus(MSG.ok);
f.reset();
return;
}
var emailEl=f.querySelector('[name="email"]');
var email=emailEl?emailEl.value.trim():'';
if(!email)return;
var turnstileToken=window.turnstile?window.turnstile.getResponse():'';
if(!turnstileToken){
var turnstileEl=f.querySelector('[name="cf-turnstile-response"]');
turnstileToken=turnstileEl?turnstileEl.value:'';
}
if(!turnstileToken){
setStatus(MSG.turnstile);
return;
}
if(joinBtn)joinBtn.setAttribute('aria-disabled','true');
fetch('/api/newsletter',{
method:'POST',
headers:{'Content-Type':'application/json'},
body:JSON.stringify({
email:email,
language:isPl?'PL':'EN',
source:location.pathname,
website:websiteEl?websiteEl.value:'',
turnstileToken:turnstileToken
})
}).then(function(res){
return res.json().then(function(body){return {ok:res.ok&&body.ok};});
}).then(function(result){
if(joinBtn)joinBtn.removeAttribute('aria-disabled');
if(window.turnstile)window.turnstile.reset();
if(result.ok){
setStatus(MSG.ok);
f.reset();
}else{
setStatus(MSG.err);
}
}).catch(function(){
if(joinBtn)joinBtn.removeAttribute('aria-disabled');
if(window.turnstile)window.turnstile.reset();
setStatus(MSG.err);
});
});
}
/* Copyright year keeps itself current without ever needing an edit. */
var y=document.getElementById('cud-year');
if(y){y.textContent=new Date().getFullYear();}

/* Mobile nav: hamburger toggles the existing <ul> as a full-screen menu. */
var navs=document.querySelectorAll('.cud-nav, .cud-pv-nav');
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
