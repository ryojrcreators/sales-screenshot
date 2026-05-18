import os
import re
import requests
from datetime import datetime
from urllib.parse import quote
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync
from PIL import Image

# ===== 設定（環境変数から読み込み） =====
DOMAIN = "app.jrcreators.com"

# Amazon配送チェック設定
AMAZON_ASIN = "B0CK55YG5W"
AMAZON_TARGET_SELLERS = ["Shop LA!", "カリフォルニアマート"]

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

MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
    "January": 1, "February": 2, "March": 3, "April": 4, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10,
    "November": 11, "December": 12,
}


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


def check_amazon_delivery() -> dict:
    """Amazon出品一覧からShop LA!とカリフォルニアマートの配送予定日テキストを返す"""
    result = {seller: None for seller in AMAZON_TARGET_SELLERS}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--force-color-profile=srgb"],
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 1024},
            device_scale_factor=DEVICE_SCALE_FACTOR,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        page = context.new_page()
        stealth_sync(page)

        url = f"https://www.amazon.com/gp/offer-listing/{AMAZON_ASIN}/"
        print(f"Amazonオファーページを開いています: {url}")
        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
        except Exception as e:
            print(f"ページ読み込みエラー: {e}")
        page.wait_for_timeout(3000)

        # オファーブロックを複数のセレクタで試みる
        found_blocks = False
        for selector in ["div.olpOffer", "#aod-offer", "[id^='aod-offer-']"]:
            blocks = page.locator(selector).all()
            if blocks:
                print(f"セレクタ '{selector}' で {len(blocks)} ブロック取得")
                for block in blocks:
                    text = block.inner_text() or ""
                    for seller in AMAZON_TARGET_SELLERS:
                        if seller in text and result[seller] is None:
                            date_text = _find_delivery_text(text)
                            if date_text:
                                result[seller] = date_text
                                print(f"  {seller}: {date_text}")
                found_blocks = True
                break

        # フォールバック：ページ全体テキストから前後行で解析
        if not found_blocks or all(v is None for v in result.values()):
            print("フォールバック: ページ全体テキストから解析")
            full_text = page.inner_text("body")
            lines = full_text.split("\n")
            for i, line in enumerate(lines):
                for seller in AMAZON_TARGET_SELLERS:
                    if seller in line and result[seller] is None:
                        context_lines = lines[max(0, i - 2):i + 8]
                        for ctx in context_lines:
                            date_text = _find_delivery_text(ctx)
                            if date_text:
                                result[seller] = date_text
                                print(f"  {seller}: {date_text} (フォールバック)")
                                break

        browser.close()

    return result


def _find_delivery_text(text: str) -> str | None:
    """テキストから配送日を含む行を抽出する"""
    for line in text.split("\n"):
        line = line.strip()
        if line and re.search(r"(Arrives?|Delivers?|Ships?|Get it)", line, re.IGNORECASE):
            return line
    return None


def _format_delivery_line(label: str, raw_text: str | None) -> str:
    """配送日テキストを 'LABEL - Month D - Month D ( X - Y days )' 形式にフォーマット"""
    if not raw_text:
        return f"{label} - N/A"

    m = re.search(r'(\w+)\s+(\d+)\s*[-–]\s*(?:(\w+)\s+)?(\d+)', raw_text)
    if not m:
        return f"{label} - {raw_text}"

    month1_str, day1_str, month2_str, day2_str = m.groups()
    month1 = MONTHS.get(month1_str)
    month2 = MONTHS.get(month2_str) if month2_str else month1

    if not month1 or not month2:
        return f"{label} - {raw_text}"

    today_dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    year = today_dt.year

    try:
        date1 = datetime(year, month1, int(day1_str))
        date2 = datetime(year, month2, int(day2_str))

        if date1 < today_dt:
            date1 = date1.replace(year=year + 1)
        if date2 < date1:
            date2 = date2.replace(year=date2.year + 1)

        # 今日を1日目として計算
        days1 = (date1 - today_dt).days + 1
        days2 = (date2 - today_dt).days + 1

        if month2_str:
            date_range = f"{month1_str} {day1_str} - {month2_str} {day2_str}"
        else:
            date_range = f"{month1_str} {day1_str} - {month1_str} {day2_str}"

        return f"{label} - {date_range} ( {days1} - {days2} days )"
    except ValueError:
        return f"{label} - {raw_text}"


def send_to_chatwork(delivery_info: dict | None = None):
    """Chatworkにメッセージ＋画像を送信する"""
    la_raw = delivery_info.get("Shop LA!") if delivery_info else None
    ca_raw = delivery_info.get("カリフォルニアマート") if delivery_info else None

    la_line = _format_delivery_line("LA", la_raw)
    ca_line = _format_delivery_line("CA", ca_raw)

    message = f"Today's Rate:　{today}\n{la_line}\n{ca_line}"

    headers = {"X-ChatWorkToken": CW_TOKEN}

    # メッセージ送信
    msg_url = f"https://api.chatwork.com/v2/rooms/{CW_ROOM_ID}/messages"
    msg_response = requests.post(msg_url, headers=headers, data={"body": message})
    if msg_response.status_code == 200:
        print("メッセージを送信しました")
    else:
        print(f"メッセージ送信失敗: {msg_response.text}")

    file_url = f"https://api.chatwork.com/v2/rooms/{CW_ROOM_ID}/files"

    # 売上スクリーンショット送信
    with open(screenshot_path, "rb") as f:
        res = requests.post(
            file_url,
            headers=headers,
            files={"file": (screenshot_path, f, "image/png")},
            data={"message": ""},
        )
    if res.status_code == 200:
        print("売上スクリーンショットを送信しました")
    else:
        print(f"売上ファイル送信失敗: {res.text}")


if __name__ == "__main__":
    print(f"=== 売上スクリーンショット送信 {today} ===")
    take_screenshot()

    print(f"\n=== Amazon配送予定日チェック {today} ===")
    delivery_info = check_amazon_delivery()

    send_to_chatwork(delivery_info)
    print("=== 完了 ===")
