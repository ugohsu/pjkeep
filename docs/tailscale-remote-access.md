# Tailscale によるリモートアクセス設計メモ

> 作成日: 2026-04-11  
> ステータス: 将来実装予定（未着手）

## 概要

外出先からアプリにアクセスするために Tailscale VPN を導入する計画。  
Tailscale は WireGuard ベースの VPN で、インターネットにポートを公開せずに安全なリモートアクセスを実現できる。

---

## 安全性

- **ゼロトラストモデル**: インターネットに直接ポートを公開しない。Tailscale ネットワーク（tailnet）内のデバイスのみがアクセス可能
- **相互認証**: デバイスごとに証明書ベースの認証。パスワード総当たり攻撃の心配がない
- **エンドツーエンド暗号化**: 通信はすべて WireGuard で暗号化される
- **ACL（アクセス制御リスト）**: 誰がどのデバイスにアクセスできるか細かく制御できる

---

## アーキテクチャ方針

**Tailscale の設定はアプリ（このリポジトリ）には含めない。**  
ホスト OS のサービスとして独立して動かす。

```
外出先のスマホ / PC
    ↓ （Tailscale VPN）
自宅サーバー（ホスト OS に Tailscale をインストール）
    ↓
Docker コンテナ（このアプリ）
```

### 理由

| 観点 | 説明 |
|------|------|
| 関心の分離 | ネットワーク層とアプリ層は別の責務 |
| 移植性 | アプリを別サーバーに移しても Tailscale 設定はそのまま |
| Docker との相性 | コンテナ外（ホスト OS）で動かす方が自然 |
| 障害の独立性 | アプリが落ちても VPN は維持できる |

---

## 導入手順（メモ）

### 1. サーバー側（Linux ホスト OS）

```bash
# インストール
curl -fsSL https://tailscale.com/install.sh | sh

# tailnet に参加（ブラウザで認証が求められる）
sudo tailscale up

# 確認
tailscale status
```

### 2. クライアント側（スマホ・PC）

Tailscale の公式アプリをインストールして同じアカウントでログインするだけ。

- iOS / Android: App Store / Google Play で「Tailscale」
- Mac / Windows: https://tailscale.com/download

### 3. アプリへのアクセス

Tailscale 接続後、サーバーの Tailscale IP（例: `100.x.x.x`）でアクセスできる。

```
http://100.x.x.x:5000/
```

`tailscale status` で表示される IP を使う。

---

## プラン

個人利用（デバイス数が少ない）なら**無料プランで十分**。

- デバイス数: 100 台まで
- ユーザー数: 1 名まで
- 料金: 無料

---

## 注意事項

- このリポジトリ（`docker-compose.yml`、`app.py` 等）には Tailscale 関連の変更は不要
- サーバーが再起動しても Tailscale が自動起動するよう `systemctl enable tailscaled` を確認すること
- ACL 設定で不要なデバイスからのアクセスを制限することを推奨
