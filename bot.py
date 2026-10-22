import asyncio
from playwright.async_api import async_playwright

# 1-QADAMDA BRAUZERDAN NUSXALAB OLGAN HAVOLANGIZNI SHU YERGA QO'YING:
DARSLAR_URL = "https://eduon.adu.uz/dashboard/student/live"

async def run_bot():
    async with async_playwright() as p:
        print("1. Bulutli brauzer ishga tushmoqda...")
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
            viewport={"width": 375, "height": 812}
        )
        page = await context.new_page()
        
        print("2. Dars sahifasiga to'g'ridan-to'g'ri kirilmoqda...")
        await page.goto(DARSLAR_URL, timeout=60000)
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(5000)
        
        # Yashil "▶ Kirish" tugmasini qidirish va bosish
        print("3. Aktiv dars tugmasi qidirilmoqda...")
        try:
            # Sahifadagi yashil "Kirish" tugmasini matni orqali topadi
            dars_linki = page.locator("text=Kirish").first
            
            if await dars_linki.is_visible():
                await dars_linki.click()
                print("🎉 ZO'R! Bot muvaffaqiyatli dars xonasiga kirdi!")
                
                # Darsda 1 soat (3600 soniya) davomida faol bo'lib turish
                print("Bot dars jarayonini ushlab turibdi...")
                await asyncio.sleep(3600)
            else:
                print("Eslatma: Hozircha sahifada yashil 'Kirish' tugmasi ko'rinmadi (balki dars vaqti emasdir).")
        except Exception as e:
            print(f"Xatolik yuz berdi: {e}")
            
        await context.close()
        await browser.close()
        print("4. Bot ishlashni tugatdi.")

if __name__ == "__main__":
    asyncio.run(run_bot())
