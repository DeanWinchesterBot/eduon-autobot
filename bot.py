import asyncio
import sys
import os
from playwright.async_api import async_playwright

# To'g'ridan-to'g'ri EduOn tizimining OneID kirish eshigi manzili qo'yildi
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
        
        if os.path.exists(COOKIES_FILE):
            print("🍪 Esda saqlangan sessiya topildi, foydalanilmoqda...")
            context = await browser.new_context(
                storage_state=COOKIES_FILE,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                viewport={"width": 1280, "height": 800}
            )
            has_session = True
        else:
            print("🔒 Sessiya topilmadi, yangi login qilinadi...")
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                viewport={"width": 1280, "height": 800}
            )
            has_session = False

        page = await context.new_page()
        page.set_default_timeout(45000) # Kutish limiti 45 soniyaga uzaytirildi
        
        if has_session:
            print("💡 [2/5] To'g'ridan-to'g'ri dars sahifasiga o'tilmoqda...")
            try:
                await page.goto(DARSLAR_URL, timeout=45000)
                await page.wait_for_selector("body", timeout=20000)
                if "login" in page.url or await page.locator("input[type='text']").is_visible():
                    print("⚠️ Sessiya eskirgan ekan, qayta login qilinadi...")
                    has_session = False
            except Exception:
                has_session = False

        if not has_session:
            print("💡 [2/5] EduOn Login sahifasiga ulanilmoqda...")
            try:
                await page.goto(LOGIN_URL, timeout=45000)
                await asyncio.sleep(5) # Sahifa to'liq yuklanishi uchun qisqa kuting
                
                # Agar OneID tugmasi bo'lsa uni bosadi, bo'lmasa to'g'ri maydonlarni qidiradi
                oneid_btn = page.locator("text=OneID orqali kirish, .btn-primary").first
                if await oneid_btn.is_visible():
                    print("🔗 OneID tugmasi topildi, bosilmoqda...")
                    await oneid_btn.click()
                    await asyncio.sleep(5)

                print("💡 [3/5] OneID identifikatsiyasi boshlandi...")
                # Turli xil muqobil maydon selectorlari qo'shildi
                input_field = page.locator("input[type='text'], input[name='username'], input[placeholder*='login']").first
                await input_field.wait_for(state="visible", timeout=30000)
                
                await input_field.fill(ONEID_LOGIN)
                await page.locator("input[type='password'], input[name='password']").first.fill(ONEID_PASSWORD)
                
                print("🔑 Login va parol kiritildi. Tizimga kirilmoqda...")
                submit_btn = page.locator("button[type='submit'], input[type='submit'], text=Kirish").first
                
                async with page.expect_navigation(timeout=45000):
                    await submit_btn.click()
                
                await context.storage_state(path=COOKIES_FILE)
                print("✔️ Yangi login bajarildi va sessiya saqlandi.")
                await page.goto(DARSLAR_URL, timeout=45000)
            except Exception as e:
                print(f"❌ Login yoki ulanish xatoligi: {e}")
                # Xatolik isboti uchun rasm olib ketamiz
                try:
                    await page.screenshot(path="darsga_kirildi.png", full_page=True)
                except:
                    pass
                await context.close()
                await browser.close()
                sys.exit(1)

        print("💡 [4/5] Dars holati tekshirilmoqda...")
        try:
            await page.wait_for_selector("body", timeout=20000)
            page_content = await page.content()
            page_content_lower = page_content.lower()
            
            if "faol dars" in page_content_lower and ("kirilgan" in page_content_lower or "faol" in page_content_lower):
                print("📢 Smooth: Siz allaqachon darsdasiz. Jarayon to'xtatildi.")
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
                print("-> [80.5-daqiqa] Dars tugadi.")
            else:
                print("📢 Eslatma: Hozir dars vaqti emas (yashil tugma yo'q). Bot darhol o'chadi.")
        except Exception as e:
            print(f"❌ Darsni tekshirishda xatolik: {e}")
            
        await context.close()
        await browser.close()
        print("🚀 Protsess yakunlandi.")

if __name__ == "__main__":
    asyncio.run(run_bot())

