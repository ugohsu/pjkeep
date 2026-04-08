# pjkeep

複式簿記ベースの帳簿 Web アプリです。  
プロジェクト単位で帳簿（SQLite ファイル）を切り替えながら使うことを想定しています。

## 特徴

- ブラウザから操作（PC・スマートフォン対応）
- 複式簿記による仕訳入力・仕訳帳・損益計算書・貸借対照表
- 設定画面からプロジェクト（DB ファイル）をワンクリックで切り替え
- DB ファイルのダウンロード（バックアップ）
- AI を使った仕訳のバッチインポート
- ローカル単体起動 / Docker + Nginx によるサーバ運用の両対応

## 動作環境

| 形態 | 必要なもの | アクセス先 |
|------|-----------|----------|
| ローカル版 | Python 3.8+, pip | `http://localhost:5000` |
| サーバ版 | Docker, Docker Compose | `http://サーバのLAN-IP:5000` |

## クイックスタート（ローカル版）

```bash
git clone https://github.com/yourname/pjkeep.git
cd pjkeep
pip3 install -r requirements.txt
python3 app.py
```

ブラウザで `http://localhost:5000` を開き、初期設定画面で帳簿ファイルを作成します。

## クイックスタート（サーバ版）

```bash
git clone https://github.com/ugohsu/pjkeep.git
cd pjkeep
cp .env.example .env
# .env の SECRET_KEY をランダムな文字列に変更する
docker compose up -d
```

`http://サーバのLAN-IP:5000` でアクセスできます。

## 詳細ドキュメント

操作方法・各機能の詳細は [MANUAL.md](MANUAL.md) を参照してください。

## 技術スタック

- **バックエンド**: Python / Flask
- **DB**: SQLite3
- **フロントエンド**: Bootstrap 5, jQuery
- **サーバ運用**: Docker, Gunicorn, Nginx
