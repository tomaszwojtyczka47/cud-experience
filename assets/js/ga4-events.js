/* ---- GA4 EVENTS -----------------------------------------------------
   One-page site, so page views say almost nothing: every visit is one
   view. These events record what people actually do - which buttons
   they press, which trips they open, how far down they get. They ride
   on the same gtag the consent script above installs. --------------- */
(function(){
function ev(n,p){ if(typeof window.gtag==='function'){ window.gtag('event',n,p||{}); } }
function txt(el){ return el ? (el.textContent||'').replace(/\s+/g,' ').trim().slice(0,60) : ''; }
document.addEventListener('click',function(e){
var j=e.target.closest('.cud-nl-join');
if(j){ ev('newsletter_join_click'); return; }
var a=e.target.closest('a'); if(!a) return;
var href=a.getAttribute('href')||'';
if(a.classList.contains('cud-card')){ ev('experience_card_click',{card:txt(a.querySelector('.cud-h3'))}); return; }
if(a.classList.contains('cud-ev')){ ev('upcoming_trip_click',{trip:txt(a.querySelector('h5'))}); return; }
if(a.closest('.cud-ft-ic')){ ev('social_click',{network:a.getAttribute('aria-label')||''}); return; }
if(a.closest('.cud-nav')){ ev('nav_click',{link_text:txt(a),target:href}); return; }
if(a.closest('.cud-ft-nav')){ ev('footer_nav_click',{link_text:txt(a)}); return; }
if(a.classList.contains('cud-btn')){ ev('cta_click',{cta:txt(a),target:href}); return; }
},true);
if('IntersectionObserver' in window){
var seen={};
var io=new IntersectionObserver(function(en){en.forEach(function(x){
var id=x.target.getAttribute('id')||'';
if(x.isIntersecting&&id&&!seen[id]){seen[id]=1;ev('section_view',{section:id});}
});},{threshold:0.35});
['about','philosophy','experiences','journal','apply','contact'].forEach(function(id){
var el=document.getElementById(id); if(el){ io.observe(el); }
});
}
})();
