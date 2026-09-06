# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 概要

ローカルの画像・動画・PDF フォルダを同一 WiFi 内の他端末(iPad など)から閲覧するための FastAPI 製シングルページアプリ。認証なし・LAN 内利用前提で `0.0.0.0:8000` に bind する。

## コマンド

```sh
# セットアップ(初回のみ)
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp config.example.py config.py   # SCREENSHOT_DIR を実環境のパスに書き換える

# 起動(uvicorn は app.py の __main__ から起動される)
.venv/bin/python app.py
```

Windows では `.venv\Scripts\python app.py`。動画サムネイルには ffmpeg が PATH 上に必要(無くても起動し、無地のサムネイルにフォールバックする)。

テストフレームワーク・リンタ・フォーマッタは導入されていない。変更の確認は実際にアプリを起動して行う。

**注意: `SEEN_FILE` / `VIEWED_FILE` / `THUMB_DIR` / `CACHE_DIR` はすべて `BASE_DIR`(= app.py のあるディレクトリ)配下**。動作確認のためにリポジトリ直下でスキャン対象を差し替えて起動すると、利用者の `seen.json` / `viewed.json` を上書きしてしまう。検証は `app.py` と `static/` `templates/` を一時ディレクトリにコピーし、そこに専用の `config.py` を置いて行うこと。

## アーキテクチャ

単一モジュール `app.py`(FastAPI)+ 素の JS/CSS(`static/`)+ Jinja2 テンプレート 1 枚(`templates/index.html`)。ビルド工程はない。

### 設定

`config.py`(gitignore)が `SCREENSHOT_DIR` を定義する。`app.py` はモジュール読み込み時に import し、無ければ `SystemExit` で落ちる。パスは環境ごとに異なるので、コード側にハードコードしない。

### 状態はプロセス内グローバル + JSON ファイル

DB はなく、次のグローバル変数と JSON ファイルで状態を保持する(JSON は gitignore)。

| グローバル | ファイル | 意味 |
| --- | --- | --- |
| `IMAGES` | (なし) | トップレベルのファイル `name -> {mtime, size, type}` |
| `FOLDERS` | (なし) | トップレベルのフォルダ `name -> {mtime, files, sizes}` |
| `VIEWED` | `viewed.json` | キー -> 閲覧時刻(ISO8601 UTC) |
| `SEEN` | `seen.json` | キー -> 初回検出時刻。新規判定の基準 |
| `NEW_ITEMS` | (なし) | 今回のスキャンで新規に現れたキーの集合 |

`VIEWED` / `SEEN` のキーは、ファイルはファイル名そのまま、**フォルダは末尾に `/` を付けた形**(`folder_key()`)。同名のファイルとフォルダを区別するための規約なので、片方だけ変えないこと。

JSON の保存は `.json.tmp` に書いてから `replace()` するアトミック書き込み。`VIEWED` の更新のみ `VIEWED_LOCK` で保護している。

### 重要な不変条件

- **`IMAGES` / `FOLDERS` が実質的な認可リスト**。ファイルを返す全エンドポイントは、`name not in IMAGES`(フォルダ内は `name not in FOLDERS[folder]["files"]`)で 404 を返してからパスを組み立てる。これがパストラバーサル対策も兼ねているため、この検査を外したり `SCREENSHOT_DIR / name` を先に組み立てたりしないこと。
- **スキャンは lifespan 起動時の 1 回のみ**。フォルダに画像を足しても再起動しないと反映されない(README にも明記済み)。
- **`seen.json` が存在しない初回起動では既存項目を「新規」扱いしない**(`update_seen` の `first_run`)。この判定は `SEEN` の中身ではなくファイルの存在で行う。
- **サブフォルダはトップレベルの 1 階層のみ**。入れ子のフォルダは辿らず、画像が 0 枚のフォルダは一覧に出さない。

### 一覧の並び順

`/api/items` がソート済みで返し、フロントは並べ替えない。優先度は `sort_key` の通り:

