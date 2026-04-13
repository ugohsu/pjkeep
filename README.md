# pjkeep

複式簿記ベースの帳簿 Web アプリです。  
プロジェクト単位で帳簿（SQLite ファイル）を切り替えながら使うことを想定しています。

## 特徴

- ブラウザから操作（PC・スマートフォン対応）
- ユーザー/パスワード認証。自分のプロジェクトのみ閲覧・編集可能
- 複式簿記による仕訳入力・仕訳帳・損益計算書・貸借対照表
- 累計純損益の任意タイミング振替（会計期間が固定されない運用に対応）
- 設定画面からプロジェクト（DB ファイル）をワンクリックで切り替え・説明文の管理
- DB ファイルのダウンロード／アップロード（バックアップ・移行）
- 勘定科目マスタの JSON エクスポート（AI への資料として活用可能）
- AI を使った仕訳のバッチインポート
- ローカル単体起動 / Docker + Nginx によるサーバ運用の両対応

## 動作環境

| 形態 | 必要なもの | アクセス先 |
|------|-----------|----------|
| ローカル版 | Python 3.8+, pip3 | `http://localhost:5000` |
| サーバ版 | Docker, Docker Compose | `http://サーバのLAN-IP:5000` |

## クイックスタート（ローカル版）

```bash
git clone https://github.com/yourname/pjkeep.git
cd pjkeep
pip3 install -r requirements.txt
python3 app.py
```

ブラウザで `http://localhost:5000` を開くと、初回のみ管理者アカウント作成画面（`/setup`）が表示されます。  
アカウントを作成してログインすると、プロジェクト設定画面に移動します。

## クイックスタート（サーバ版）

```bash
git clone https://github.com/yourname/pjkeep.git
cd pjkeep
cp .env.example .env
```

`.env` を編集して `SECRET_KEY` をランダムな文字列に変更します：

```bash
# SECRET_KEY の生成
python3 -c "import secrets; print(secrets.token_hex(32))"
```

ホストユーザーの UID/GID を確認して `.env` に記入します（ファイルのオーナー問題を防ぐため）：

```bash
echo "APP_UID=$(id -u)" >> .env
echo "APP_GID=$(id -g)" >> .env
```

起動：

```bash
docker compose up -d
```

`http://サーバのLAN-IP:5000` にアクセスすると、初回のみ管理者アカウント作成画面が表示されます。

## 詳細ドキュメント

操作方法・各機能の詳細は [MANUAL.md](docs/MANUAL.md) を参照してください。

## 技術スタック

- **バックエンド**: Python / Flask / Flask-Login
- **DB**: SQLite3
- **フロントエンド**: Bootstrap 5, jQuery
- **サーバ運用**: Docker, Gunicorn, Nginx
