import asyncio
import json
import os
from playwright.async_api import async_playwright

DARSLAR_URL = "https://adu.uz"

async def run_bot():
    async with async_playwright() as p:
        print("1. Brauzer ishga tushmoqda...")
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        
        # Telefon seansini yuklash qismi
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
            viewport={"width": 375, "height": 812}
        )
        
        # GitHub Secrets-dan cookies ma'lumotlarini o'qib olish
        try:
            cookies_json = os.environ.get("EDUON_COOKIES")
            if cookies_json:
                cookies = json.loads(cookies_json)
                await context.add_cookies(cookies)
                print("2. Telefon seansi (cookies) muvaffaqiyatli yuklandi!")
            else:
                print("Xatolik: Cookies topilmadi. Tizimga kirib bo'lmaydi.")
                return
        except Exception as e:
            print(f"Sessiyani yuklashda xatolik: {e}")
            return

        page = await context.new_page()
        
        # To'g'ridan-to'g'ri dars sahifasiga o'tish
        print("3. Jonli darslar sahifasiga o'tilmoqda...")
        await page.goto(DARSLAR_URL, timeout=60000)
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(5000)
        
        # Yashil "Kirish" tugmasini qidirish
        print("4. Faol dars tugmasi qidirilmoqda...")
        try:
            dars_linki = page.locator("text=Kirish").first
            if await dars_linki.is_visible():
                await dars_linki.click()
                print("🎉 MUVAFFAQIYATLI: Bot brauzer seansi orqali darsga kirdi!")
                await asyncio.sleep(3600)  # 1 soat darsda qolish
            else:
                print("Eslatma: Hozircha sahifada yashil Kirish tugmasi ko'rinmadi.")
        except Exception as e:
            print(f"Tugmani bosishda xatolik: {e}")
            
        await context.close()
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_bot())
