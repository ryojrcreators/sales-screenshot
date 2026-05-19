import os
import requests
from datetime import datetime
from urllib.parse import quote
from playwright.sync_api import sync_playwright
from PIL import Image

# ===== 設定（環境変数から読み込み） =====
DOMAIN = "app.jrcreators.com"

# 1枚目：Basic認証
LOGIN_ID_1 = os.environ["LOGIN_ID_1"]
LOGIN_PASS_1 = os.environ["LOGIN_PASS_1"]

LOGIN_ID_1_ENC = quote(LOGIN_ID_1, safe="")
LOGIN_PASS_1_ENC = quote(LOGIN_PASS_1, safe="")

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

DEVICE_SCALE_FACTOR = 2


def take_screenshot():
    """売上表のスクリーンショットを撮る"""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            # GitHub Actions の headless Chromium で背景色を確実に再現するため sRGB を強制
            args=["--force-color-profile=srgb"],
        )

        context = browser.new_context(
            viewport={"width": 1800, "height": 900},
            device_scale_factor=DEVICE_SCALE_FACTOR,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
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

        # テーブル行が描画されるまで待つ
        try:
            page.wait_for_function(
                "document.querySelectorAll('table tr').length > 5",
                timeout=15000,
            )
        except Exception:
            pass

        # JavaScriptによる背景色の適用が完了するまで待つ
        try:
            page.wait_for_function(
                """() => {
                    const cells = document.querySelectorAll('table td, table th');
                    return Array.from(cells).some(cell => {
                        const bg = window.getComputedStyle(cell).backgroundColor;
                        return bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent';
                    });
                }""",
                timeout=10000,
            )
        except Exception:
            pass

        # 色付けが確定するまで追加待機
        page.wait_for_timeout(2000)

        # ===== 表部分だけスクリーンショット =====
        # ページ上の全テーブルから面積が最大のものを選ぶ（レイアウト用の細い要素を除外）
        table = _find_largest_table(page)
        box = table.bounding_box() if table else None
        print(f"対象テーブルのbounding_box: {box}")

        try:
            if table is None:
                raise RuntimeError("テーブルが見つかりませんでした")
            # Playwright がスケールを自動処理して表だけ撮影
            table.screenshot(path=screenshot_path)
            print(f"テーブルのスクリーンショットを保存しました: {screenshot_path}")
        except Exception as e:
            # フォールバック：ページ全体を撮影してから PIL で切り取り
            print(f"テーブル直接撮影失敗、全体から切り取ります: {e}")
            full_path = f"full_page_{today}.png"
            page.screenshot(path=full_path, full_page=True)
            _crop_table(full_path, box)

        browser.close()


def _find_largest_table(page):
    """ページ上の全テーブルから面積最大のものを返す"""
    tables = page.locator("table").all()
    best, best_area = None, 0
    for t in tables:
        box = t.bounding_box()
        if box:
            area = box["width"] * box["height"]
            print(f"  table: {box['width']:.0f}x{box['height']:.0f} (area={area:.0f})")
            if area > best_area:
                best_area = area
                best = t
    return best


def _crop_table(full_path: str, box: dict | None) -> None:
    """PIL でページ全体画像からテーブル部分を切り取る（フォールバック用）"""
    if box:
        scale = DEVICE_SCALE_FACTOR
        img = Image.open(full_path)
        cropped = img.crop((
            int(box["x"] * scale),
            int(box["y"] * scale),
            int((box["x"] + box["width"]) * scale),
            int((box["y"] + box["height"]) * scale),
        ))
        cropped.save(screenshot_path)
        print(f"テーブル部分を切り取りました: {screenshot_path}")
    else:
        import shutil
        shutil.copy(full_path, screenshot_path)
        print("テーブルが見つからなかったためページ全体を使用します")


def send_to_chatwork():
    """Chatworkにメッセージ＋画像を送信する"""
    message = f"本日の売上です！\nToday's Sales : {today}"

    headers = {"X-ChatWorkToken": CW_TOKEN}

    # メッセージ＋ファイル（スクリーンショット）を1つの投稿で送信
    file_url = f"https://api.chatwork.com/v2/rooms/{CW_ROOM_ID}/files"
    with open(screenshot_path, "rb") as f:
        file_response = requests.post(
            file_url,
            headers=headers,
            files={"file": (screenshot_path, f, "image/png")},
            data={"message": message},
        )
    if file_response.status_code == 200:
        print("メッセージ＋スクリーンショットを送信しました")
    else:
        print(f"ファイル送信失敗: {file_response.text}")


if __name__ == "__main__":
    print(f"=== 売上スクリーンショット送信 {today} ===")
    take_screenshot()
    send_to_chatwork()
    print("=== 完了 ===")
