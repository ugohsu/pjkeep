# ダッシュボード（可視化機能）設計メモ

## 現在の実装状況

### ページ構成

- URL: `/dashboard`
- ナビゲーション: 財務諸表と元帳の間に配置
- Blueprint: `blueprints/dashboard.py`
- テンプレート: `templates/dashboard.html`
- JS: `static/js/dashboard.js`

---

### 固定ウィジェット①：比例縮尺損益計算書（月次）

**概要**

会計教育で用いられる比例縮尺財務諸表の PL 版。T字型の積み上げ棒グラフで、借方（費用）と貸方（収益）を月ごとに横並べし、収益規模と費用構造を視覚的に比較できる。

**仕様**

- グラフ種: 積み上げ棒グラフ（Chart.js 4 の `stack` オプションで2グループ）
- X軸: 月（YYYY-MM）
- 期間セレクタ: 3ヶ月（デフォルト）/ 半年 / 1年 / 全期間
- 横スクロール対応（1月あたり80px、コンテナ幅以上に動的拡張）
- スマホ対応: `touch-action: pan-x` で縦スクロールとの競合を回避

**データ構造**

| スタック | 内容 | 色 |
|---|---|---|
| 借方（左） | 費用科目（sort_order順、上位科目がグラフ上段）| 青グラデーション |
| 借方（左） | 当期純利益（利益月のみ、最下段）| 薄緑 `#DCEDC8` |
| 貸方（右） | 収益科目（sort_order順、上位科目がグラフ上段）| オレンジグラデーション |
| 貸方（右） | 当期純損失（損失月のみ、最下段）| 赤 `red` |

- 費用: `#E3F2FD`〜`#1565C0`（8段階）
- 収益: `#FFE0B2`〜`#EF6C00`（8段階、R版 `anal.Rmd` の配色を踏襲）
- Y軸上限: 表示期間内の `max(収益合計, 費用合計) × 1.05`（損失月でも見切れない）

**ツールチップ**

- `mode: 'nearest'` + `intersect: true`（ホバーしたセグメントのみ表示）
- 科目名・金額・収益合計比 % を表示
- 値が0のセグメントは非表示

**API**

```
GET /api/dashboard/pl_monthly?range=3m   # 3m / 6m / 12m / all
```

レスポンス:

```json
{
  "accounts": [{"id": 1, "name": "売上", "element": "revenues"}, ...],
  "monthly": [
    {
      "ym": "2025-10",
      "total_revenues": 500000,
      "total_expenses": 400000,
      "net_income": 100000,
      "by_account": {"1": 500000, "2": 300000}
    },
    ...
  ]
}
```

---

### 固定ウィジェット②：純資産合計の推移

**概要**

純資産合計の月次累計残高を折れ線グラフで表示する時系列チャート。

**仕様**

- グラフ種: 折れ線グラフ（塗り付き）
- X軸: 月（YYYY-MM）
- 期間セレクタ: 3ヶ月 / 半年 / 1年（デフォルト）/ 全期間
- 横スクロール対応（PLグラフと同構造）

**計算ロジック**

```
純資産合計 = 純資産科目の累計残高 + 累計純損益
```

振替（closing）は純資産科目残高に加算・累計純損益から差し引かれるため、
合計では相殺される。全期間の累計を積み上げてから表示範囲を切り出す。

**API**

```
GET /api/dashboard/equity_monthly?range=12m   # 3m / 6m / 12m / all
```

レスポンス:

```json
{
  "monthly": [
    {"ym": "2025-01", "total_equity": 1200000},
    ...
  ]
}
```

---

## 今後の拡張予定

### 1. ユーザー定義グラフ（BI ライクなダッシュボード）

固定ウィジェット以外に、ユーザーが任意のグラフを追加・並び替えできる機能。
科目ごとにグラフを大きく異なるため、固定レイアウトでは対応できないユーザー向け。

**想定 DB スキーマ**

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
    time_range   TEXT    NOT NULL DEFAULT 'all',
    time_range_n INTEGER,
    sort_order   INTEGER DEFAULT 0
);

CREATE TABLE graph_series (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    graph_id     INTEGER NOT NULL REFERENCES dashboard_graphs(id),
    label        TEXT,
    series_type  TEXT    NOT NULL,  -- 'account' | 'total_revenues' | 'total_expenses' | 'net_income'
    account_id   INTEGER REFERENCES accounts(id),
    sort_order   INTEGER DEFAULT 0
);
```

**UI フロー（案）**

1. 「グラフを追加」ボタン → モーダルでグラフ種・期間・系列を設定
2. グラフはカード形式で並ぶ
3. 各グラフに編集・削除ボタン
4. ドラッグ＆ドロップまたは sort_order 手入力で並び替え

**Y 軸の値の意味（科目種別による違い）**

| 科目種別 | グラフに使う値 |
|---|---|
| 収益・費用 | その月の発生額（月次 PL 値）|
| 資産・負債・純資産 | 月末時点の累計残高 |
| 集計値 | 同上のルールに従う |

### 2. 会計年度フィルタ

- `time_range = 'fiscal_year'` 対応
- 会計期間の開始月設定（未実装）と連動
- 現在は `all` / `last_N` のみ

### 3. 科目合算系列

- 複数科目をユーザーが束ねて1系列にする（例: 人件費＋福利厚生費）
- `graph_series` テーブルの複数レコードで表現できるよう、スキーマは複数系列対応で設計済み

### 4. 固定ウィジェットの拡張候補

- 貸借対照表の比例縮尺版（BS）
- 月次当期純損益の棒グラフ
- 費用内訳の構成比推移（面グラフ）
