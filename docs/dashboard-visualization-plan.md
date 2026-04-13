# ダッシュボード（可視化機能）設計メモ

## 基本方針

- ユーザが自由にグラフを配置できる BI ライクなダッシュボード
- 勘定科目がユーザごとに大きく異なるため、固定レイアウトは不適
- グラフ設定は DB に保存（マルチユーザへの拡張性を確保）

---

## グラフの構成要素

| 要素 | 候補 |
|------|------|
| グラフ種 | 折れ線、棒、積み上げ棒（まず3種で十分） |
| X 軸 | 月（ほぼ固定でよい） |
| Y 軸（系列） | 特定科目の発生額 / 残高、または収益合計・費用合計・当期純損益などの集計値 |
| 時間範囲 | 全期間 / 直近 N ヶ月 / 会計年度（グラフごとに設定） |

---

## 検討ポイント

### 1. 系列の粒度

**シンプル案（推奨スタート地点）**
- 1グラフ = 1科目 または 1集計値（収益合計など）
- 実装コストが低く、まず動くものを作れる

**拡張案（後から追加可能）**
- 複数科目をユーザが束ねて1系列にする（例: 人件費＋福利厚生費）
- `graph_series` テーブルに複数レコードで表現できる
- 最初から複数系列に対応したスキーマにしておくとよい

→ **スキーマは複数系列対応で設計し、UI は最初シンプルにする** のが安全

### 2. DB スキーマ案

```sql
CREATE TABLE dashboards (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    title       TEXT    NOT NULL DEFAULT '',
    sort_order  INTEGER DEFAULT 0
);

CREATE TABLE dashboard_graphs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    dashboard_id INTEGER NOT NULL REFERENCES dashboards(id),
    title        TEXT    NOT NULL DEFAULT '',
    chart_type   TEXT    NOT NULL CHECK(chart_type IN ('line','bar','stacked_bar')),
    time_range   TEXT    NOT NULL DEFAULT 'all',  -- 'all' | 'last_N' | 'fiscal_year'
    time_range_n INTEGER,                          -- time_range='last_N' のときの N（月数）
    sort_order   INTEGER DEFAULT 0
);

CREATE TABLE graph_series (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    graph_id         INTEGER NOT NULL REFERENCES dashboard_graphs(id),
    label            TEXT,                          -- 系列の表示名（省略時は科目名）
    series_type      TEXT    NOT NULL,              -- 'account' | 'total_revenues' | 'total_expenses' | 'net_income'
    account_id       INTEGER REFERENCES accounts(id), -- series_type='account' のときのみ
    sort_order       INTEGER DEFAULT 0
);
```

**補足**
- `dashboards` はシングルユーザ構成でも `user_id` を持っておくとマルチユーザ化が楽
- `graph_series` を複数レコードにしておくことで、将来の科目合算系列に対応できる
- `time_range` の `fiscal_year` は会計期間設定が実装されたタイミングで有効化

### 3. 時間範囲と会計期間の関係

- `time_range='fiscal_year'` は、会計期間の開始日設定（未実装）と連動する
- 当面は `all`（全期間）と `last_N`（直近 N ヶ月）だけ実装し、`fiscal_year` は後回しでよい

### 4. Y 軸の値の意味（科目種別による違い）

| 科目種別 | グラフに使う値 |
|----------|--------------|
| 収益・費用 | その月の発生額（月次PL値） |
| 資産・負債・純資産 | 月末時点の残高（累計） |
| 集計値（収益合計など） | 同上のルールに従う |

科目種別によって「発生額」か「残高」かが変わることをUIで明示する必要がある。

### 5. UI 上の操作フロー（案）

1. ダッシュボードページを開く
2. 「グラフを追加」ボタン → モーダルでグラフ種・時間範囲・系列を設定
3. グラフはカード形式で並ぶ（ドラッグ＆ドロップで並び替え、または sort_order 手入力）
4. 各グラフに編集・削除ボタン

### 6. グラフ描画ライブラリ

- **Chart.js** が現実的（すでに軽量 JS ライブラリ路線のアプリなら相性よい）
- CDN から読み込むだけで動く、学習コスト低

---

## 実装順序（案）

1. DBスキーマ追加（`dashboards` / `dashboard_graphs` / `graph_series`）
2. データ取得 API（グラフ設定一覧、系列データ）
3. グラフ描画（Chart.js）
4. グラフ追加・編集・削除 UI
5. 並び替え
6. （後から）科目合算系列、会計年度フィルタ
