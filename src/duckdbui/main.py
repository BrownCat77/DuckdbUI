import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import duckdb
import json
import csv
import os

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    _DND_AVAILABLE = True
except ImportError:
    _DND_AVAILABLE = False

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "db-files")


def ensure_db_dir():
    os.makedirs(DB_DIR, exist_ok=True)


def list_db_files() -> list[str]:
    ensure_db_dir()
    return [f for f in os.listdir(DB_DIR) if f.endswith(".duckdb")]


def _queries_file(db_name: str | None) -> str:
    key = "_inmemory" if db_name is None else db_name
    return os.path.join(DB_DIR, f"{key}.queries.json")


def load_saved_queries(db_name: str | None) -> list:
    ensure_db_dir()
    path = _queries_file(db_name)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return list(data.values())
            return data
    return []


def save_saved_queries(queries: list, db_name: str | None):
    ensure_db_dir()
    with open(_queries_file(db_name), "w", encoding="utf-8") as f:
        json.dump(queries, f, ensure_ascii=False, indent=2)


class App(TkinterDnD.Tk if _DND_AVAILABLE else tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("DuckDB SQL Editor")
        self.geometry("1200x750")
        self.configure(bg="#1a1a2e")

        self.con = duckdb.connect()  # 初期はインメモリ
        self.current_db: str | None = None  # 現在のDBファイル名
        self.loaded_tables: dict[str, str] = {}
        self.last_result: tuple[list, list] | None = None  # (columns, rows)
        self.saved_queries: list = load_saved_queries(None)  # 初期はインメモリ用
        self._drag_query_idx: int | None = None
        self._page = 0
        self._page_size = 100
        self._tooltip: tk.Toplevel | None = None

        self._build_ui()
        self._setup_dnd()

    # ------------------------------------------------------------------ UI --
    def _build_ui(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background="#1a1a2e", foreground="#e0e0e0", fieldbackground="#0f3460")
        style.configure("TButton", background="#0f3460", foreground="#e0e0e0", borderwidth=0, padding=6)
        style.map("TButton", background=[("active", "#1a4a8a")])
        style.configure("Run.TButton", background="#e94560", foreground="#ffffff")
        style.map("Run.TButton", background=[("active", "#c73652")])
        style.configure("TCombobox", fieldbackground="#0f3460", background="#0f3460", foreground="#e0e0e0")
        style.configure("Treeview", background="#0d1117", foreground="#c9d1d9",
                        fieldbackground="#0d1117", rowheight=24)
        style.configure("Treeview.Heading", background="#16213e", foreground="#e94560")
        style.map("Treeview", background=[("selected", "#0f3460")])
        style.configure("TSeparator", background="#0f3460")

        # --- Top toolbar ---
        toolbar = tk.Frame(self, bg="#16213e", pady=6)
        toolbar.pack(fill="x")
        tk.Label(toolbar, text="DuckDB SQL Editor", bg="#16213e", fg="#e94560",
                 font=("Segoe UI", 13, "bold")).pack(side="left", padx=14)

        # DB選択
        tk.Label(toolbar, text="DB:", bg="#16213e", fg="#aaa",
                 font=("Segoe UI", 9)).pack(side="left", padx=(16, 4))
        self.db_var = tk.StringVar(value="(インメモリ)")
        self.db_combo = tk.OptionMenu(toolbar, self.db_var, "(インメモリ)", command=self._on_db_select)
        self.db_combo.config(bg="#0f3460", fg="#e0e0e0", activebackground="#1a4a8a",
                             activeforeground="#e0e0e0", relief="flat", borderwidth=0,
                             highlightthickness=0, font=("Segoe UI", 9))
        self.db_combo["menu"].config(bg="#0f3460", fg="#e0e0e0")
        self.db_combo.pack(side="left")
        ttk.Button(toolbar, text="新規作成", command=self._create_db).pack(side="left", padx=6)
        ttk.Button(toolbar, text="↺", width=3, command=self._refresh_db_list).pack(side="left")

        # --- Main layout: 左固定 / 中央伸縮 / 右固定 ---
        container = tk.Frame(self, bg="#1a1a2e")
        container.pack(fill="both", expand=True)
        container.columnconfigure(1, weight=1)  # 中央のみ伸縮
        container.rowconfigure(0, weight=1)

        # 左サイドバー: ファイル/テーブル
        sidebar = tk.Frame(container, bg="#16213e", width=200)
        sidebar.grid(row=0, column=0, sticky="ns")
        sidebar.pack_propagate(False)  # 幅を固定

        tk.Frame(container, bg="#0f3460", width=1).grid(row=0, column=0, sticky="nse")

        tk.Label(sidebar, text="テーブル一覧 (ファイルをドロップ)", bg="#16213e", fg="#888",
                 font=("Segoe UI", 8)).pack(anchor="w", padx=10, pady=(10, 2))

        # スクロール可能なテーブル一覧フレーム
        table_list_outer = tk.Frame(sidebar, bg="#0d1117")
        table_list_outer.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        table_vsb = ttk.Scrollbar(table_list_outer, orient="vertical")
        table_vsb.pack(side="right", fill="y")
        self.table_canvas = tk.Canvas(table_list_outer, bg="#0d1117", bd=0,
                                      highlightthickness=0, yscrollcommand=table_vsb.set)
        self.table_canvas.pack(side="left", fill="both", expand=True)
        table_vsb.config(command=self.table_canvas.yview)
        self.table_inner = tk.Frame(self.table_canvas, bg="#0d1117")
        self._table_inner_id = self.table_canvas.create_window((0, 0), window=self.table_inner, anchor="nw")
        self.table_inner.bind("<Configure>", lambda e: self.table_canvas.configure(scrollregion=self.table_canvas.bbox("all")))
        self.table_canvas.bind("<Configure>", lambda e: self.table_canvas.itemconfig(self._table_inner_id, width=e.width))

        # 中央: エディタ + 結果
        right = tk.Frame(container, bg="#1a1a2e")
        right.grid(row=0, column=1, sticky="nsew")

        # SQL editor
        editor_frame = tk.Frame(right, bg="#0d1117")
        editor_frame.pack(fill="x")
        self.sql_editor = tk.Text(editor_frame, height=9, bg="#0d1117", fg="#c9d1d9",
                                  insertbackground="#e0e0e0", font=("Consolas", 10),
                                  relief="flat", bd=0, padx=10, pady=8, wrap="none")
        self.sql_editor.pack(fill="both", expand=True)
        self.sql_editor.insert("1.0", "SELECT * FROM your_table LIMIT 100")
        self.sql_editor.bind("<Control-Return>", lambda e: self._run_query())

        # SQL下部ボタンバー（実行・保存・クリア / エクスポート）
        sql_btnbar = tk.Frame(right, bg="#16213e", pady=4, padx=8)
        sql_btnbar.pack(fill="x")
        ttk.Button(sql_btnbar, text="▶ 実行  Ctrl+Enter", style="Run.TButton",
                   command=self._run_query).pack(side="left", padx=(0, 4))
        ttk.Button(sql_btnbar, text="保存", command=self._save_query).pack(side="left", padx=2)
        ttk.Button(sql_btnbar, text="クリア", command=self._clear_editor).pack(side="left", padx=2)
        self.btn_export_parquet = ttk.Button(sql_btnbar, text="Parquet エクスポート", command=self._export_parquet, state="disabled")
        self.btn_export_parquet.pack(side="right", padx=2)
        self.btn_export_json = ttk.Button(sql_btnbar, text="JSON エクスポート", command=self._export_json, state="disabled")
        self.btn_export_json.pack(side="right", padx=2)
        self.btn_export_csv = ttk.Button(sql_btnbar, text="CSV エクスポート", command=self._export_csv, state="disabled")
        self.btn_export_csv.pack(side="right", padx=2)

        # Result info bar (ステータス表示のみ、件数はページネーションに表示)
        rtoolbar = tk.Frame(right, bg="#16213e", pady=2, padx=8)
        rtoolbar.pack(fill="x")
        self.result_info = tk.Label(rtoolbar, text="", bg="#16213e", fg="#888", font=("Segoe UI", 9))
        self.result_info.pack(side="left")

        # Result table
        result_frame = tk.Frame(right, bg="#0d1117")
        result_frame.pack(fill="both", expand=True)

        # ページネーション (上)
        self.page_bar_top = tk.Frame(result_frame, bg="#16213e")
        self.page_bar_top.pack(fill="x")
        self._build_page_bar(self.page_bar_top)

        self.tree = ttk.Treeview(result_frame, show="headings")
        vsb = ttk.Scrollbar(result_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(result_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self.tree.pack(fill="both", expand=True)

        # ページネーション (下)
        self.page_bar_bottom = tk.Frame(result_frame, bg="#16213e")
        self.page_bar_bottom.pack(fill="x")
        self._build_page_bar(self.page_bar_bottom)

        # 右サイドバー: 保存クエリ一覧
        qsidebar = tk.Frame(container, bg="#16213e", width=220)
        qsidebar.grid(row=0, column=2, sticky="ns")
        qsidebar.pack_propagate(False)  # 幅を固定

        tk.Frame(container, bg="#0f3460", width=1).grid(row=0, column=2, sticky="nsw")

        tk.Label(qsidebar, text="保存済みクエリ", bg="#16213e", fg="#888",
                 font=("Segoe UI", 8)).pack(anchor="w", padx=10, pady=(10, 2))

        query_list_outer = tk.Frame(qsidebar, bg="#0d1117")
        query_list_outer.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        query_vsb = ttk.Scrollbar(query_list_outer, orient="vertical")
        query_vsb.pack(side="right", fill="y")
        self.query_canvas = tk.Canvas(query_list_outer, bg="#0d1117", bd=0,
                                      highlightthickness=0, yscrollcommand=query_vsb.set)
        self.query_canvas.pack(side="left", fill="both", expand=True)
        query_vsb.config(command=self.query_canvas.yview)
        self.query_inner = tk.Frame(self.query_canvas, bg="#0d1117")
        self._query_inner_id = self.query_canvas.create_window((0, 0), window=self.query_inner, anchor="nw")
        self.query_inner.bind("<Configure>", lambda e: self.query_canvas.configure(scrollregion=self.query_canvas.bbox("all")))
        self.query_canvas.bind("<Configure>", lambda e: self.query_canvas.itemconfig(self._query_inner_id, width=e.width))

        self._refresh_query_list()
        self._refresh_db_list()

    # --------------------------------------------------------- Drag & Drop --
    def _setup_dnd(self):
        if not _DND_AVAILABLE:
            return
        self.table_canvas.drop_target_register(DND_FILES)
        self.table_canvas.dnd_bind("<<Drop>>", self._on_drop)
        self.table_inner.drop_target_register(DND_FILES)
        self.table_inner.dnd_bind("<<Drop>>", self._on_drop)

    def _on_drop(self, event):
        paths = self.tk.splitlist(event.data)
        for path in paths:
            self._load_file(path)

    # --------------------------------------------------------- DB Management -
    def _refresh_db_list(self):
        files = list_db_files()
        menu = self.db_combo["menu"]
        menu.delete(0, "end")
        menu.add_command(label="(インメモリ)", command=lambda: self._select_db("(インメモリ)"))
        for f in files:
            menu.add_command(label=f, command=lambda v=f: self._select_db(v))
        # 現在の選択を維持、なければインメモリ
        if not self.current_db:
            self.db_var.set("(インメモリ)")
        elif self.current_db in files:
            self.db_var.set(self.current_db)
        else:
            self.db_var.set("(インメモリ)")

    def _select_db(self, value: str):
        self.db_var.set(value)
        self._on_db_select(value)

    def _on_db_select(self, value=None):
        selected = value or self.db_var.get()
        if selected == "(インメモリ)":
            self._switch_db(None)
        else:
            self._switch_db(selected)

    def _switch_db(self, filename: str | None):
        try:
            self.con.close()
        except Exception:
            pass
        if filename:
            path = os.path.join(DB_DIR, filename)
            self.con = duckdb.connect(path)
            self.current_db = filename
            self.title(f"DuckDB SQL Editor — {filename}")
        else:
            self.con = duckdb.connect()
            self.current_db = None
            self.title("DuckDB SQL Editor")

        # ロード済みテーブルをリセットしてDBのテーブルを表示
        self.loaded_tables.clear()
        self._sync_tables_from_db()
        # DBごとの保存クエリを読み込む
        self.saved_queries = load_saved_queries(self.current_db)
        self._refresh_query_list()

    def _sync_tables_from_db(self):
        """現在のDBに存在するテーブル/ビューをサイドバーに反映"""
        self.loaded_tables.clear()
        try:
            rows = self.con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
            ).fetchall()
            for (name,) in rows:
                self.loaded_tables[name] = ""
        except Exception:
            pass
        self._refresh_table_list()

    def _refresh_table_list(self):
        for w in self.table_inner.winfo_children():
            w.destroy()
        for name in self.loaded_tables:
            self._add_table_row(name)

    def _add_table_row(self, name: str):
        row = tk.Frame(self.table_inner, bg="#0d1117", cursor="hand2")
        row.pack(fill="x")
        lbl = tk.Label(row, text=name, bg="#0d1117", fg="#ccc",
                       font=("Segoe UI", 9), anchor="w", padx=4)
        lbl.pack(side="left", fill="x", expand=True)
        btn = tk.Label(row, text="✕", bg="#0d1117", fg="#555",
                       font=("Segoe UI", 9), padx=4, cursor="hand2")
        btn.pack(side="right")

        def on_enter(e, r=row, l=lbl, b=btn):
            r.config(bg="#16213e"); l.config(bg="#16213e"); b.config(bg="#16213e")
        def on_leave(e, r=row, l=lbl, b=btn):
            r.config(bg="#0d1117"); l.config(bg="#0d1117"); b.config(bg="#0d1117")
            self._hide_tooltip()

        for w in (row, lbl):
            w.bind("<Double-Button-1>", lambda e, n=name: self._insert_select(n))
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)
            w.bind("<Motion>", lambda e, n=name: self._on_table_hover_name(e, n))

        btn.bind("<Enter>", lambda e: btn.config(fg="#e94560"))
        btn.bind("<Leave>", lambda e: btn.config(fg="#555"))
        btn.bind("<Button-1>", lambda e, n=name: self._remove_table_by_name(n))

    def _insert_select(self, name: str):
        self.sql_editor.delete("1.0", "end")
        self.sql_editor.insert("1.0", f"SELECT * FROM {name}")
        self._run_query()

    def _on_table_double_click(self, _event):
        pass

    def _remove_table(self):
        pass

    def _remove_table_by_name(self, name: str):
        self.con.execute(f'DROP VIEW IF EXISTS "{name}"')
        self.con.execute(f'DROP TABLE IF EXISTS "{name}"')
        self.loaded_tables.pop(name, None)
        self._sync_tables_from_db()

    def _create_db(self):
        name = simpledialog.askstring("新規DB作成", "DBファイル名を入力してください (.duckdb):")
        if not name:
            return
        if not name.endswith(".duckdb"):
            name += ".duckdb"
        path = os.path.join(DB_DIR, name)
        if os.path.exists(path):
            messagebox.showwarning("警告", f'"{name}" はすでに存在します')
            return
        # ファイルを作成してすぐ切り替え
        conn = duckdb.connect(path)
        conn.close()
        self._refresh_db_list()
        self.db_var.set(name)
        self._switch_db(name)
        self._show_status(f'"{name}" を作成しました')

    # --------------------------------------------------------- File Load ----
    def _load_file(self, path: str):
        # Windowsパスの\をDuckDBが解釈できるよう/に変換
        path = path.strip().strip('"').strip("'")
        path_for_duckdb = path.replace("\\", "/")
        name = os.path.basename(path)
        ext = name.rsplit(".", 1)[-1].lower()
        table_name = name.rsplit(".", 1)[0].replace(" ", "_").replace("-", "_")

        try:
            if ext == "parquet":
                sql = f"CREATE OR REPLACE VIEW \"{table_name}\" AS SELECT * FROM parquet_scan('{path_for_duckdb}')"
            elif ext == "csv":
                sql = f"CREATE OR REPLACE VIEW \"{table_name}\" AS SELECT * FROM read_csv_auto('{path_for_duckdb}')"
            elif ext == "json":
                sql = f"CREATE OR REPLACE VIEW \"{table_name}\" AS SELECT * FROM read_json_auto('{path_for_duckdb}')"
            else:
                messagebox.showwarning("未対応", f"未対応のファイル形式: {ext}")
                return
            self.con.execute(sql)
        except Exception as e:
            messagebox.showerror("エラー", str(e))
            return

        self.loaded_tables[table_name] = path
        self._sync_tables_from_db()
        self._show_status(f'"{table_name}" をロードしました')

    # --------------------------------------------------------- Query Run ----
    def _run_query(self):
        sql = self.sql_editor.get("1.0", "end").strip()
        if not sql:
            return
        try:
            rel = self.con.execute(sql)
            if rel.description is None:
                # CREATE VIEW / DROP など結果セットなし
                self._sync_tables_from_db()
                self._show_status("実行完了")
                return
            columns = [d[0] for d in rel.description]
            rows = rel.fetchall()
            self.last_result = (columns, rows)
            self._page = 0
            self._render_page()
            self.btn_export_csv.config(state="normal")
            self.btn_export_json.config(state="normal")
            self.btn_export_parquet.config(state="normal")
            self._sync_tables_from_db()
        except Exception as e:
            messagebox.showerror("クエリエラー", str(e))

    def _render_page(self):
        if not self.last_result:
            return
        columns, rows = self.last_result
        start = self._page * self._page_size
        end = start + self._page_size
        self._render_table(columns, rows[start:end])
        self._refresh_page_bars()

    def _render_table(self, columns: list, rows: list):
        self.tree.delete(*self.tree.get_children())
        self.tree["columns"] = columns
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=120, minwidth=60)
        for row in rows:
            self.tree.insert("", "end", values=[str(v) if v is not None else "NULL" for v in row])

    # --------------------------------------------------------- Export ------
    def _export_csv(self):
        if not self.last_result:
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        columns, rows = self.last_result
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            writer.writerows(rows)
        self._show_status("CSVをエクスポートしました")

    def _export_json(self):
        if not self.last_result:
            return
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if not path:
            return
        columns, rows = self.last_result
        data = [dict(zip(columns, row)) for row in rows]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        self._show_status("JSONをエクスポートしました")

    def _export_parquet(self):
        if not self.last_result:
            return
        path = filedialog.asksaveasfilename(defaultextension=".parquet", filetypes=[("Parquet", "*.parquet")])
        if not path:
            return
        # last_resultをDataFrameに変換してCOPY TO
        columns, rows = self.last_result
        tmp_con = duckdb.connect()
        tmp_con.execute(
            f"CREATE TABLE _export_tmp ({', '.join(f'\"{c}\" VARCHAR' for c in columns)})"
        )
        tmp_con.executemany(
            f"INSERT INTO _export_tmp VALUES ({', '.join('?' for _ in columns)})",
            [[str(v) if v is not None else None for v in row] for row in rows]
        )
        path_escaped = path.replace("\\", "/")
        tmp_con.execute(f"COPY _export_tmp TO '{path_escaped}' (FORMAT PARQUET)")
        tmp_con.close()
        self._show_status("Parquetをエクスポートしました")

    def _clear_editor(self):
        self.sql_editor.delete("1.0", "end")
        if not self.last_result:
            return
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if not path:
            return
        columns, rows = self.last_result
        data = [dict(zip(columns, row)) for row in rows]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        self._show_status("JSONをエクスポートしました")

    # --------------------------------------------------------- Saved Queries
    def _refresh_query_list(self):
        for w in self.query_inner.winfo_children():
            w.destroy()
        for idx, sql in enumerate(self.saved_queries):
            self._add_query_row(idx, sql)

    def _add_query_row(self, idx: int, sql: str):
        label_text = sql.strip().replace("\n", " ")[:50]
        row = tk.Frame(self.query_inner, bg="#0d1117", cursor="hand2")
        row.pack(fill="x")
        btn = tk.Label(row, text="✕", bg="#0d1117", fg="#555",
                       font=("Segoe UI", 9), padx=4, cursor="hand2")
        btn.pack(side="right")
        lbl = tk.Label(row, text=label_text, bg="#0d1117", fg="#ccc",
                       font=("Segoe UI", 9), anchor="w", padx=4)
        lbl.pack(side="left", fill="x", expand=True)

        def on_enter(e, r=row, l=lbl, b=btn):
            r.config(bg="#16213e"); l.config(bg="#16213e"); b.config(bg="#16213e")
        def on_leave(e, r=row, l=lbl, b=btn):
            r.config(bg="#0d1117"); l.config(bg="#0d1117"); b.config(bg="#0d1117")
            self._hide_tooltip()

        for w in (row, lbl):
            w.bind("<Double-Button-1>", lambda e, i=idx: self._load_query_by_idx(i))
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)
            w.bind("<Motion>", lambda e, i=idx: self._on_query_hover_idx(e, i))
            # ドラッグ&ドロップ
            w.bind("<ButtonPress-1>", lambda e, i=idx: self._on_query_drag_start(i))
            w.bind("<B1-Motion>", lambda e, i=idx: self._on_query_drag_motion(e, i))
            w.bind("<ButtonRelease-1>", lambda e, i=idx: self._on_query_drag_release(e, i))

        btn.bind("<Enter>", lambda e: btn.config(fg="#e94560"))
        btn.bind("<Leave>", lambda e: btn.config(fg="#555"))
        btn.bind("<Button-1>", lambda e, i=idx: self._delete_query_by_idx(i))

    def _load_query_by_idx(self, idx: int):
        if 0 <= idx < len(self.saved_queries):
            self.sql_editor.delete("1.0", "end")
            self.sql_editor.insert("1.0", self.saved_queries[idx])

    def _delete_query_by_idx(self, idx: int):
        if 0 <= idx < len(self.saved_queries):
            self.saved_queries.pop(idx)
            save_saved_queries(self.saved_queries, self.current_db)
            self._refresh_query_list()
            self._show_status("クエリを削除しました")

    def _save_query(self):
        sql = self.sql_editor.get("1.0", "end").strip()
        if not sql:
            messagebox.showwarning("警告", "クエリが空です")
            return
        self.saved_queries.append(sql)
        save_saved_queries(self.saved_queries, self.current_db)
        self._refresh_query_list()
        self._show_status("クエリを保存しました")

    # ドラッグ&ドロップ並び替え
    def _on_query_drag_start(self, idx: int):
        self._drag_query_idx = idx

    def _on_query_drag_motion(self, event, idx: int):
        # ドラッグ中はカーソル位置から移動先インデックスを計算してハイライト
        rows = self.query_inner.winfo_children()
        y = event.y_root - self.query_inner.winfo_rooty()
        target = max(0, min(len(rows) - 1, y // 24))
        for i, r in enumerate(rows):
            r.config(bg="#e94560" if i == target else "#0d1117")
            for child in r.winfo_children():
                child.config(bg="#e94560" if i == target else "#0d1117")

    def _on_query_drag_release(self, event, idx: int):
        rows = self.query_inner.winfo_children()
        y = event.y_root - self.query_inner.winfo_rooty()
        target = max(0, min(len(rows) - 1, y // 24))
        if self._drag_query_idx is not None and self._drag_query_idx != target:
            item = self.saved_queries.pop(self._drag_query_idx)
            self.saved_queries.insert(target, item)
            save_saved_queries(self.saved_queries, self.current_db)
        self._drag_query_idx = None
        self._refresh_query_list()

    # --------------------------------------------------------- Helpers -----
    def _build_page_bar(self, parent: tk.Frame):
        """ページネーションバーのウィジェットを生成して返す"""
        outer = tk.Frame(parent, bg="#16213e")
        outer.pack(fill="x", pady=2)
        bar = tk.Frame(outer, bg="#16213e")
        bar.pack(anchor="center")  # 中央寄せ
        btn_prev = ttk.Button(bar, text="◀", width=3, command=self._prev_page)
        btn_prev.pack(side="left")
        lbl = tk.Label(bar, text="", bg="#16213e", fg="#aaa", font=("Segoe UI", 8), width=28)
        lbl.pack(side="left", padx=6)
        btn_next = ttk.Button(bar, text="▶", width=3, command=self._next_page)
        btn_next.pack(side="left")
        parent._btn_prev = btn_prev
        parent._lbl = lbl
        parent._btn_next = btn_next

    def _refresh_page_bars(self):
        if not self.last_result:
            return
        total = len(self.last_result[1])
        total_pages = max(1, (total + self._page_size - 1) // self._page_size)
        current_start = self._page * self._page_size + 1
        current_end = min(current_start + self._page_size - 1, total)
        label = f"{current_start}-{current_end} / {total}件  ({self._page + 1}/{total_pages}ページ)"
        for bar in (self.page_bar_top, self.page_bar_bottom):
            bar._lbl.config(text=label)
            bar._btn_prev.config(state="normal" if self._page > 0 else "disabled")
            bar._btn_next.config(state="normal" if self._page < total_pages - 1 else "disabled")

    def _prev_page(self):
        if self._page > 0:
            self._page -= 1
            self._render_page()

    def _next_page(self):
        if not self.last_result:
            return
        total_pages = (len(self.last_result[1]) + self._page_size - 1) // self._page_size
        if self._page < total_pages - 1:
            self._page += 1
            self._render_page()

    # --------------------------------------------------------- Tooltip -----
    def _on_table_hover_name(self, event, name: str):
        text = self._get_table_tooltip(name)
        self._show_tooltip_for(self.table_inner, event, text)

    def _get_table_tooltip(self, name: str) -> str:
        try:
            # VIEWの定義を取得 (カラム名は 'sql')
            rows = self.con.execute(
                "SELECT sql FROM duckdb_views() WHERE view_name = ?", [name]
            ).fetchall()
            if rows:
                return f"[VIEW] {name}\n\n{rows[0][0]}"
            # テーブルの場合はカラム一覧を表示
            cols = self.con.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = ? AND table_schema = 'main' ORDER BY ordinal_position",
                [name]
            ).fetchall()
            if cols:
                col_lines = "\n".join(f"  {c}  {t}" for c, t in cols)
                return f"[TABLE] {name}\n\n{col_lines}"
        except Exception:
            pass
        return name

    def _on_query_hover_idx(self, event, idx: int):
        if 0 <= idx < len(self.saved_queries):
            sql = self.saved_queries[idx]
            self._show_tooltip_for(self.query_inner, event, sql)

    def _show_tooltip_for(self, widget: tk.Widget, event, text: str):
        self._hide_tooltip()
        x = widget.winfo_rootx() - 10
        y = event.y_root + 10
        tip = tk.Toplevel(self)
        tip.wm_overrideredirect(True)
        tip.wm_geometry(f"+{x}+{y}")
        lbl = tk.Label(tip, text=text, bg="#0f3460", fg="#e0e0e0",
                       font=("Consolas", 8), justify="left",
                       relief="solid", bd=1, padx=6, pady=4, wraplength=360)
        lbl.pack()
        self._tooltip = tip

    # 後方互換
    def _show_tooltip(self, event, text: str):
        self._show_tooltip_for(self.query_inner, event, text)

    def _hide_tooltip(self, _event=None):
        if self._tooltip:
            self._tooltip.destroy()
            self._tooltip = None

    def _show_status(self, msg: str):
        self.result_info.config(text=msg)
        self.after(3000, lambda: self.result_info.config(text=""))


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
