import asyncio
import os
import json
from playwright.async_api import async_playwright

DARSLAR_URL = "https://eduon.adu.uz/dashboard/student/live
STATE_FILE = "auth_state.json"  # Butun brauzer tizimi saqlanadigan fayl

async def run_bot():
    async with async_playwright() as p:
        print("1. Bulutli brauzer ishga tushmoqda...")
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        
        # Agar avval saqlangan tizim holati mavjud bo'lsa, OneID so'ramaydi
        if os.path.exists(STATE_FILE) and os.path.getsize(STATE_FILE) > 0:
            print("🔒 Saqlangan OneID holati topildi! Tizimga to'g'ridan-to'g'ri kirilmoqda...")
            context = await browser.new_context(storage_state=STATE_FILE)
        else:
            print("⚠️ Diqqat: Tizim holati fayli topilmadi yoki bo'sh!")
            print("Iltimos, qo'lda olingan seansni ta'minlang.")
            await browser.close()
            return

        page = await context.new_page()
        
        # To'g'ridan-to'g'ri dars xonasi sahifasiga borish
        print("2. Dars sahifasiga o'tilmoqda...")
        await page.goto(DARSLAR_URL, timeout=60000)
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(5000)
        
        # Agar tizim baribir login sahifasiga haydab yuborsa (sessiya eskirgan bo'lsa)
        if "login" in page.url:
            print("❌ Xatolik: Seans muddati tugagan! OneID qayta kirishni talab qilmoqda.")
            await browser.close()
            return

        # Yashil "Kirish" tugmasini bosish
        print("3. Aktiv dars tugmasi qidirilmoqda...")
        try:
            dars_linki = page.locator("text=Kirish").first
            if await dars_linki.is_visible():
                await dars_linki.click()
                print("🎉 MUVAFFAQIYATLI: Bot dars xonasiga muvaffaqiyatli kirdi!")
                await asyncio.sleep(3600)  # 1 soat dars seansini ushlab turish
            else:
                print("Eslatma: Hozircha sahifada aktiv dars tugmasi ko'rinmadi (dars vaqti emas).")
        except Exception as e:
            print(f"Xatolik: {e}")
            
        await context.close()
        await browser.close()
        print("4. Bot ishlashni muvaffaqiyatli yakunladi.")

if __name__ == "__main__":
    asyncio.run(run_bot())
