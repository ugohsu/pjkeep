# Avahi による LAN 内ホスト名アクセス（mDNS）

> 作成日: 2026-04-12  
> ステータス: 導入済み（または導入候補）

## 概要

**Avahi** は Linux 向けの mDNS（Multicast DNS）/ DNS-SD 実装。  
同一 LAN 内のクライアントが **`ホスト名.local`** でサーバーにアクセスできるようになる。

- IP アドレスの直打ち不要
- クライアントの `/etc/hosts` 編集不要
- 専用の DNS サーバー構築不要
- **SSH も同じホスト名で使える**

macOS の「Bonjour」や Apple の Zeroconf と同じ仕組み（RFC 6762 mDNS）。

---

## サーバー側セットアップ

### 1. Avahi のインストール・起動

```bash
sudo apt install avahi-daemon
sudo systemctl enable avahi-daemon
sudo systemctl start avahi-daemon
```

### 2. ホスト名の確認・変更

```bash
# 現在のホスト名を確認
hostname

# ホスト名を変更する場合（例: myserver）
sudo hostnamectl set-hostname myserver
```

変更後のホスト名が `myserver` であれば、LAN 内から **`myserver.local`** でアクセスできる。

### 3. 動作確認

```bash
# avahi-daemon が動いているか確認
sudo systemctl status avahi-daemon

# LAN 内の mDNS ホストを一覧表示（avahi-utils が必要）
sudo apt install avahi-utils
avahi-browse -a
```

---

## クライアント側の対応状況

| OS | 必要な作業 |
|---|---|
| **macOS** | 不要（Bonjour が標準搭載） |
| **Windows 10 / 11** | 不要（mDNS が標準搭載）※ |
| **Linux** | `avahi-daemon` + `libnss-mdns` のインストールが必要 |
| **iOS / Android** | 基本的に不要（Bonjour / mDNS 対応済み） |

> ※ Windows は古いバージョンや環境によっては Bonjour（Apple 製）のインストールが必要な場合がある。

### Linux クライアントの追加設定

```bash
# パッケージインストール
sudo apt install avahi-daemon libnss-mdns

# /etc/nsswitch.conf の hosts 行を確認
# "mdns4_minimal" が含まれていれば OK
grep ^hosts /etc/nsswitch.conf
# → hosts: files mdns4_minimal [NOTFOUND=return] dns
```

---

## アクセス方法

### Web ブラウザ

```
http://myserver.local:5000/
```

（nginx でリバースプロキシしている場合は `http://myserver.local/`）

### SSH

```bash
ssh ユーザー名@myserver.local
```

通常の IP アドレスによる SSH と完全に同等。パスフレーズや鍵認証もそのまま使える。

---

## Docker 環境での注意点

このアプリは Docker コンテナで動いているが、Avahi はホスト OS のサービスとして動作するため **コンテナ側の変更は不要**。

```
LAN 内のクライアント
    ↓ myserver.local → ホスト OS の IP に解決（mDNS）
ホスト OS（Avahi がここで動く）
    ↓ ポートフォワード
Docker コンテナ（アプリ）
```

---

## Tailscale との併用

| 用途 | 推奨手段 |
|---|---|
| 自宅 LAN 内からのアクセス | Avahi（`*.local`） |
| 外出先・リモートからのアクセス | Tailscale（`docs/tailscale-remote-access.md` 参照） |

両者は競合しないため、同時に運用できる。

---

## 注意事項

- `*.local` の名前解決は **同一 LAN セグメント内のみ** 有効（ルーターをまたぐと届かない）
- ホスト名を変更した場合は `avahi-daemon` の再起動が必要: `sudo systemctl restart avahi-daemon`
- サーバー再起動後も自動起動するよう `systemctl enable` を忘れずに
