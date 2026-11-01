import asyncio
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

from playwright.async_api import async_playwright

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DARSLAR_URL = "https://eduon.adu.uz/dashboard/student/live"
LOGIN_URL = "https://eduon.adu.uz/login"
COOKIES_FILE = "cookies.json"

ONEID_LOGIN = os.getenv("ONEID_LOGIN")
ONEID_PASSWORD = os.getenv("ONEID_PASSWORD")
EDUON_COOKIES = os.getenv("EDUON_COOKIES")  # Cookie-Editor JSON (GitHub Secret)
WAIT_MINUTES = int(os.getenv("WAIT_MINUTES", "20"))  # dars tugmasini necha daqiqa kutish

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def load_seed_cookies(raw):
    """Cookie-Editor JSON formatini Playwright formatiga o'giradi."""
    try:
        data = json.loads(raw)
    except Exception as e:
        print(f"⚠️ EDUON_COOKIES JSON emas: {e}")
        return []

    same_site_map = {"no_restriction": "None", "none": "None", "lax": "Lax", "strict": "Strict"}
    result = []
    for c in data:
        try:
            item = {
                "name": c["name"],
                "value": c["value"],
                "domain": c["domain"],
                "path": c.get("path", "/"),
                "secure": bool(c.get("secure", False)),
                "httpOnly": bool(c.get("httpOnly", False)),
                "sameSite": same_site_map.get(str(c.get("sameSite", "")).lower(), "Lax"),
            }
            if c.get("expirationDate") and not c.get("session"):
                item["expires"] = float(c["expirationDate"])
            if item["sameSite"] == "None":
                item["secure"] = True
            result.append(item)
        except Exception as e:
            print(f"⚠️ Cookie o'tkazib yuborildi: {e}")
    return result


def is_login_url(url):
    return any(x in url for x in ("/login", "id.egov.uz", "/auth", "oauth"))


async def check_session(page):
    """Dars sahifasini 3 marta urinib ochadi.
    True = sessiya faol, False = login kerak, None = sayt umuman ochilmadi."""
    for attempt in range(1, 4):
        try:
            await page.goto(DARSLAR_URL, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(4)
            return not is_login_url(page.url)
        except Exception as e:
            print(f"⚠️ Urinish {attempt}/3 muvaffaqiyatsiz: {str(e).splitlines()[0]}")
            await asyncio.sleep(10)
    return None


async def oneid_login(page, context):
    if not ONEID_LOGIN or not ONEID_PASSWORD:
        print("❌ ONEID_LOGIN yoki ONEID_PASSWORD topilmadi!")
        return False

    page.set_default_timeout(120000)
    try:
        print("🔗 Eduon login sahifasiga o'tilmoqda...")
        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)

        # OneID tugmasi topilmasa, aniq xato chiqsin (jimgina o'tkazib yubormaymiz)
        oneid_btn = page.locator(
            "a:has-text('OneID'), button:has-text('OneID'), a[href*='oneid']"
        ).first
        await oneid_btn.click(timeout=15000)

        print("👤 OneID sahifasi ochildi. Ma'lumotlar kiritilmoqda...")
        await asyncio.sleep(3)

        username_input = page.locator(
            "input[type='text'], input[type='tel'], input[name='login']"
        ).first
        await username_input.wait_for(state="visible", timeout=60000)
        await username_input.fill(ONEID_LOGIN)

        password_input = page.locator("input[type='password']").first
        await password_input.wait_for(state="visible", timeout=30000)
        await password_input.fill(ONEID_PASSWORD)

        print("🔑 'Kirish' tugmasi bosilmoqda...")
        await page.locator("button[type='submit'], button:has-text('Kirish')").first.click()

        await page.wait_for_url(lambda url: "eduon.adu.uz" in url, timeout=120000)
        await context.storage_state(path=COOKIES_FILE)
        print("🍪 Sessiya saqlandi!")
        return True
    except Exception as e:
        print(f"❌ OneID login jarayonida xatolik: {e}")
        try:
            await page.screenshot(path="oneid_xato.png", full_page=True)
        except Exception:
            pass
        return False
    finally:
        page.set_default_timeout(45000)


