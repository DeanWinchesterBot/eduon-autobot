import asyncio
from playwright.async_api import async_playwright

# LOGIN VA DARSLAR LINKI
LOGIN_URL = "https://eduon.adu.uz/dashboard/student"
DARSLAR_URL = "https://eduon.adu.uz/dashboard/student/live"

# SIZNING JIDDIY MA'LUMOTLARINGIZ
ONEID_LOGIN = "998907721203"  # OneID dagi telefon raqamingiz
ONEID_PASSWORD = "RuUAtp8f8jYRVj"
# O'rnatgan parolingiz

async def run_bot():
    async with async_playwright() as p:
        print("1. Bulutli brauzer ochilmoqda...")
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await context.new_page()
        
        print("2. EduOn login sahifasiga kirilmoqda...")
        await page.goto(LOGIN_URL, timeout=60000)
        await page.wait_for_load_state("networkidle")
        
        # OneID orqali avtomatik login qilish qismi
        print("3. OneID orqali avtomat kirish boshlandi...")
        try:
            # Telefon raqami va parolni kiritish
            await page.fill("input[type='text'], input[placeholder*='login'], input[placeholder*='telefon']", ONEID_LOGIN)
            await page.fill("input[type='password']", ONEID_PASSWORD)
            
            # Kirish (Submit) tugmasini bosish
            await page.click("button[type='submit'], text=Kirish")
            await page.wait_for_timeout(7000)  # Tizim profilga o'tishini kutamiz
            print("Login muvaffaqiyatli bajarildi!")
        except Exception as e:
            print(f"Login jarayonida xatolik: {e}")
        
        # Jonli darslar bo'limiga to'g'ridan-to'g'ri o'tish
        print("4. Jonli darslar sahifasiga o'tilmoqda...")
        await page.goto(DARSLAR_URL, timeout=60000)
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(4000)
        
        # "Kirish" tugmasini bosish
        print("5. Yashil 'Kirish' tugmasi qidirilmoqda...")
        try:
            dars_linki = page.locator("text=Kirish").first
            if await dars_linki.is_visible():
                await dars_linki.click()
                print("🎉 MUVAFFAQIYATLI: Bot dars xonasiga muvaffaqiyatli kirdi!")
                await asyncio.sleep(3600)  # 1 soat darsda faol o'tirish
            else:
                print("Eslatma: Hozircha sahifada yashil 'Kirish' tugmasi ko'rinmadi (dars vaqti emas).")
        except Exception as e:
            print(f"Xatolik: {e}")
            
        await context.close()
        await browser.close()
        print("6. Bot ishni tugatdi.")

if __name__ == "__main__":
    asyncio.run(run_bot())