1. 新規追加(`is_new`)— mtime 降順
2. 閲覧済み — 閲覧時刻の新しい順
3. 未閲覧 — mtime 降順

クリック時はフロント側で該当タイルを DOM の先頭へ移動し、次回ロードでサーバ順と一致させる。

### 種別ごとの扱い

`file_type()` が拡張子から `image` / `gif` / `video` / `pdf` を決め、フォルダは `folder`。`/api/items` は各項目のサムネイル URL・本体 URL・閲覧記録 URL を**サーバ側で組み立てて返す**(`urllib.parse.quote`)。フロントで URL を組み立て直さないこと。

- **PDF**: ブラウザ標準ビューアを iframe で使うと **iOS Safari が1ページ目しか描画しない**ため、pypdfium2 でページごとに JPEG へ変換して縦に並べている。`/api/pdf/{name}` がページ数と各ページの用紙サイズを返し、`/pdfpage/{name}/{index}` が実画像を返す。用紙サイズはフロントが `aspect-ratio` に使い、遅延読み込み時のレイアウトずれを防ぐ。
- **GIF**: `_gif_force_loop()` が NETSCAPE アプリケーション拡張のループ回数を 0(無限)に書き換える。**再エンコードではなくバイト列の直接操作**(拡張が無い GIF には論理画面記述子 + グローバルカラーテーブルの直後に挿入する)なので、画質とフレームは元のまま。Pillow で開き直して保存すると劣化・破損の恐れがあるため、この方式を変えないこと。
- **動画**: サムネイルは ffmpeg で 1 秒地点のフレームを1枚抜く(冒頭が黒画面のことがあるため。失敗したら 0 秒、それも駄目ならプレースホルダ)。配信は `FileResponse` 任せで、Starlette 1.0 が Range リクエストを処理するのでシークできる。
- **フォルダ(漫画ビューア)**: 中の画像をファイル名の自然順(`natural_key()` で `1, 2, 10` の順)に並べ、PDF と同じ縦スクロールビューアで表示する。

### キャッシュ

- `thumbnails/` — 一覧のサムネイル。キーは `sha1(元ファイルの絶対パス | mtime)`。パスを含めるのはフォルダ内の同名ファイルと衝突させないため
- `cache/` — PDF のページ画像と無限ループ化した GIF。キーは用途 + パス + mtime(+ ページ番号)

いずれも古いファイルの削除処理はない。キーの作り方を変えると既存キャッシュは丸ごと再生成される。

### モーダル(`static/app.js`)

`#modal` は `data-mode` で 3 つの表示を切り替える。

| mode | 要素 | 対象 |
| --- | --- | --- |
| `image` | `#modal-img` | 画像・GIF |
| `video` | `#modal-video` | 動画 |
| `scroll` | `#modal-scroll` | PDF・フォルダ |

- 表示を切り替える前に必ず `hideAllViews()` を通す。動画は `src` を消して `load()` しないとバックグラウンドでダウンロードが続く。
- `scroll` モードだけ背景タップで閉じない(読んでいる最中の誤タップ対策)。
- `openToken` は、フォルダ / PDF の情報取得が非同期なため、閉じた後に届いたレスポンスで描画しないための世代番号。
- ページ番号の算出に `offsetTop` を使うので、`#modal-scroll` の `position: relative` は必須(これが offsetParent になる)。

#### 履歴制御

Android Brave での戻る操作に対応するため、`location.hash = '#image'` と `hashchange` イベントで開閉を管理している(commit `433b0c6` / `e352903` の経緯)。触る際の注意:

- `closeModal({ fromBack })` の `fromBack` は「hashchange 由来か」を表す。ユーザ操作由来の閉じるときだけ `history.back()` を呼び、二重に履歴を戻さないようにしている。
- `pushState` / `popstate` ではなく hash ベースであること自体が意図的な選択。
- ページロード時に残っている `#image` は `replaceState` で除去する。

## 慣習

- コミットメッセージは日本語の Conventional Commits(`feat:` / `fix:` + 日本語本文)。
- コード内コメント・ドキュメント・UI 文言はすべて日本語。
