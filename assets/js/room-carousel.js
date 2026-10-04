(function(){
var dialog = document.querySelector('.cud-room-dialog');
if(!dialog) return;

function wireCarousel(root){
var track = root.querySelector('.cud-space-car-track');
var prev = root.querySelector('.cud-space-car-prev');
var next = root.querySelector('.cud-space-car-next');
if(!track || !prev || !next) return;
function go(dir){
track.scrollBy({left: dir*track.clientWidth, behavior: 'auto'});
}
prev.addEventListener('click', function(e){ e.stopPropagation(); go(-1); });
next.addEventListener('click', function(e){ e.stopPropagation(); go(1); });
}

var wired = new WeakSet();
function wireOnce(root){
if(wired.has(root)) return;
wired.add(root);
wireCarousel(root);
}

document.querySelectorAll('.cud-space-carousel').forEach(wireOnce);
wireOnce(dialog.querySelector('.cud-room-dialog-media'));

var dialogTrack = dialog.querySelector('.cud-space-car-track');
var dialogNo = dialog.querySelector('.cud-room-dialog-no');
var dialogLoc = dialog.querySelector('.cud-room-dialog-loc');
var dialogTitle = dialog.querySelector('.cud-room-dialog-title');
var dialogTag = dialog.querySelector('.cud-room-dialog-tag');
var dialogDesc = dialog.querySelector('.cud-room-dialog-desc');
var dialogFeat = dialog.querySelector('.cud-room-dialog-feat');
var dialogMeta = dialog.querySelector('.cud-room-dialog-meta');
var dialogPrice = dialog.querySelector('.cud-room-dialog-price');
var lastTrigger = null;

function text(card, sel){
var el = card.querySelector(sel);
return el ? el.textContent : '';
}

function openRoom(card, trigger){
lastTrigger = trigger;
dialogTrack.innerHTML = '';
card.querySelectorAll('.cud-space-car-slide').forEach(function(s){
dialogTrack.appendChild(s.cloneNode(true));
});
dialogTrack.querySelectorAll('source').forEach(function(src){
src.sizes = '(min-width: 980px) 450px, (min-width: 701px) 46vw, 92vw';
});
dialogTrack.scrollLeft = 0;
dialogNo.textContent = text(card, '.cud-space-no');
dialogLoc.textContent = text(card, '.cud-space-loc');
dialogTitle.textContent = text(card, 'h3');
dialogTag.textContent = text(card, '.cud-space-tag');
dialogDesc.textContent = text(card, '.cud-space-full');
dialogFeat.textContent = text(card, '.cud-space-feat');
dialogMeta.textContent = text(card, '.cud-space-meta');
dialogPrice.innerHTML = card.querySelector('.cud-space-price') ? card.querySelector('.cud-space-price').innerHTML : '';
document.documentElement.style.overflow = 'hidden';
dialog.showModal();
}

document.querySelectorAll('.cud-space').forEach(function(card){
var openBtn = card.querySelector('.cud-space-open');
var photoArea = card.querySelector('.cud-space-ph');
if(!openBtn || !photoArea) return;
openBtn.addEventListener('click', function(){ openRoom(card, openBtn); });
photoArea.addEventListener('click', function(e){
if(e.target.closest('.cud-space-car-btn')) return;
openRoom(card, openBtn);
});
});

function finishClose(){
document.documentElement.style.overflow = '';
if(lastTrigger){ var t = lastTrigger; lastTrigger = null; t.focus(); }
}

var closeBtn = dialog.querySelector('.cud-room-dialog-close');
if(closeBtn) closeBtn.addEventListener('click', function(){ finishClose(); dialog.close(); });
dialog.addEventListener('click', function(e){
if(e.target === dialog){ finishClose(); dialog.close(); }
});
dialog.addEventListener('keydown', function(e){
if(e.key === 'Escape'){ finishClose(); }
});
dialog.addEventListener('close', finishClose);
})();
