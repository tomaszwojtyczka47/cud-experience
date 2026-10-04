(function(){
var NEWSLETTER_ENABLED=false;
var f=document.querySelector('.cud-nl-form');
if(f){
var isPl=(document.documentElement.lang||'').toLowerCase().indexOf('pl')===0;
var s=document.querySelector('.cud-nl-status');
var joinBtn=f.querySelector('.cud-nl-join');
var MSG={
ok:isPl?'Dziękujemy! Zostałeś zapisany.':'Thanks! You’re on the list.',
err:isPl?'Coś poszło nie tak. Spróbuj ponownie za chwilę albo napisz na contact@cudexperience.com.':'Something went wrong. Please try again shortly, or email contact@cudexperience.com.',
turnstile:isPl?'Potwierdź, że nie jesteś robotem, i spróbuj ponownie.':'Please confirm you’re not a robot and try again.',
disabled:isPl?'Zapisy chwilowo wstrzymane. Wróć niebawem albo napisz na contact@cudexperience.com.':'Sign-ups are temporarily paused. Please check back soon, or email contact@cudexperience.com.'
};
function setStatus(msg){if(s)s.textContent=msg;}
var consentEl=f.querySelector('[name="consent"]');
function syncJoin(){
if(joinBtn&&consentEl)joinBtn.disabled=!consentEl.checked;
}
if(consentEl){
consentEl.addEventListener('change',syncJoin);
f.addEventListener('reset',function(){setTimeout(syncJoin,0);});
window.addEventListener('pageshow',syncJoin);
syncJoin();
}
if(!NEWSLETTER_ENABLED){
if(joinBtn)joinBtn.setAttribute('aria-disabled','true');
f.addEventListener('submit',function(e){
e.preventDefault();
setStatus(MSG.disabled);
});
return;
}
f.addEventListener('submit',function(e){
e.preventDefault();
setStatus('');
var websiteEl=f.querySelector('[name="website"]');
if(websiteEl&&websiteEl.value){
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
})();

(function(){
var y=document.getElementById('cud-year');
if(y){y.textContent=new Date().getFullYear();}

var NAV_MQ='(min-width:961px)';
var navs=document.querySelectorAll('.cud-nav');
navs.forEach(function(nav){
var btn=nav.querySelector('.cud-menu-btn');
if(!btn)return;
function closeMenu(){
nav.classList.remove('cud-nav-open');
btn.setAttribute('aria-expanded','false');
document.documentElement.style.overflow='';
}
btn.addEventListener('click',function(){
var open=nav.classList.toggle('cud-nav-open');
btn.setAttribute('aria-expanded',open?'true':'false');
document.documentElement.style.overflow=open?'hidden':'';
});
nav.querySelectorAll('ul a').forEach(function(a){
a.addEventListener('click',closeMenu);
});
document.addEventListener('keydown',function(e){
if(e.key==='Escape')closeMenu();
});
if(window.matchMedia){
var wide=window.matchMedia(NAV_MQ);
var onWide=function(e){if(e.matches)closeMenu();};
if(wide.addEventListener)wide.addEventListener('change',onWide);
else if(wide.addListener)wide.addListener(onWide);
}
});
})();

(function(){
var item=document.querySelector('.cud-nav .cud-has-sub');
if(!item)return;
var link=item.firstElementChild;
function active(){return item.matches(':hover')||item.contains(document.activeElement);}
function rearm(){setTimeout(function(){if(!active())item.classList.remove('cud-sub-off');},0);}
document.addEventListener('keydown',function(e){
if(e.key!=='Escape'||!active())return;
item.classList.add('cud-sub-off');
if(link&&document.activeElement!==link&&item.contains(document.activeElement))link.focus();
});
item.addEventListener('mouseleave',rearm);
item.addEventListener('focusout',rearm);
})();

(function(){
var widget=document.querySelector('.cf-turnstile');
if(!widget)return;
var started=false;
function load(){
if(started)return;
started=true;
var s=document.createElement('script');
s.src='https://challenges.cloudflare.com/turnstile/v0/api.js';
s.async=true;
s.defer=true;
document.head.appendChild(s);
}
var form=widget.closest('form');
if(form)form.addEventListener('focusin',load);
if('IntersectionObserver' in window){
var io=new IntersectionObserver(function(entries){
if(entries.some(function(en){return en.isIntersecting;})){io.disconnect();load();}
},{rootMargin:'400px 0px'});
io.observe(widget);
}else{
load();
}
})();
