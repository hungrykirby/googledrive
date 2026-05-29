const grid = document.getElementById('grid');
const modal = document.getElementById('modal');
const modalImg = document.getElementById('modal-img');
const modalPdf = document.getElementById('modal-pdf');
const modalClose = document.getElementById('modal-close');
const countEl = document.getElementById('count');

async function load() {
  const res = await fetch('/api/images');
  const data = await res.json();
  countEl.textContent = `${data.images.length}件`;
  const frag = document.createDocumentFragment();
  for (const item of data.images) {
    const tile = document.createElement('div');
    tile.className = 'tile';
    const img = document.createElement('img');
    img.loading = 'lazy';
    img.decoding = 'async';
    img.src = `/thumb/${encodeURIComponent(item.name)}`;
    img.alt = item.name;
    tile.appendChild(img);
    tile.addEventListener('click', () => openItem(item, tile));
    frag.appendChild(tile);
  }
  grid.appendChild(frag);
}

const MODAL_HASH = '#image';
const BLANK_PDF = 'about:blank';

function openItem(item, tile) {
  const url = `/image/${encodeURIComponent(item.name)}`;
  if (item.type === 'pdf') {
    modalImg.hidden = true;
    modalImg.removeAttribute('src');
    modalPdf.src = url;
    modalPdf.hidden = false;
  } else {
    modalPdf.hidden = true;
    modalPdf.src = BLANK_PDF;
    modalImg.src = url;
    modalImg.hidden = false;
  }
  modal.classList.remove('hidden');
  if (location.hash !== MODAL_HASH) {
    location.hash = MODAL_HASH.slice(1);
  }
  if (tile && tile.parentNode === grid && grid.firstChild !== tile) {
    grid.insertBefore(tile, grid.firstChild);
  }
  fetch(`/api/viewed/${encodeURIComponent(item.name)}`, { method: 'POST' }).catch(() => {});
}

function closeModal({ fromBack = false } = {}) {
  if (modal.classList.contains('hidden')) return;
  modal.classList.add('hidden');
  modalImg.removeAttribute('src');
  modalPdf.src = BLANK_PDF;
  if (!fromBack && location.hash === MODAL_HASH) {
    history.back();
  }
}

modal.addEventListener('click', (e) => {
  if (e.target === modal) closeModal();
});
modalClose.addEventListener('click', () => closeModal());
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !modal.classList.contains('hidden')) closeModal();
});
window.addEventListener('hashchange', () => {
  if (location.hash !== MODAL_HASH && !modal.classList.contains('hidden')) {
    closeModal({ fromBack: true });
  }
});

if (location.hash === MODAL_HASH) {
  history.replaceState(null, '', location.pathname + location.search);
}

load();
