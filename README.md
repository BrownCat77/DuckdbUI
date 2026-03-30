# ⬡ DuckDB SQL Editor

DuckDB を使ってブラウザ不要でローカルファイルに対して SQL を実行できる Python デスクトップアプリです。

Parquet / CSV / JSON ファイルをドラッグ&ドロップで読み込み、SQL で分析・エクスポートできます。

## 必要環境

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)

## セットアップ

```bash
uv sync
uv add tkinterdnd2   # ドラッグ&ドロップを有効にする場合
```

## 起動

```bash
uv run duckdbui
```

## ドキュメント

| ドキュメント | 内容 |
|---|---|
| [機能一覧](documents/features.md) | 全機能の一覧と説明 |
| [使い方](documents/usage.html) | 画面構成・操作手順・ショートカット |
| [ビルド・配布手順](documents/build.md) | exe化の手順・配布フォルダ構成 |

## プロジェクト構成

```
├── src/duckdbui/
│   └── main.py        # アプリ本体
├── db-files/          # DBファイル・保存クエリの格納先 (.gitignore対象)
├── documents/
│   ├── features.md    # 機能一覧
│   ├── usage.md       # 使い方 (Markdown)
│   └── usage.html     # 使い方 (HTML)
└── pyproject.toml
```
