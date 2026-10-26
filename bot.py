import asyncio
import sys
import os
from playwright.async_api import async_playwright

LOGIN_URL = "https://eduon.adu.uz"
DARSLAR_URL = "https://eduon.adu.uz/dashboard/student/live"
COOKIES_FILE = "cookies.json"

ONEID_LOGIN = "998907721203"       
ONEID_PASSWORD = "RuUAtp8f8jYRVj"   

async def run_bot():
    async with async_playwright() as p:
        print("💡 [1/5] Brauzer ishga tushmoqda...")
        browser = await p.chromium.launch(
            headless=True, 
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
        )
        
        # 1-BOSQICH: Keshdan eski cookies faylini tekshirish
        if os.path.exists(COOKIES_FILE):
            print("🍪 Esda saqlangan cookies topildi, yuklanmoqda...")
            context = await browser.new_context(
                storage_state=COOKIES_FILE,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                viewport={"width": 1280, "height": 800}
            )
        else:
            print("🔒 Avvaldan saqlangan cookies topilmadi. Toza sessiya ochildi.")
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                viewport={"width": 1280, "height": 800}
            )

        page = await context.new_page()
        page.set_default_timeout(60000) # Kutish limiti 60 soniya
        
        # 2-BOSQICH: Loginsiz to'g'ridan-to'g'ri dars sahifasiga kirishga urinish
        print("💡 [2/5] Loginsiz to'g'ridan-to'g'ri dars sahifasiga kirish urinilmoqda...")
        need_login = False
        try:
            await page.goto(DARSLAR_URL, timeout=45000)
            await asyncio.sleep(5) # Sahifa barqarorlashishi uchun qisqa kutish
            
            # Agar sahifa bizni loginga haydasa yoki kirish maydonlari ko'rinib qolsa
            current_url = page.url
            if "login" in current_url or await page.locator("input[type='text'], input[type='password']").is_visible():
                print("⚠️ Tizim login so'radi! OneID orqali avtorizatsiyaga o'tiladi...")
                need_login = True
            else:
                print("✔️ Ajoyib! Sessiya faol, login talab qilinmadi.")
        except Exception as e:
            print(f"⚠️ Dars sahifasiga to'g'ridan-to'g'ri kirib bo'lmadi, login sahifasi tekshiriladi: {e}")
            need_login = True

        # 3-BOSQICH: Agar login so'rasa, OneID tizimidan o'tish
        if need_login:
            print("💡 [3/5] OneID orqali tizimga kirish boshlandi...")
            try:
                if LOGIN_URL not in page.url:
                    await page.goto(LOGIN_URL, timeout=45000)
                    await asyncio.sleep(5)

                # OneID tugmasi bormi?
                oneid_btn = page.locator("text=OneID, .btn-primary, a[href*='oneid']").first
                if await oneid_btn.is_visible():
                    print("🔗 OneID orqali kirish tugmasi bosilmoqda...")
                    await oneid_btn.click()
                    await asyncio.sleep(5)

                # Input maydonlarini to'ldirish
                input_field = page.locator("input[type='text'], input[name='username'], input[placeholder*='login']").first
                await input_field.wait_for(state="visible", timeout=30000)
                await input_field.fill(ONEID_LOGIN)
                
                password_field = page.locator("input[type='password'], input[name='password']").first
                await password_field.fill(ONEID_PASSWORD)
                
                print("🔑 Login va parol kiritildi. Tizimga kirilmoqda...")
                submit_btn = page.locator("button[type='submit'], input[type='submit'], text=Kirish").first
                
                async with page.expect_navigation(timeout=60000):
                    await submit_btn.click()
                
                # Yangi cookies faylini kelgusi safar uchun keshga yozish
                await context.storage_state(path=COOKIES_FILE)
                print("🍪 Yangi cookies muvaffaqiyatli saqlandi!")
                
                # Login tugagach dars sahifasiga qaytish
                await page.goto(DARSLAR_URL, timeout=45000)
            except Exception as e:
                print(f"❌ OneID login jarayonida xatolik: {e}")
                try: await page.screenshot(path="darsga_kirildi.png", full_page=True)
                except: pass
                await context.close()
                browser.close()
                sys.exit(1)

        # 4-BOSQICH: Darsni tekshirish va unga kirish
        print("💡 [4/5] Dars holati tekshirilmoqda...")
        try:
            await page.wait_for_selector("body", timeout=20000)
            page_content = await page.content()
            page_content_lower = page_content.lower()
            
            # Agar parallel bot ishlayotgan bo'lsa smooth chiqib ketish
            if "faol dars" in page_content_lower and ("kirilgan" in page_content_lower or "faol" in page_content_lower):
                print("📢 Smooth: Siz allaqachon dars xonasidasiz. Ortiqcha bot o'chirildi.")
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
                
                # Darsda o'tirish bosqichi
                print("⏳ Darsda kutish rejasi yoqildi (80.5 daqiqa)...")
                await asyncio.sleep(2400)
                print("-> [40-daqiqa] Bot darsda faol.")
                await asyncio.sleep(2430)
                print("-> [80.5-daqiqa] Dars yakunlandi.")
            else:
                print("📢 Eslatma: Hozir dars vaqti emas (yashil tugma yo'q). Bot ishni yakunladi.")
        except Exception as e:
            print(f"❌ Darsni tekshirish bosqichida xatolik: {e}")
            
        await context.close()
        await browser.close()
        print("🚀 [5/5] Protsess to'liq yakunlandi.")

if __name__ == "__main__":
    asyncio.run(run_bot())
