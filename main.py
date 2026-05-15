import os
import requests
from datetime import datetime
from urllib.parse import quote
from playwright.sync_api import sync_playwright

# ===== 設定（環境変数から読み込み） =====
DOMAIN = "app.jrcreators.com"

# 1枚目：Basic認証
LOGIN_ID_1 = os.environ["LOGIN_ID_1"]
LOGIN_PASS_1 = os.environ["LOGIN_PASS_1"]

# 特殊文字をURLエンコード
LOGIN_ID_1_ENC = quote(LOGIN_ID_1, safe="")
LOGIN_PASS_1_ENC = quote(LOGIN_PASS_1, safe="")

# Basic認証をURLに埋め込む
LOGIN_URL = f"https://{LOGIN_ID_1_ENC}:{LOGIN_PASS_1_ENC}@{DOMAIN}/"
SALES_URL = f"https://{LOGIN_ID_1_ENC}:{LOGIN_PASS_1_ENC}@{DOMAIN}/sales/report"

# 2枚目：フォームログイン
LOGIN_ID_2 = os.environ["LOGIN_ID_2"]
LOGIN_PASS_2 = os.environ["LOGIN_PASS_2"]

# Chatwork
CW_TOKEN = os.environ["CW_TOKEN"]
CW_ROOM_ID = os.environ["CW_ROOM_ID"]

# ===== スクリーンショット保存パス =====
today = datetime.now().strftime("%Y-%m-%d")
screenshot_path = f"screenshot_{today}.png"


def take_screenshot():
    """売上画面のスクリーンショットを撮る"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        context = browser.new_context(
            viewport={"width": 1800, "height": 900},
            device_scale_factor=2
        )
        page = context.new_page()

        # ===== ステップ1：Basic認証 =====
        print("Basic認証付きでトップページを開いています...")
        page.goto(LOGIN_URL, wait_until="networkidle")

        # ===== ステップ2：Loginボタンをクリック =====
        print("Loginボタンをクリックしています...")
        page.click('a:has-text("Login"), button:has-text("Login")')
        page.wait_for_load_state("networkidle")

        # ===== ステップ3：フォームログイン =====
        print("フォームログインを処理しています...")
        page.fill('input[name="username"]', LOGIN_ID_2)
        page.fill('input[type="password"]', LOGIN_PASS_2)
        page.click('button[type="submit"], input[type="submit"]')
        page.wait_for_load_state("networkidle")
        print("フォームログイン完了")

        # ===== 売上画面に移動 =====
        print("売上画面に移動しています...")
        page.goto(SALES_URL, wait_until="networkidle")
        page.wait_for_timeout(2000)

        # ページ全体をスクリーンショット
        page.screenshot(path=screenshot_path, full_page=True)
        print(f"スクリーンショットを保存しました: {screenshot_path}")

        browser.close()


def send_to_chatwork():
    """Chatworkにメッセージ＋画像を送信する"""
    message = f"本日の売上\n📅 {today}"

    headers = {"X-ChatWorkToken": CW_TOKEN}

    # メッセージ送信
    msg_url = f"https://api.chatwork.com/v2/rooms/{CW_ROOM_ID}/messages"
    msg_response = requests.post(
        msg_url,
        headers=headers,
        data={"body": message}
    )

    if msg_response.status_code == 200:
        print("メッセージを送信しました")
    else:
        print(f"メッセージ送信失敗: {msg_response.text}")

    # ファイル（スクリーンショット）送信
    file_url = f"https://api.chatwork.com/v2/rooms/{CW_ROOM_ID}/files"

    with open(screenshot_path, "rb") as f:
        file_response = requests.post(
            file_url,
            headers=headers,
            files={"file": (screenshot_path, f, "image/png")},
            data={"message": ""}
        )

    if file_response.status_code == 200:
        print("スクリーンショットを送信しました")
    else:
        print(f"ファイル送信失敗: {file_response.text}")


if __name__ == "__main__":
    print(f"=== 売上スクリーンショット送信 {today} ===")
    take_screenshot()
    send_to_chatwork()
    print("=== 完了 ===")
