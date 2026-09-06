# googledrive

ローカルの画像フォルダを、同一WiFi内の他端末(iPadなど)から閲覧するためのシンプルなWebアプリ。

## 機能

- 指定フォルダ内の画像・GIF・動画・PDF・サブフォルダを一覧表示(サムネイル)
- 画像はモーダル拡大表示
- PDF は全ページをサーバ側で画像化し、モーダル内で縦スクロール閲覧
- サブフォルダを選ぶと中の画像が縦に並んでスクロールできる(漫画などの閲覧用)
- GIF は無限ループで再生される(元ファイルのループ回数に関わらず)
- 動画(`.mov` `.mp4` など)はモーダル内で再生。シーク(早送り)にも対応
- 閲覧したファイルが次回以降一覧の先頭に来る(閲覧時刻を `viewed.json` に永続化)
- クリック直後に該当タイルが一覧先頭へ移動
- フォルダに追加された新規ファイル・新規フォルダは一覧の最上部に表示される
- 同一WiFi内の任意端末からアクセス可能

## 想定環境

- Python 3.12+
- macOS / Linux / Windows
- ffmpeg(任意。動画サムネイルの生成に使う。無い場合は無地のサムネイルになるが再生自体は可能)

## セットアップ

### macOS / Linux

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp config.example.py config.py
```

### Windows

```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy config.example.py config.py
```

`config.py` の `SCREENSHOT_DIR` を、表示したい画像フォルダの絶対パスに書き換える。`config.example.py` に macOS / Windows それぞれの代表的なパス例をコメントで記載している。

動画のサムネイルが必要な場合は ffmpeg をインストールして PATH に通す(macOS なら `brew install ffmpeg`)。

## 起動

### macOS / Linux

```sh
.venv/bin/python app.py
```

### Windows

```bat
.venv\Scripts\python app.py
```

初回起動時、Windows Defender ファイアウォールが許可確認ダイアログを出すので「プライベートネットワーク」を許可する(許可しないと同一WiFi上の他端末から接続できない)。

起動時にコンソールへ `http://<MacのIP or PCのIP>:8000` が出力されるので、iPad などから同一WiFi経由でアクセスする。

## 操作

- タイルをタップ / クリックで開く
- 閉じる: 右上の × / Esc キー / ブラウザの戻る
- 画像・動画は背景をタップしても閉じる。縦スクロール表示(PDF・フォルダ)は読んでいる最中の誤タップを防ぐため背景タップでは閉じない
- 縦スクロール表示では右下に「現在のページ / 総ページ数」を表示

## 仕様メモ

- 対応拡張子(大文字小文字区別なし)
  - 画像: `.png .jpg .jpeg .webp`
  - GIF: `.gif`
  - 動画: `.mov .mp4 .m4v .webm`
  - 文書: `.pdf`
- サブフォルダはトップレベルの1階層のみを対象とし、中の画像・GIF をファイル名の自然順(`1, 2, 10` の順)で並べる。画像が1枚も無いフォルダは一覧に出ない
- サムネイルは `thumbnails/` に JPEG キャッシュ(元ファイルのパスと mtime をキーに自動更新)
  - PDF は1ページ目、動画は再生開始1秒地点のフレームをサムネイルにする
- PDF は `cache/` にページ画像(JPEG・幅1400px目安)をキャッシュし、表示のたびに再描画しない
  - ブラウザ標準の PDF ビューアを iframe で使うと iOS Safari が1ページ目しか表示しないため、サーバ側でページ画像に変換している
- GIF は NETSCAPE 拡張のループ回数を 0(無限)に書き換えたものを `cache/` に置いて配信する。バイト列の書き換えのみで再エンコードしないため画質・フレームは変化しない
- 動画は Range リクエストに対応しているため、大きいファイルでもシークできる。`.mov` の再生可否は端末のコーデック対応次第(iPad / Mac の Safari は H.264・HEVC とも再生可)
- フォルダに新規ファイルが追加された場合は、Python プロセスを再起動して再スキャンする
- 認証なし(同一WiFi内利用を前提)

## ファイル構成

```
app.py              # FastAPI 本体
config.py           # SCREENSHOT_DIR を定義(gitignore)
config.example.py   # config.py のテンプレート
templates/          # HTML
static/             # JS / CSS
thumbnails/         # サムネイルの自動生成キャッシュ(gitignore)
cache/              # PDFページ画像・無限ループ化GIFのキャッシュ(gitignore)
viewed.json         # 閲覧時刻記録(gitignore)
seen.json           # 既知ファイル一覧・新規判定用(gitignore)
```
