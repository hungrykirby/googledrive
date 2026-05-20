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

function openItem(item, tile) {
  const url = `/image/${encodeURIComponent(item.name)}`;
  if (item.type === 'pdf') {
    modalImg.hidden = true;
    modalImg.src = '';
    modalPdf.src = url;
    modalPdf.hidden = false;
  } else {
    modalPdf.hidden = true;
    modalPdf.src = '';
    modalImg.src = url;
    modalImg.hidden = false;
  }
  modal.classList.remove('hidden');
  if (tile && tile.parentNode === grid && grid.firstChild !== tile) {
    grid.insertBefore(tile, grid.firstChild);
  }
  fetch(`/api/viewed/${encodeURIComponent(item.name)}`, { method: 'POST' }).catch(() => {});
}

function closeModal() {
  modal.classList.add('hidden');
  modalImg.src = '';
  modalPdf.src = '';
}

modal.addEventListener('click', (e) => {
  if (e.target === modal) closeModal();
});
modalClose.addEventListener('click', closeModal);
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !modal.classList.contains('hidden')) closeModal();
});

load();
