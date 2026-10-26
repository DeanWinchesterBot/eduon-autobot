import asyncio
import sys
import os
from dotenv import load_dotenv
from playwright.async_api import async_playwright

# Env faylni yuklash
load_dotenv()

DARSLAR_URL = "https://eduon.adu.uz/dashboard/student/live"
LOGIN_URL = "https://eduon.adu.uz"
COOKIES_FILE = "cookies.json"

ONEID_LOGIN = os.getenv("asadbekhoshimov")
ONEID_PASSWORD = os.getenv("RuUAtp8f8jYRVj")

# O'zbekiston Proxy (Zarur bo'lsa yoqing, bo'lmasa None qiling)
UZ_PROXY = os.getenv("UZ_PROXY", None) 

async def run_bot():
    if not ONEID_LOGIN or not ONEID_PASSWORD:
        print("❌ XATOLIK: .env faylida ONEID_LOGIN yoki ONEID_PASSWORD topilmadi!")
        sys.exit(1)

    async with async_playwright() as p:
        print("💡 [1/5] Brauzer ishga tushmoqda...")
        
        launch_args = ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
        
        context_args = {
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "viewport": {"width": 1280, "height": 800},
            "permissions": ["microphone", "camera"],  # Media ruxsatlarini avtomatik berish
        }

        if UZ_PROXY:
            context_args["proxy"] = {"server": UZ_PROXY}

        if os.path.exists(COOKIES_FILE):
            print("🍪 Saqlangan cookies yuklanmoqda...")
            context_args["storage_state"] = COOKIES_FILE

        browser = await p.chromium.launch(headless=True, args=launch_args)
        context = await browser.new_context(**context_args)
        page = await context.new_page()
        page.set_default_timeout(45000)

        print("💡 [2/5] EduOn darslar sahifasiga kirilmoqda...")
        need_login = False
        try:
            await page.goto(DARSLAR_URL, wait_until="networkidle")
            if "login" in page.url or "id.egov.uz" in page.url:
                print("⚠️ Tizim avtorizatsiya so'radi.")
                need_login = True
            else:
                print("✔️ Sessiya faol, login talab qilinmadi.")
        except Exception as e:
            print(f"⚠️ To'g'ridan-to'g me'yoriy kirib bo'lmadi: {e}")
            need_login = True

        # AVTORIZATSIYA BLOKI
        if need_login:
            print("💡 [3/5] OneID orqali tizimga kirish boshlandi...")
            try:
                await page.goto(LOGIN_URL)
                
                # OneID tugmasini topish
                oneid_btn = page.locator("a[href*='oneid'], button:has-text('OneID'), .btn-primary").first
                await oneid_btn.wait_for(state="visible")
                
                # Pop-up yoki Shu sahifada yo'naltirishni to'g'ri ushlash
                async with page.expect_navigation(timeout=60000):
                    await oneid_btn.click()

                print("🔗 OneID sahifasi ochildi. Ma'lumotlar to'ldirilmoqda...")

                # Inputlarni kutish va to'ldirish
                username_input = page.locator("input[name='login'], input[placeholder*='Login'], #username").first
                await username_input.wait_for(state="visible")
                await username_input.fill(ONEID_LOGIN)

                password_input = page.locator("input[name='password'], input[type='password'], #password").first
                await password_input.fill(ONEID_PASSWORD)

                submit_btn = page.locator("button[type='submit'], #submitBtn, button:has-text('Kirish')").first
                
                print("🔑 'Kirish' tugmasi bosilmoqda...")
                await submit_btn.click()

                # Eduon'ga qaytguncha kutish
                await page.wait_for_url(lambda url: "eduon.adu.uz" in url, timeout=60000)
                
                # Cookies saqlash
                await context.storage_state(path=COOKIES_FILE)
                print("🍪 Yangi cookies saqlandi!")
                
                await page.goto(DARSLAR_URL)

            except Exception as e:
                print(f"❌ OneID login jarayonida xatolik: {e}")
                await page.screenshot(path="oneid_xato.png", full_page=True)
                await browser.close()
                sys.exit(1)

        print("💡 [4/5] Dars tugmasi va faollik tekshirilmoqda...")
        try:
            await page.wait_for_selector("body")
            
            # "Kirish" yoki "Darsga kirish" tugmasini dinamik izlash
            dars_btn = page.locator("a:has-text('Kirish'), button:has-text('Kirish'), .btn-success").first
            
            if await dars_btn.is_visible():
                await dars_btn.click()
                print("=======================================================")
                print("🎉 MUVAFFAQIYATLI: Dars xonasiga kirdingiz!")
                print("=======================================================")
                
                await page.wait_for_timeout(5000)
                await page.screenshot(path="darsga_kirildi.png", full_page=True)

                print("⏳ Darsda kutish rejasi yoqildi (80 daqiqa)...")
                await asyncio.sleep(4800) # 80 daqiqa
                print("-> Dars yakunlandi.")
            else:
                print("📢 Hozir faol dars mavjud emas.")
                
        except Exception as e:
            print(f"❌ Darsga kirishda xatolik: {e}")

        await context.close()
        await browser.close()
        print("🚀 [5/5] Bot ishini yakunladi.")

if __name__ == "__main__":
    asyncio.run(run_bot())