async def run_bot():
    tashkent = datetime.now(timezone(timedelta(hours=5))).strftime("%H:%M")
    print(f"🕒 Bot ishga tushdi: Toshkent vaqti {tashkent}")
    async with async_playwright() as p:
        print("💡 [1/5] Brauzer ishga tushmoqda...")
        launch_args = ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        context_args = {
            "user_agent": USER_AGENT,
            "viewport": {"width": 1280, "height": 800},
        }
        if os.path.exists(COOKIES_FILE):
            print("🍪 Saqlangan sessiya (kesh) yuklanmoqda...")
            context_args["storage_state"] = COOKIES_FILE

        browser = await p.chromium.launch(headless=True, args=launch_args)
        context = await browser.new_context(**context_args)
        page = await context.new_page()
        page.set_default_timeout(45000)

        try:
            # Kesh bo'sh bo'lsa, boshidanoq Secret'dagi cookies'ni qo'yamiz
            seed_used = False
            if not os.path.exists(COOKIES_FILE) and EDUON_COOKIES:
                seed = load_seed_cookies(EDUON_COOKIES)
                if seed:
                    await context.add_cookies(seed)
                    seed_used = True
                    print("🍪 Boshlang'ich cookies (Secret) qo'yildi.")

            print("💡 [2/5] EduOn jonli darslar sahifasiga kirilmoqda...")
            logged_in = await check_session(page)

            if logged_in is None:
                print("❌ EduOn sayti 3 urinishda ham ochilmadi (tarmoq/IP muammosi).")
                print("   Ishni qayta ishga tushiring (Re-run).")
                sys.exit(1)

            # Kesh eskirgan bo'lsa, Secret'dagi cookies bilan urinib ko'ramiz
            if not logged_in and EDUON_COOKIES and not seed_used:
                print("🍪 Kesh eskirgan, Secret'dagi cookies bilan urinilmoqda...")
                seed = load_seed_cookies(EDUON_COOKIES)
                if seed:
                    await context.clear_cookies()
                    await context.add_cookies(seed)
                    logged_in = await check_session(page)
                    if logged_in is None:
                        print("❌ EduOn sayti ochilmadi.")
                        sys.exit(1)

            if logged_in:
                print("✔️ Sessiya faol, login talab qilinmadi.")
            else:
                print("⚠️ Tizim avtorizatsiya so'radi.")
                print("💡 [3/5] OneID orqali tizimga kirish boshlandi...")
                if not await oneid_login(page, context):
                    await browser.close()
                    sys.exit(1)
                await page.goto(DARSLAR_URL, wait_until="domcontentloaded")
                await asyncio.sleep(3)

            await context.storage_state(path=COOKIES_FILE)

            print("💡 [4/5] 'Jonli darslar' bo'limi tekshirilmoqda...")
            try:
                if "live" not in page.url:
                    await page.goto(DARSLAR_URL, wait_until="domcontentloaded")
                    await asyncio.sleep(3)

                kirish_btn = page.locator(
                    "a:has-text('Kirish'), button:has-text('Kirish'), .btn-success"
                ).first

                print(f"🔍 'Kirish' tugmasi kutilmoqda (eng ko'pi bilan {WAIT_MINUTES} daqiqa)...")
                deadline = time.monotonic() + WAIT_MINUTES * 60
                found = False
                while True:
                    try:
                        if await kirish_btn.is_visible(timeout=5000):
                            found = True
                            break
                    except Exception:
                        pass
                    if time.monotonic() >= deadline:
                        break
                    await asyncio.sleep(60)
                    try:
                        await page.reload(wait_until="domcontentloaded", timeout=60000)
                        await asyncio.sleep(3)
                        if is_login_url(page.url):
                            print("⚠️ Kutish paytida sessiya tugadi.")
                            break
                    except Exception as e:
                        print(f"⚠️ Sahifani yangilab bo'lmadi: {str(e).splitlines()[0]}")

                if found:
                    await kirish_btn.click()
                    print("🎉 MUVAFFAQIYATLI: Jonli dars xonasiga kirildi!")
                    await asyncio.sleep(5)
                    await page.screenshot(path="darsga_kirildi.png", full_page=True)
                    await context.storage_state(path=COOKIES_FILE)

                    print("⏳ Dars boshlandi. 1 soat 20 daqiqa darsda qatnashilmoqda...")
                    await asyncio.sleep(4800)
                    await context.storage_state(path=COOKIES_FILE)
                else:
                    print("📢 Kutish vaqtida faol dars topilmadi ('Kirish' tugmasi chiqmadi).")
                    await page.screenshot(path="dars_yoq.png", full_page=True)
            except Exception as e:
                print(f"❌ Dars jarayonida xatolik: {e}")
                try:
                    await page.screenshot(path="dars_xato.png", full_page=True)
                except Exception:
                    pass
        finally:
            await context.close()
            await browser.close()

        print("🚀 [5/5] Bot o'z ishini yakunladi.")


if __name__ == "__main__":
    asyncio.run(run_bot())
