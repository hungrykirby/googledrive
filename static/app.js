const grid = document.getElementById('grid');
const modal = document.getElementById('modal');
const modalImg = document.getElementById('modal-img');
const countEl = document.getElementById('count');

async function load() {
  const res = await fetch('/api/images');
  const data = await res.json();
  countEl.textContent = `${data.images.length}枚`;
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
    tile.addEventListener('click', () => openImage(item.name, tile));
    frag.appendChild(tile);
  }
  grid.appendChild(frag);
}

function openImage(name, tile) {
  modalImg.src = `/image/${encodeURIComponent(name)}`;
  modal.classList.remove('hidden');
  if (tile && tile.parentNode === grid && grid.firstChild !== tile) {
    grid.insertBefore(tile, grid.firstChild);
  }
  fetch(`/api/viewed/${encodeURIComponent(name)}`, { method: 'POST' }).catch(() => {});
}

function closeImage() {
  modal.classList.add('hidden');
  modalImg.src = '';
}

modal.addEventListener('click', closeImage);
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeImage();
});

load();
