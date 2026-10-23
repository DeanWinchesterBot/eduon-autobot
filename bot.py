import asyncio
import sys
from playwright.async_api import async_playwright

# TIZIM STRUKTURASI
LOGIN_URL = "https://eduon.adu.uz"
DARSLAR_URL = "https://https://https://eduon.adu.uz/dashboard/student/live"

# SIZNING AVTORIZATSIYA MA'LUMOTLARINGIZ
ONEID_LOGIN = "998907721203"       # Bu yerga telefon raqamingizni yozing
ONEID_PASSWORD = "RuUAtp8f8jYRVj"   # Bu yerga OneID parolingizni yozing

async def run_bot():
    async with async_playwright() as p:
        print("💡 [1/5] Bulutli brauzer ochilmoqda...")
        browser = await p.chromium.launch(
            headless=True, 
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()
        
        # Maksimal kutish vaqtini 2 soatga (7200000 ms) uzaytirdik
        page.set_default_timeout(7200000)
        page.set_default_navigation_timeout(7200000)
        
        print("💡 [2/5] EduOn Login sahifasiga ulanilmoqda...")
        try:
            await page.goto(LOGIN_URL, wait_until="commit")
            await page.wait_for_load_state("domcontentloaded")
        except Exception as e:
            print(f"⚠️ Ulanish sekin: {e}")
        
        print("💡 [3/5] OneID identifikatsiyasi orqali kirish boshlandi...")
        try:
            await page.wait_for_selector("input[type='text']", timeout=15000)
            await page.fill("input[type='text'], input[placeholder*='login']", ONEID_LOGIN)
            await page.fill("input[type='password']", ONEID_PASSWORD)
            await page.click("button[type='submit'], text=Kirish")
            await asyncio.sleep(8) 
            print("✔️ Login bajarildi.")
        except Exception as e:
            print(f"❌ Login xatoligi: {e}")
        
        print("💡 [4/5] Jonli darslar platformasiga o'tilmoqda...")
        try:
            await page.goto(DARSLAR_URL, wait_until="commit")
            await page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"❌ Dars sahifasi ochilmadi: {e}")
        
        print("💡 [5/5] Faol dars ('Kirish' tugmasi) tekshirilmoqda...")
        try:
            dars_linki = page.locator("text=Kirish").first
            
            if await dars_linki.is_visible():
                await dars_linki.click()
                print("=======================================================")
                print("🎉 MUVAFFAQIYATLI: Dars xonasiga muvaffaqiyatli kirildi!")
                print("=======================================================")
                
                # 1-TEKSHIRUV: Roppa-rosa 40 daqiqa (2400 soniya) kutish
                print("⏳ 1-bosqich: Bot darsda. Keyingi tekshiruv 40 daqiqadan so'ng...")
                await asyncio.sleep(2400)
                print("-> [40-daqiqa]: Darsning yarmi o'tdi. Bot faol holatda davom etmoqda.")
                
                # 2-TEKSHIRUV: Keyingi 40 daqiqa + 30 soniya (2430 soniya) kutish
                print("⏳ 2-bosqich: Dars yakunigacha oxirgi faza. 40 daqiqa va 30 soniya kutilmoqda...")
                await asyncio.sleep(2430)
                print("-> [80 daqiqa 30 soniya]: Dars vaqti rasman tugadi.")
                
                # Oxirgi marta sahifa holatini tekshirish
                page_content = await page.content()
                if "yakunlandi" in page_content.lower() or "tugadi" in page_content.lower() or "yopildi" in page_content.lower():
                    print("🛑 Tizim: Dars to'liq yopilganligi tasdiqlandi.")
                else:
                    print("⚠️ Dars o'qituvchi tomonidan hali yopilmagan bo'lsa ham, vaqt limiti (80.5 daqiqa) tugagani uchun bot sessiyani yakunlaydi.")
            else:
                print("📢 Eslatma: Hozir class vaqti emasligi sababli yashil kirish tugmasi yo'q.")
        except Exception as e:
            print(f"❌ Xatolik yuz berdi: {e}")
            
        await context.close()
        await browser.close()
        print("🚀 Protsess to'liq yakunlandi. GitHub serveri xavfsiz o'chmoqda.")

if __name__ == "__main__":
    asyncio.run(run_bot())
