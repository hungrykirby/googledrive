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
- サブフォルダはトップレベルの1階層のみを対象とし、中の画像・GIF を既定では更新日時の古い順(先にダウンロードしたものほど上)で並べる。並び順は `order.json` で変えられる(下記「フォルダ内の並び順」)。画像が1枚も無いフォルダは一覧に出ない
- フォルダの一覧サムネイル(表紙)は、並べ替えた後の先頭ページ
- サムネイルは `thumbnails/` に JPEG キャッシュ(元ファイルのパスと mtime をキーに自動更新)
  - PDF は1ページ目、動画は再生開始1秒地点のフレームをサムネイルにする
- PDF は `cache/` にページ画像(JPEG・幅1400px目安)をキャッシュし、表示のたびに再描画しない
  - ブラウザ標準の PDF ビューアを iframe で使うと iOS Safari が1ページ目しか表示しないため、サーバ側でページ画像に変換している
- GIF は NETSCAPE 拡張のループ回数を 0(無限)に書き換えたものを `cache/` に置いて配信する。バイト列の書き換えのみで再エンコードしないため画質・フレームは変化しない
- 動画は Range リクエストに対応しているため、大きいファイルでもシークできる。`.mov` の再生可否は端末のコーデック対応次第(iPad / Mac の Safari は H.264・HEVC とも再生可)
- フォルダに新規ファイルが追加された場合は、Python プロセスを再起動して再スキャンする
- 認証なし(同一WiFi内利用を前提)
- 画面のタイトルは `config.py` の `SITE_TITLE` で変えられる(省略時は「ギャラリー」)

## フォルダ内の並び順

`app.py` と同じ場所に `order.json` を置くと、フォルダ内の画像の並び順を変えられる。無ければ全フォルダが更新日時の古い順になる。書式は `order.example.json` を参照。

```json
{
  "default": "oldest",
  "folders": {
    "ファイル名の順で読みたいフォルダ名": "name_asc",
    "順番を細かく決めたいフォルダ名": ["表紙.jpg", "1.png", "2.png"]
  }
}
```

並び順に書ける値:

| 値 | 並び順 |
| --- | --- |
| `"oldest"` | 更新日時の古い順(先にダウンロードしたものほど上)。既定 |
| `"newest"` | 更新日時の新しい順 |
| `"name_asc"` | ファイル名の自然順(`1, 2, 10`) |
| `"name_desc"` | ファイル名の自然順の逆(`10, 2, 1`) |

| キー | 値 | 意味 |
| --- | --- | --- |
| `default` | 上の表の値 | 全フォルダ共通の並び順。省略時は `oldest` |
| `folders` の各キー | フォルダ名(トップレベルのフォルダ名そのまま) | |
| `folders` の各値 | 上の表の値 | そのフォルダだけ並び順を変える |
| `folders` の各値 | ファイル名のリスト | 書いた順に並べる。リストに無いファイルは `default` の順で後ろに続く |

- 更新日時は Finder の「変更日」/ エクスプローラーの「更新日時」。ブラウザでダウンロードしたファイルならダウンロードした日時になるが、zip を展開したファイルや別の場所からコピー・同期したファイルは元の日時を引き継ぐことがある。その場合は `name_asc` やファイル名のリストで指定する
- 更新日時が同じファイルどうしはファイル名の自然順に並ぶ
- 反映には Python プロセスの再起動が必要(新規ファイルの検出と同じく、起動時にだけ読む)
- 存在しないフォルダ名・ファイル名や書式の誤りは、起動時にコンソールへ `[warn]` を出して無視する

## ファイル構成

```
app.py              # FastAPI 本体
config.py           # SCREENSHOT_DIR / SITE_TITLE を定義(gitignore)
config.example.py   # config.py のテンプレート
order.json          # フォルダ内の並び順の設定(任意・gitignore)
order.example.json  # order.json の書式例
templates/          # HTML
static/             # JS / CSS
thumbnails/         # サムネイルの自動生成キャッシュ(gitignore)
cache/              # PDFページ画像・無限ループ化GIFのキャッシュ(gitignore)
viewed.json         # 閲覧時刻記録(gitignore)
seen.json           # 既知ファイル一覧・新規判定用(gitignore)
```
