# googledrive

ローカルの画像フォルダを、同一WiFi内の他端末(iPadなど)から閲覧するためのシンプルなWebアプリ。

## 機能

- 指定フォルダ内の画像とPDFを一覧表示(サムネイル)
- 画像はモーダル拡大表示、PDFはモーダル内のブラウザ標準ビューアでスクロール閲覧
- 閲覧したファイルが次回以降一覧の先頭に来る(閲覧時刻を `viewed.json` に永続化)
- クリック直後に該当タイルが一覧先頭へ移動
- 同一WiFi内の任意端末からアクセス可能

## 想定環境

- Python 3.12+
- macOS / Linux / Windows

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

## 仕様メモ

- 対応拡張子: `.png .jpg .jpeg .gif .webp .pdf`(大文字小文字区別なし)
- サムネイルは `thumbnails/` に JPEG キャッシュ(元ファイルの mtime をキーに自動更新)。PDF は1ページ目をレンダリングしてサムネイル化
- PDFビューアはブラウザ標準(iOS Safari / Chrome / Firefox いずれもインライン表示・縦スクロール対応)
- フォルダに新規画像が追加された場合は、Python プロセスを再起動して再スキャンする
- 認証なし(同一WiFi内利用を前提)

## ファイル構成

```
app.py              # FastAPI 本体
config.py           # SCREENSHOT_DIR を定義(gitignore)
config.example.py   # config.py のテンプレート
templates/          # HTML
static/             # JS / CSS
thumbnails/         # 自動生成キャッシュ(gitignore)
viewed.json        # 閲覧時刻記録(gitignore)
```
