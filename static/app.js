const grid = document.getElementById('grid');
const modal = document.getElementById('modal');
const modalImg = document.getElementById('modal-img');
const modalVideo = document.getElementById('modal-video');
const modalScroll = document.getElementById('modal-scroll');
const modalClose = document.getElementById('modal-close');
const pageIndicator = document.getElementById('page-indicator');
const countEl = document.getElementById('count');

const MODAL_HASH = '#image';
// 開いている最中に閉じられた場合、あとから届いた fetch で描画しないための世代番号
let openToken = 0;

async function load() {
  const res = await fetch('/api/items');
  const data = await res.json();
  countEl.textContent = `${data.items.length}件`;
  const frag = document.createDocumentFragment();
  for (const item of data.items) {
    frag.appendChild(buildTile(item));
  }
  grid.appendChild(frag);
}

function buildTile(item) {
  const tile = document.createElement('div');
  tile.className = `tile tile-${item.type}`;
  const img = document.createElement('img');
  img.loading = 'lazy';
  img.decoding = 'async';
  img.src = item.thumb;
  img.alt = item.name;
  tile.appendChild(img);

  if (item.type === 'video') {
    const play = document.createElement('span');
    play.className = 'play';
    tile.appendChild(play);
  }
  if (item.type === 'gif' || item.type === 'pdf') {
    const tag = document.createElement('span');
    tag.className = 'tag';
    tag.textContent = item.type.toUpperCase();
    tile.appendChild(tag);
  }
  if (item.type === 'folder') {
    const caption = document.createElement('span');
    caption.className = 'caption';
    caption.textContent = `${item.name} (${item.count})`;
    tile.appendChild(caption);
  }

  tile.addEventListener('click', () => openItem(item, tile));
  return tile;
}

function openItem(item, tile) {
  const token = ++openToken;
  hideAllViews();
  modal.classList.remove('hidden');
  modal.dataset.mode = item.type === 'video' ? 'video'
    : (item.type === 'pdf' || item.type === 'folder') ? 'scroll' : 'image';
  if (location.hash !== MODAL_HASH) {
    location.hash = MODAL_HASH.slice(1);
  }

  if (item.type === 'video') {
    modalVideo.src = item.src;
    modalVideo.hidden = false;
    modalVideo.play().catch(() => {});
  } else if (item.type === 'pdf' || item.type === 'folder') {
    fetch(item.info)
      .then((r) => r.json())
      .then((data) => {
        if (token !== openToken) return;
        showPages(data.pages);
      })
      .catch(() => {});
  } else {
    modalImg.src = item.src;
    modalImg.hidden = false;
  }

  if (tile && tile.parentNode === grid && grid.firstChild !== tile) {
    grid.insertBefore(tile, grid.firstChild);
  }
  fetch(item.viewed_url, { method: 'POST' }).catch(() => {});
}

// PDF のページ画像 / フォルダ内の画像を縦に並べてスクロール表示する
function showPages(pages) {
  modalScroll.replaceChildren();
  const frag = document.createDocumentFragment();
  pages.forEach((page, i) => {
    const img = document.createElement('img');
    img.className = 'page';
    img.loading = 'lazy';
    img.decoding = 'async';
    // 読み込み前でも高さを確保してレイアウトのずれと遅延読み込みの誤判定を防ぐ
    if (page.w > 0 && page.h > 0) img.style.aspectRatio = `${page.w} / ${page.h}`;
    img.src = page.src;
    img.alt = `${i + 1}`;
    frag.appendChild(img);
  });
  modalScroll.appendChild(frag);
  modalScroll.hidden = false;
  modalScroll.scrollTop = 0;
  pageIndicator.hidden = pages.length < 2;
  updateIndicator();
}

function updateIndicator() {
  const pages = modalScroll.children;
  if (!pages.length) return;
  const line = modalScroll.scrollTop + modalScroll.clientHeight * 0.4;
  let current = 1;
  for (let i = 0; i < pages.length; i++) {
    if (pages[i].offsetTop <= line) current = i + 1;
    else break;
  }
  pageIndicator.textContent = `${current} / ${pages.length}`;
}

let indicatorPending = false;
modalScroll.addEventListener('scroll', () => {
  if (indicatorPending) return;
  indicatorPending = true;
  requestAnimationFrame(() => {
    indicatorPending = false;
    updateIndicator();
  });
});

function hideAllViews() {
  modalImg.hidden = true;
  modalImg.removeAttribute('src');
  modalVideo.hidden = true;
  modalVideo.pause();
  modalVideo.removeAttribute('src');
  modalVideo.load();
  modalScroll.hidden = true;
  modalScroll.replaceChildren();
  pageIndicator.hidden = true;
}

function closeModal({ fromBack = false } = {}) {
  if (modal.classList.contains('hidden')) return;
  openToken++;
  modal.classList.add('hidden');
  delete modal.dataset.mode;
  hideAllViews();
  if (!fromBack && location.hash === MODAL_HASH) {
    history.back();
  }
}

modal.addEventListener('click', (e) => {
  // 縦スクロール表示(漫画・PDF)は読んでいる最中の誤タップで閉じないようにする
  if (e.target === modal && modal.dataset.mode !== 'scroll') closeModal();
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
