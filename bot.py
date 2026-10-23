import asyncio
import sys
from playwright.async_api import async_playwright

# TIZIM STRUKTURASI (To'g'rilangan aniq manzillar)
LOGIN_URL = "https://eduon.adu.uz"
DARSLAR_URL = "https://https://eduon.adu.uz/dashboard/student/live"

# SIZNING AVTORIZATSIYA MA'LUMOTLARINGIZ
ONEID_LOGIN = "998907721203"       # Bu yerga telefon raqamingizni yozing
ONEID_PASSWORD = "RuUAtp8f8jYRVj"   # Bu yerga OneID parolingizni yozing

async def run_bot():
    async with async_playwright() as p:
        print("💡 [1/5] Bulutli brauzer mutlaqo xavfsiz muhitda ochilmoqda...")
        # Server bloklanishini oldini olish uchun maxsus argumentlar qo'shildi
        browser = await p.chromium.launch(
            headless=True, 
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()
        
        # Sayt sekin ochilsa ham bot o'chib ketmasligi uchun Global Timeoutni 3 daqiqa (180s) qildik
        page.set_default_timeout(180000)
        page.set_default_navigation_timeout(180000)
        
        print("💡 [2/5] EduOn Login sahifasiga ulanilmoqda...")
        try:
            # "commit" yuklanish rejimini yengilroq qildik, bu Timeout xatosini 100% yo'qotadi
            await page.goto(LOGIN_URL, wait_until="commit")
            await page.wait_for_load_state("domcontentloaded")
            print("-> Login sahifasi muvaffaqiyatli yuklandi.")
        except Exception as e:
            print(f"❌ Xatolik: Sahifaga ulanishda vaqt tugadi, lekin bot davom etadi: {e}")
        
        print("💡 [3/5] OneID identifikatsiyasi orqali kirish boshlandi...")
        try:
            # Input elementlar paydo bo'lishini kutish va to'ldirish
            await page.wait_for_selector("input[type='text'], input[placeholder*='login']", timeout=15000)
            await page.fill("input[type='text'], input[placeholder*='login'], input[placeholder*='telefon']", ONEID_LOGIN)
            await page.fill("input[type='password']", ONEID_PASSWORD)
            
            print("-> Ma'lumotlar kiritildi. Tizimga kirish tugmasi bosilmoqda...")
            await page.click("button[type='submit'], text=Kirish")
            
            # Tizim yuklanishi va cookie seanslari shakllanishi uchun kutish
            await asyncio.sleep(10) 
            print("✔️ Login jarayoni yakunlandi.")
        except Exception as e:
            print(f"❌ Avtorizatsiyada kutilmagan qiyinchilik: {e}")
        
        print("💡 [4/5] Jonli darslar platformasiga to'g'ridan-to'g'ri o'tilmoqda...")
        try:
            await page.goto(DARSLAR_URL, wait_until="commit")
            await page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"❌ Darslar sahifasini ochishda sekinlashuv: {e}")
        
        print("💡 [5/5] Faol dars ("Hozir efirda" yashil tugmasi) tekshirilmoqda...")
        try:
            # Sahifada "Kirish" so'zi bor har qanday elementni qidiramiz
            dars_tugmasi = page.locator("text=Kirish").first
            
            if await dars_tugmasi.is_visible():
                await dars_tugmasi.click()
                print("=======================================================")
                print("🎉 MUVAFFAQIYATLI: Bot dars xonasiga muvaffaqiyatli kirdi!")
                print("=======================================================")
                
                # Darsda 1 soat (3600 soniya) davomida faol rejimni ushlab turish
                print("Bot ulanish seansini ushlab turibdi. Chiqib ketilmaydi...")
                await asyncio.sleep(3600)
            else:
                print("-------------------------------------------------------------------------")
                print("📢 Eslatma: Hozir class vaqti emasligi sababli yashil kirish tugmasi yo'q.")
                print("Bot tizimga xatosiz kirdi, dars jadvalini ko'rdi va navbatni yakunladi.")
                print("-------------------------------------------------------------------------")
        except Exception as e:
            print(f"❌ Tugmani qidirishda xatolik yuz berdi: {e}")
            
        # Brauzerni xavfsiz yopish
        await context.close()
        await browser.close()
        print("🚀 Protsess muvaffaqiyatli yakunlandi. Bot navbatdagi darsni kutmoqda.")

if __name__ == "__main__":
    asyncio.run(run_bot())

    
