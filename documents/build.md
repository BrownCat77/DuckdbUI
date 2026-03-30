# ビルド・配布手順

## 開発環境のセットアップ

### 必要なもの

- Python 3.13+
- [uv](https://docs.astral.sh/uv/getting-started/installation/)

### 手順

```bash
# 依存関係のインストール
uv sync
```

### 開発時の起動

```bash
uv run duckdbui
```

---

## exe ビルド手順

### 1. PyInstaller をインストール

```bash
uv add --dev pyinstaller
```

### 2. ビルド実行

```bash
uv run pyinstaller --onefile --windowed --name duckdbui --add-data "documents;documents" src/duckdbui/main.py
```

| オプション | 説明 |
|---|---|
| `--onefile` | 単一の `.exe` にまとめる |
| `--windowed` | コンソールウィンドウを非表示にする |
| `--name duckdbui` | 出力ファイル名 |
| `--add-data "documents;documents"` | `documents/` フォルダを同梱する |

### 3. 出力先

ビルドが成功すると以下に生成されます。

```
dist/
└── duckdbui.exe
```

---

## 配布パッケージの構成

`dist/duckdbui.exe` 単体では動作しません。以下のフォルダ構成で配布してください。

```
配布フォルダ/
├── duckdbui.exe          # 実行ファイル
├── db-files/             # DBファイル・保存クエリの格納先（空フォルダでOK）
└── documents/
    ├── usage.html        # 使い方（アプリ内の「？ 使い方」ボタンから参照）
    └── features.md       # 機能一覧
```

### 注意事項

- `db-files/` フォルダは exe と同じディレクトリに必要です。存在しない場合は起動時に自動作成されます。
- `documents/usage.html` が存在しない場合、「？ 使い方」ボタンを押してもブラウザで何も開きません。
- `tkinterdnd2` を使用している場合、ビルド済み exe にはDLLが自動的に同梱されます。

---

## ビルド時に生成されるファイル

以下はビルド時の中間ファイルです。`.gitignore` に追加済みのため Git には含まれません。

```
build/          # PyInstaller の中間ファイル
dist/           # ビルド成果物
duckdbui.spec   # PyInstaller の設定ファイル（自動生成）
```

---

## 再ビルド

ソースを変更した場合は同じコマンドを再実行するだけです。

```bash
uv run pyinstaller --onefile --windowed --name duckdbui --add-data "documents;documents" src/duckdbui/main.py
```
