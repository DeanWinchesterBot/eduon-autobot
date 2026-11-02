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
EDUON_LOCALSTORAGE = os.getenv("EDUON_LOCALSTORAGE")  # Safari'dan olingan localStorage JSON (GitHub Secret)
WAIT_MINUTES = int(os.getenv("WAIT_MINUTES", "0"))  # 0 = kutmaydi, topilmasa darrov tugaydi

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
            try:
                await page.wait_for_load_state("networkidle", timeout=20000)
            except Exception:
                pass
            await asyncio.sleep(3)
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


async def whoami(page):
    """Sayt sizni kim deb bilishini tekshiradi (shaxsiy qiymatlarsiz, faqat tuzilma)."""
    try:
        res = await page.evaluate("""async () => {
            try {
                const r = await fetch('/bff/api/telegram/me', {credentials: 'include'});
                let j = null;
                try { j = await r.json(); } catch (e) {}
                const shape = {};
                if (j && typeof j === 'object') {
                    for (const k of Object.keys(j).slice(0, 15)) {
                        const v = j[k];
                        shape[k] = v === null ? 'null' : (typeof v === 'object' ? 'object' : typeof v);
                    }
                }
                return {status: r.status, shape: shape};
            } catch (e) { return {error: String(e)}; }
        }""")
        print(f"🪪 /me javobi: {res}")
        keys = await page.evaluate("() => Object.keys(localStorage)")
        print(f"🗂 localStorage kalitlari: {keys}")
    except Exception as e:
        print(f"⚠️ whoami xatosi: {e}")


async def dump_page(page):
    """Tugma topilmaganda: bot nimani ko'rayotganini logga chiqaradi."""
    try:
        print(f"🔎 Joriy manzil: {page.url}")
        print(f"🔎 Sahifa sarlavhasi: {await page.title()}")
        info = await page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('*').forEach(el => {
                const t = (el.innerText || '').trim();
                if (t.length > 0 && t.length < 40 && /kirish/i.test(t) && el.children.length < 3) {
                    const r = el.getBoundingClientRect();
                    out.push(el.tagName + ' | class=' + (el.className || '').toString().slice(0, 60)
                        + ' | text=' + t.replace(/\\s+/g, ' ')
                        + ' | ' + Math.round(r.width) + 'x' + Math.round(r.height));
                }
            });
            return out.slice(0, 15);
        }""")
        print(f"🔎 'Kirish' so'zi bor elementlar ({len(info)} ta):")
        for line in info:
            print("   -", line)
        body = (await page.inner_text("body"))[:1200].replace("\n", " | ")
        print(f"🔎 Sahifa matni: {body}")
    except Exception as e:
        print(f"⚠️ Diagnostika xatosi: {e}")


async def run_bot():
    tashkent = datetime.now(timezone(timedelta(hours=5))).strftime("%H:%M")
    print(f"🕒 Bot ishga tushdi: Toshkent vaqti {tashkent}")
    async with async_playwright() as p:
        print("💡 [1/5] Brauzer ishga tushmoqda...")
        launch_args = ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        context_args = {
            "user_agent": USER_AGENT,
            "viewport": {"width": 1280, "height": 800},
            "timezone_id": "Asia/Tashkent",  # sayt dars vaqtini brauzer soatiga qarab hisoblaydi
            "locale": "uz-UZ",
        }
        if os.path.exists(COOKIES_FILE) and not EDUON_COOKIES:
            print("🍪 Saqlangan sessiya (kesh) yuklanmoqda...")
            context_args["storage_state"] = COOKIES_FILE
        elif EDUON_COOKIES:
            print("🍪 Secret'dagi cookies ishlatiladi (kesh e'tiborga olinmaydi).")

        browser = await p.chromium.launch(headless=True, args=launch_args)
        context = await browser.new_context(**context_args)
        if EDUON_LOCALSTORAGE:
            try:
                json.loads(EDUON_LOCALSTORAGE)  # to'g'ri JSON ekanini tekshirish
                init_js = (
                    "(() => { if (location.hostname !== 'eduon.adu.uz') return;"
                    " let d = {}; try { d = JSON.parse(" + json.dumps(EDUON_LOCALSTORAGE) + "); } catch (e) {}"
                    " for (const k in d) { try { if (localStorage.getItem(k) === null)"
                    " localStorage.setItem(k, d[k]); } catch (e) {} } })();"
                )
                await context.add_init_script(init_js)
                print("🗂 Secret'dagi localStorage qo'yiladi.")
            except Exception as e:
                print(f"⚠️ EDUON_LOCALSTORAGE JSON emas: {e}")

        page = await context.new_page()
        page.set_default_timeout(45000)

        seen_urls = set()

        def log_response(resp):
            try:
                rtype = resp.request.resource_type
                path = resp.url.split("?")[0][:110]
                if rtype in ("xhr", "fetch") and (resp.status, path) not in seen_urls and len(seen_urls) < 60:
                    seen_urls.add((resp.status, path))
                    print(f"   🌐 {resp.status} {path}")
            except Exception:
                pass

        page.on("response", log_response)

        try:
            # Kesh bo'sh bo'lsa, boshidanoq Secret'dagi cookies'ni qo'yamiz
            seed_used = False
            if EDUON_COOKIES:
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
                await whoami(page)
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

                # Matni aynan "Kirish" bo'lgan, ko'rinib turgan istalgan element (a, button, div...)
                kirish_btn = page.get_by_text("Kirish", exact=True).locator("visible=true").first

                print(f"🔍 'Kirish' tugmasi kutilmoqda (kutish: {WAIT_MINUTES} daqiqa)...")
                deadline = time.monotonic() + WAIT_MINUTES * 60
                found = False
                while True:
                    try:
                        # wait_for haqiqatan kutadi (is_visible esa kutmaydi)
                        await kirish_btn.wait_for(state="visible", timeout=10000)
                        found = True
                        break
                    except Exception:
                        pass
                    try:
                        await page.screenshot(path="kutish.png", full_page=True)
                    except Exception:
                        pass
                    if time.monotonic() >= deadline:
                        break
                    print("⏳ Tugma hali ko'rinmadi, 60 soniyadan keyin qayta tekshiriladi...")
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
                    print("📢 Faol dars topilmadi ('Kirish' tugmasi ko'rinmadi).")
                    await page.screenshot(path="dars_yoq.png", full_page=True)
                    await dump_page(page)
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
