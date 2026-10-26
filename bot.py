import asyncio
import sys
import os
from playwright.async_api import async_playwright

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DARSLAR_URL = "https://eduon.adu.uz/dashboard/student/live"
COOKIES_FILE = "cookies.json"

ONEID_LOGIN = os.getenv("ONEID_LOGIN")
ONEID_PASSWORD = os.getenv("ONEID_PASSWORD")

async def run_bot():
    if not ONEID_LOGIN or not ONEID_PASSWORD:
        print("❌ XATOLIK: ONEID_LOGIN yoki ONEID_PASSWORD topilmadi!")
        sys.exit(1)

    async with async_playwright() as p:
        print("💡 [1/5] Brauzer ishga tushmoqda...")
        
        launch_args = ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
        
        context_args = {
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "viewport": {"width": 1280, "height": 800},
        }

        if os.path.exists(COOKIES_FILE):
            print("🍪 Saqlangan cookies yuklanmoqda...")
            context_args["storage_state"] = COOKIES_FILE

        browser = await p.chromium.launch(headless=True, args=launch_args)
        context = await browser.new_context(**context_args)
        page = await context.new_page()
        page.set_default_timeout(45000)

        print("💡 [2/5] EduOn jonli darslar sahifasiga kirilmoqda...")
        need_login = False
        try:
            await page.goto(DARSLAR_URL, wait_until="domcontentloaded")
            await asyncio.sleep(3)
            if "login" in page.url or "id.egov.uz" in page.url or "auth" in page.url:
                print("⚠️ Tizim avtorizatsiya so'radi.")
                need_login = True
            else:
                print("✔️ Sessiya faol, login talab qilinmadi.")
        except Exception as e:
            print(f"⚠️ Sahifaga kirib bo'lmadi: {e}")
            need_login = True

        # ONEID ORQALI KIRISH (Tugmani qidirmasdan to'g'ridan-to'g'ri o'tamiz)
        if need_login:
            print("💡 [3/5] OneID tizimiga to'g'ridan-to'g'ri o'tilmoqda...")
            try:
                # Eduon'ning OneID ga yo'naltiruvchi sahifasiga o'tamiz
                await page.goto("https://eduon.adu.uz/auth/oneid", wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(4)

                # Agar avtomatik o'tmasa, id.egov.uz ga o'zimiz majburiy boramiz
                if "id.egov.uz" not in page.url:
                    await page.goto("https://id.egov.uz/oz/oauth2/authorize?response_type=code&client_id=eduon_adu_uz&redirect_uri=https://eduon.adu.uz/auth/oneid/callback", wait_until="domcontentloaded")
                    await asyncio.sleep(3)

                print("👤 Ma'lumotlar kiritilmoqda...")

                # id.egov.uz dagi birinchi va ikkinchi inputlar (Login va Parol)
                inputs = page.locator("input[type='text'], input[type='tel'], input:not([type])")
                await inputs.first.wait_for(state="visible", timeout=30000)
                
                await inputs.first.fill(ONEID_LOGIN)

                password_input = page.locator("input[type='password']").first
                await password_input.wait_for(state="visible", timeout=15000)
                await password_input.fill(ONEID_PASSWORD)

                # Kirish tugmasi
                submit_btn = page.locator("button[type='submit'], button:has-text('Kirish')").first
                
                print("🔑 OneID 'Kirish' tugmasi bosilmoqda...")
                await submit_btn.click()

                # Eduon'ga muvaffaqiyatli qaytib kelishini kutish
                await page.wait_for_url(lambda url: "eduon.adu.uz" in url, timeout=60000)
                
                # Cookies saqlash
                await context.storage_state(path=COOKIES_FILE)
                print("🍪 Yangi cookies muvaffaqiyatli saqlandi!")
                
                await page.goto(DARSLAR_URL, wait_until="domcontentloaded")

            except Exception as e:
                print(f"❌ OneID login jarayonida xatolik: {e}")
                try:
                    await page.screenshot(path="oneid_xato.png", full_page=True)
                except:
                    pass
                await browser.close()
                sys.exit(1)

        print("💡 [4/5] 'Jonli darslar' bo'limi tekshirilmoqda...")
        try:
            if "live" not in page.url:
                await page.goto(DARSLAR_URL, wait_until="domcontentloaded")
                await asyncio.sleep(3)

            print("🔍 Faol dars va 'Kirish' tugmasi qidirilmoqda...")
            kirish_btn = page.locator("a:has-text('Kirish'), button:has-text('Kirish'), .btn-success").first
            
            if await kirish_btn.is_visible(timeout=15000):
                await kirish_btn.click()
                print("=======================================================")
                print("🎉 MUVAFFAQIYATLI: Jonli dars xonasiga kirildi!")
                print("=======================================================")
                
                await asyncio.sleep(5)
                await page.screenshot(path="darsga_kirildi.png", full_page=True)

                print("⏳ Dars boshlandi. 1 soat 20 daqiqa davomida darsda qatnashilmoqda...")
                await asyncio.sleep(4800) 
            else:
                print("📢 Hozir faol efirda dars mavjud emas ('Kirish' tugmasi topilmadi).")
                await page.screenshot(path="dars_yoq.png", full_page=True)
                
        except Exception as e:
            print(f"❌ Dars jarayonida xatolik: {e}")
            try:
                await page.screenshot(path="dars_xato.png", full_page=True)
            except:
                pass

        await context.close()
        await browser.close()
        print("🚀 [5/5] Bot o'z ishini muvaffaqiyatli yakunladi.")

if __name__ == "__main__":
    asyncio.run(run_bot())
