# sales-screenshot

毎朝、売上レポート画面のスクリーンショットを自動で撮影し、Chatworkに送信するツールです。

## 概要

GitHub Actions のワークフロー(`.github/workflows/daily_screenshot.yml`)を手動実行すると、以下の処理を行います。

1. Playwright（headless Chromium）でサイトにアクセス
   - Basic認証でトップページへアクセス
   - フォームログインでログイン
2. 売上画面（`/sales/report`）に移動し、テーブル部分だけを切り取ってスクリーンショットを撮影
3. 撮影した画像をメッセージ付きでChatworkのルームに送信

## 必要な環境変数（GitHub Secrets）

| 変数名 | 内容 |
| --- | --- |
| `APP_DOMAIN` | 対象サイトのドメイン |
| `LOGIN_ID_1` / `LOGIN_PASS_1` | Basic認証のID・パスワード |
| `LOGIN_ID_2` / `LOGIN_PASS_2` | フォームログインのID・パスワード |
| `CW_TOKEN` | Chatwork APIトークン |
| `CW_ROOM_ID` | 送信先のChatworkルームID |

## ローカルでの実行

```bash
pip install -r requirements.txt
playwright install chromium

# 上記の環境変数を設定した上で実行
python main.py
```

## ファイル構成

- `main.py` — スクリーンショット撮影とChatwork送信の処理
- `requirements.txt` — Python依存パッケージ
- `.github/workflows/daily_screenshot.yml` — GitHub Actionsワークフロー
