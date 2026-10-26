import asyncio
import sys
import os
from playwright.async_api import async_playwright

DARSLAR_URL = "https://eduon.adu.uz/dashboard/student/live"
LOGIN_URL = "https://eduon.adu.uz"
COOKIES_FILE = "cookies.json"

ONEID_LOGIN = "asadbekhoshimov"       
ONEID_PASSWORD = "RuUAtp8f8jYRVj"   

# O'zbekiston bepul proxy manzillari ro'yxati (Blokirovkani chetlab o'tish uchun)
UZ_PROXY = "http://213.230.91.134:3128" # Agar bu proxy o'chsa, boshqa UZ proxy qo'yiladi

async def run_bot():
    async with async_playwright() as p:
        print("💡 [1/5] O'zbekiston Proxy serveri orqali brauzer ishga tushmoqda...")
        browser = await p.chromium.launch(
            headless=True, 
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
        )
        
        # Brauzer kontekstiga O'zbekiston proxy manzilini ulaymiz
        context_args = {
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "viewport": {"width": 1280, "height": 800},
            "proxy": {"server": UZ_PROXY} # UZ IP yoqildi
        }
        
        if os.path.exists(COOKIES_FILE):
            print("🍪 Esda saqlangan cookies topildi, yuklanmoqda...")
            context_args["storage_state"] = COOKIES_FILE
            context = await browser.new_context(**context_args)
            has_session = True
        else:
            print("🔒 Avvaldan saqlangan cookies topilmadi. Toza sessiya ochildi.")
            context = await browser.new_context(**context_args)
            has_session = False

        page = await context.new_page()
        page.set_default_timeout(60000)
        
        print("💡 [2/5] Loginsiz to'g'ridan-to'g'ri dars sahifasiga kirish urinilmoqda...")
        need_login = False
        try:
            await page.goto(DARSLAR_URL, timeout=45000)
            await asyncio.sleep(5)
            if "login" in page.url:
                print("⚠️ Tizim login so'radi! OneID avtorizatsiyasiga o'tiladi...")
                need_login = True
            else:
                print("✔️ Ajoyib! Sessiya faol, login talab qilinmadi.")
        except Exception as e:
            print(f"⚠️ Dars sahifasiga to'g'ridan-to'g'ri kirib bo'lmadi: {e}")
            need_login = True

        if need_login:
            print("💡 [3/5] EduOn Login sahifasiga ulanilmoqda...")
            try:
                await page.goto(LOGIN_URL, timeout=45000)
                await asyncio.sleep(5)

                oneid_btn = page.locator("text=OneID orqali kirish, .btn-primary, a[href*='oneid']").first
                
                async with context.expect_page() as new_page_info:
                    await oneid_btn.click()
                oneid_page = await new_page_info.value
                await oneid_page.set_default_timeout(60000)
                
                print("🔗 id.egov.uz sahifasi muvaffaqiyatli ochildi! Inputlar to'ldirilmoqda...")
                await asyncio.sleep(5)

                input_field = oneid_page.locator("input[placeholder*='Login'], input[type='text'], #username").first
                await input_field.wait_for(state="visible", timeout=45000)
                await input_field.fill(ONEID_LOGIN)
                
                password_field = oneid_page.locator("input[placeholder*='Parol'], input[type='password'], #password").first
                await password_field.fill(ONEID_PASSWORD)
                
                print("🔑 Ma'lumotlar kiritildi. 'Kirish' tugmasi bosilmoqda...")
                submit_btn = oneid_page.locator("button:has-text('Kirish'), button[type='submit'], .btn-primary, #submitBtn").first
                
                async with oneid_page.expect_navigation(timeout=60000):
                    await submit_btn.click()
                print("⏳ EduOn platformasiga qaytish kutilmoqda...")
                await asyncio.sleep(12) 
                
                await context.storage_state(path=COOKIES_FILE)
                print("🍪 Yangi cookies muvaffaqiyatli saqlandi!")
                await page.goto(DARSLAR_URL, timeout=45000)
            except Exception as e:
                print(f"❌ OneID login qismida xatolik: {e}")
                try: await page.screenshot(path="oneid_xato.png", full_page=True)
                except: pass
                await context.close()
                await browser.close()
                sys.exit(1)

        print("💡 [4/5] Dars holati tekshirilmoqda...")
        try:
            await page.wait_for_selector("body", timeout=20000)
            page_content = await page.content()
            page_content_lower = page_content.lower()
            
            if "faol dars" in page_content_lower and ("kirilgan" in page_content_lower or "faol" in page_content_lower):
                print("📢 Smooth: Siz allaqachon dars xonasidasiz. Bot yopildi.")
                await context.close()
                await browser.close()
                sys.exit(0)
                
            dars_linki = page.locator("text=Kirish").first
            
            if await dars_linki.is_visible():
                await dars_linki.click()
                print("=======================================================")
                print("🎉 MUVAFFAQIYATLI: Dars xonasiga kirildi!")
                print("=======================================================")
                
                await asyncio.sleep(5)
                await page.screenshot(path="darsga_kirildi.png", full_page=True)
                
                print("⏳ Darsda kutish rejasi yoqildi (80.5 daqiqa)...")
                await asyncio.sleep(2400)
                print("-> [40-daqiqa] Bot faol.")
                await asyncio.sleep(2430)
                print("-> [80.5-daqiqa] Dars yakunlandi.")
            else:
                print("📢 Eslatma: Hozir dars vaqti emas. Bot ishni yakunlandi.")
        except Exception as e:
            print(f"❌ Dars bosqichida xatolik: {e}")
            
        await context.close()
        await browser.close()
        print("🚀 [5/5] Protsess to'liq yakunlandi.")

if __name__ == "__main__":
    asyncio.run(run_bot())
