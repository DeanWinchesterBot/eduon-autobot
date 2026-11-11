import asyncio
import base64
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

from playwright.async_api import async_playwright

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DARSLAR_URL = "https://eduon.adu.uz/dashboard/student/live"
LOGIN_URL = "https://eduon.adu.uz/login"
COOKIES_FILE = "cookies.json"

ONEID_LOGIN = os.getenv("ONEID_LOGIN")
ONEID_PASSWORD = os.getenv("ONEID_PASSWORD")
EDUON_COOKIES = os.getenv("EDUON_COOKIES")  # Cookie-Editor JSON (GitHub Secret)
EDUON_LOCALSTORAGE = os.getenv("EDUON_LOCALSTORAGE")  # Safari'dan olingan localStorage JSON (GitHub Secret)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")  # ixtiyoriy: darsga kirganda rasm yuborish
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
MODE = os.getenv("MODE") or "lesson"  # lesson = darsga kirish, schedule = jadvalni o'qish
SCHEDULE_URL = "https://eduon.adu.uz/dashboard/student/schedule"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  # ixtiyoriy: dars konspekti uchun
GEMINI_MODEL = os.getenv("GEMINI_MODEL") or "gemini-2.5-flash"
AUDIO_FILE = "lesson_audio.webm"
MP3_FILE = "lesson_audio.mp3"
SESSION_URL = os.getenv("SESSION_URL")  # Cloudflare Worker manzili (Telegram orqali yangilanadigan sessiya)
SESSION_KEY = os.getenv("SESSION_KEY")
WAIT_MINUTES = int(os.getenv("WAIT_MINUTES", "0"))  # 0 = kutmaydi, topilmasa darrov tugaydi

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _parse_expires(v):
    """Turli ilovalar: soniya, millisoniya yoki ISO matn. Playwright uchun soniya (float) qaytaradi."""
    if v in (None, "", 0):
        return None
    try:
        x = float(v)
        return x / 1000 if x > 1e12 else x
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def load_seed_cookies(raw):
    """Cookie-Editor / boshqa ilovalar JSON'ini yoki 'nom=qiymat; nom2=qiymat2' qatorini Playwright formatiga o'giradi."""
    raw = (raw or "").strip()
    try:
        data = json.loads(raw)
    except Exception:
        # JSON emas: "auth_session=...; auth_token=..." ko'rinishidagi qator
        out = []
        for pair in raw.replace("\n", ";").split(";"):
            if "=" not in pair:
                continue
            name, val = pair.strip().split("=", 1)
            if name.strip():
                out.append({"name": name.strip(), "value": val.strip(), "domain": "eduon.adu.uz", "path": "/",
                            "secure": True, "httpOnly": True, "sameSite": "Lax"})
        if not out:
            print("⚠️ EDUON_COOKIES na JSON, na 'nom=qiymat' qatori emas.")
        return out

    if isinstance(data, dict):
        data = data.get("cookies") if isinstance(data.get("cookies"), list) else [data]

    same_site_map = {"no_restriction": "None", "none": "None", "lax": "Lax", "strict": "Strict"}
    result = []
    for c in data:
        try:
            item = {
                "name": c["name"],
                "value": c["value"],
                "domain": c.get("domain") or "eduon.adu.uz",
                "path": c.get("path", "/") or "/",
                "secure": bool(c.get("secure", True)),
                "httpOnly": bool(c.get("httpOnly", c.get("http_only", False))),
                "sameSite": same_site_map.get(str(c.get("sameSite", "")).lower(), "Lax"),
            }
            exp = _parse_expires(c.get("expirationDate") or c.get("expires") or c.get("expiry"))
            if exp and not c.get("session"):
                item["expires"] = exp
            if item["sameSite"] == "None":
                item["secure"] = True
            result.append(item)
        except Exception as e:
            print(f"⚠️ Cookie o'tkazib yuborildi: {e}")
    return result


def cookies_from_ls(raw):
    """LS bookmark nusxasidagi '__cookies' (document.cookie) qatoridan cookie ro'yxati yasaydi."""
    try:
        text = (json.loads(raw) or {}).get("__cookies") or ""
    except Exception:
        return []
    out = []
    for pair in text.split(";"):
        if "=" not in pair:
            continue
        name, val = pair.strip().split("=", 1)
        if name:
            out.append({"name": name, "value": val, "domain": "eduon.adu.uz", "path": "/",
                        "secure": True, "httpOnly": False, "sameSite": "Lax"})
    return out


def get_seed():
    """Boshlang'ich cookies: avval EDUON_COOKIES (Cookie-Editor), bo'lmasa LS nusxasidagi cookies."""
    if EDUON_COOKIES:
        return load_seed_cookies(EDUON_COOKIES)
    if EDUON_LOCALSTORAGE:
        return cookies_from_ls(EDUON_LOCALSTORAGE)
    return []


def jwt_exp(token):
    """JWT ichidagi amal qilish muddatini (soniya) qaytaradi. Imzo tekshirilmaydi."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return int(json.loads(base64.urlsafe_b64decode(payload))["exp"])
    except Exception:
        return None


def seed_token_exp():
    """Secret'lardagi tokenning amal qilish muddati (auth_token cookie yoki auth-store)."""
    try:
        for c in get_seed():
            if c["name"] == "auth_token":
                e = jwt_exp(c["value"])
                if e:
                    return e
    except Exception:
        pass
    try:
        d = json.loads(EDUON_LOCALSTORAGE or "{}")
        tok = json.loads(d.get("auth-store", "{}"))["state"]["user"]["token"]
        return jwt_exp(tok)
    except Exception:
        return None


def fmt_tashkent(ts):
    return datetime.fromtimestamp(ts, timezone(timedelta(hours=5))).strftime("%d.%m %H:%M")


async def log_token_exp(context, tag):
    """Brauzerdagi auth_token cookie muddatini logga chiqaradi (sayt tokenni o'zi yangilaydimi, shuni bilish uchun)."""
    try:
        for c in await context.cookies():
            if c["name"] == "auth_token":
                e = jwt_exp(c["value"])
                if e:
                    print(f"🔑 Token muddati ({tag}): {fmt_tashkent(e)} Toshkent")
                return
        print(f"🔑 Token cookie topilmadi ({tag}).")
    except Exception:
        pass


def is_login_url(url):
    return any(x in url for x in ("/login", "id.egov.uz", "/auth", "oauth"))


async def check_session(page):
    """Dars sahifasini 3 marta urinib ochadi.
    True = sessiya faol, False = login kerak, None = sayt umuman ochilmadi."""
    for attempt in range(1, 4):
        try:
            await page.goto(DARSLAR_URL, wait_until="domcontentloaded", timeout=60000)
            try:
                await page.wait_for_load_state("networkidle", timeout=20000)
            except Exception:
                pass
            await asyncio.sleep(3)
            return not is_login_url(page.url)
        except Exception as e:
            print(f"⚠️ Urinish {attempt}/3 muvaffaqiyatsiz: {str(e).splitlines()[0]}")
            await asyncio.sleep(10)
    return None


async def oneid_login(page, context):
    if not ONEID_LOGIN or not ONEID_PASSWORD:
        print("❌ ONEID_LOGIN yoki ONEID_PASSWORD topilmadi!")
        return False

    page.set_default_timeout(120000)
    try:
        print("🔗 Eduon login sahifasiga o'tilmoqda...")
        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)

        # OneID tugmasi topilmasa, aniq xato chiqsin (jimgina o'tkazib yubormaymiz)
        oneid_btn = page.locator(
            "a:has-text('OneID'), button:has-text('OneID'), a[href*='oneid']"
        ).first
        await oneid_btn.click(timeout=15000)

        print("👤 OneID sahifasi ochildi. Ma'lumotlar kiritilmoqda...")
        await asyncio.sleep(3)

        username_input = page.locator(
            "input[type='text'], input[type='tel'], input[name='login']"
        ).first
        await username_input.wait_for(state="visible", timeout=60000)
        await username_input.fill(ONEID_LOGIN)

        password_input = page.locator("input[type='password']").first
        await password_input.wait_for(state="visible", timeout=30000)
        await password_input.fill(ONEID_PASSWORD)

        print("🔑 'Kirish' tugmasi bosilmoqda...")
        await page.locator("button[type='submit'], button:has-text('Kirish')").first.click()

        await page.wait_for_url(lambda url: "eduon.adu.uz" in url, timeout=120000)
        await context.storage_state(path=COOKIES_FILE)
        print("🍪 Sessiya saqlandi!")
        return True
    except Exception as e:
        print(f"❌ OneID login jarayonida xatolik: {e}")
        try:
            await page.screenshot(path="oneid_xato.png", full_page=True)
        except Exception:
            pass
        return False
    finally:
        page.set_default_timeout(45000)


def tashkent_now():
    return datetime.now(timezone(timedelta(hours=5))).strftime("%H:%M")


async def send_telegram(p, text, photo_path=None):
    """Telegram'ga xabar (yoki rasm) yuboradi. Token/chat sozlanmagan bo'lsa, jim o'tadi."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    api = None
    try:
        api = await p.request.new_context()
        base = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
        if photo_path and os.path.exists(photo_path):
            with open(photo_path, "rb") as f:
                buf = f.read()
            r = await api.post(
                base + "/sendPhoto",
                multipart={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "caption": text,
                    "photo": {"name": "dars.png", "mimeType": "image/png", "buffer": buf},
                },
            )
        else:
            r = await api.post(base + "/sendMessage", form={"chat_id": TELEGRAM_CHAT_ID, "text": text})
        print(f"📨 Telegram: {'yuborildi' if r.ok else 'xato ' + str(r.status)}")
    except Exception as e:
        print(f"⚠️ Telegram yuborilmadi: {str(e).splitlines()[0]}")
    finally:
        if api:
            await api.dispose()


async def schedule_dump(p, page):
    """Jadval sahifasini ochib, skrinshot va matnini chiqaradi (tuzilmani o'rganish uchun)."""
    print("📅 Jadval sahifasi ochilmoqda...")
    await page.goto(SCHEDULE_URL, wait_until="domcontentloaded", timeout=60000)
    try:
        await page.wait_for_load_state("networkidle", timeout=20000)
    except Exception:
        pass
    await asyncio.sleep(4)
    await page.screenshot(path="jadval.png", full_page=True)
    text = (await page.inner_text("body")).replace("\n", " | ")
    print("📅 Jadval o'qildi (matn faqat Telegram'ga yuboriladi).")
    await send_telegram(p, f"📅 Jadval sahifasi (Toshkent {tashkent_now()})", "jadval.png")
    await send_telegram(p, text[:3800])


# ---------------------------------------------------------------------------
# Dars audiosini yozib olish va konspekt tayyorlash (Gemini)
# ---------------------------------------------------------------------------
audio_state = {"bytes": 0, "tracks": 0}

REC_JS = r"""
(() => {
  if (window.__lessonRecInstalled) return;
  window.__lessonRecInstalled = true;
  const Orig = window.RTCPeerConnection;
  if (!Orig) return;
  let ctx = null, dest = null, rec = null;
  const handled = new Set();
  function ensure() {
    if (rec) return;
    ctx = new (window.AudioContext || window.webkitAudioContext)();
    dest = ctx.createMediaStreamDestination();
    try { ctx.resume(); } catch (e) {}
    const opts = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? {mimeType: 'audio/webm;codecs=opus'} : {};
    rec = new MediaRecorder(dest.stream, opts);
    rec.ondataavailable = (ev) => {
      if (!ev.data || !ev.data.size) return;
      const fr = new FileReader();
      fr.onloadend = () => { try { window.__saveChunk(String(fr.result).split(',')[1]); } catch (e) {} };
      fr.readAsDataURL(ev.data);
    };
    rec.start(10000);
  }
  function onTrack(track) {
    if (!track || track.kind !== 'audio' || handled.has(track.id)) return;
    handled.add(track.id);
    try {
      ensure();
      const ms = new MediaStream([track]);
      const a = new Audio(); a.muted = true; a.srcObject = ms; a.play().catch(() => {});
      ctx.createMediaStreamSource(ms).connect(dest);
      window.__trackAdded();
    } catch (e) {}
  }
  function Patched(...args) {
    const pc = new Orig(...args);
    pc.addEventListener('track', (e) => onTrack(e.track));
    return pc;
  }
  Patched.prototype = Orig.prototype;
  Object.setPrototypeOf(Patched, Orig);
  window.RTCPeerConnection = Patched;
  if (window.webkitRTCPeerConnection) window.webkitRTCPeerConnection = Patched;
  window.__stopRec = () => { try { if (rec && rec.state !== 'inactive') rec.stop(); } catch (e) {} };
})();
"""

NOTES_PROMPT = """Sen talabaga darsni tushunishda yordam beradigan o'qituvchisan. Senga universitet jonli darsining audio yozuvi berildi (til: o'zbek, rus yoki aralash). Darsni boshidan oxirigacha diqqat bilan tingla va talaba uchun o'zbek tilida, sodda va tushunarli qilib batafsil konspekt yoz. Muhim hech narsani tashlab ketma.

Tuzilishi:
1) MAVZU: dars mavzusi va 3-5 gapli qisqa xulosa.
2) ASOSIY TUSHUNCHALAR: har bir atama yoki ta'rifni oddiy so'zlar bilan, iloji bo'lsa hayotiy misol bilan tushuntir.
3) DARS TAFSILOTI: dars qanday tartibda o'tganini bosqichma-bosqich, o'qituvchi aytgan barcha muhim fikr, misol, formula, raqam, sana va nomlar bilan yoz.
4) VAZIFA VA ESLATMALAR: o'qituvchi aytgan uy vazifasi, topshiriq, muddatlar, nazorat yoki imtihon haqidagi gaplar. Aytilmagan bo'lsa "aytilmadi" deb yoz.
5) ESDA QOLDIRISH UCHUN: 5-7 ta eng muhim fikrni qisqa ro'yxat qilib yoz va o'zini tekshirish uchun 5 ta savol ber.

Qoidalar: faqat audioda aytilgan narsalarga tayan, o'zingdan fakt to'qima. O'zing qo'shgan tushuntirish misollarini "Misol:" deb ajrat. Eshitilmagan yoki tushunarsiz joyni "(eshitilmadi)" deb belgila. Markdown belgilarini (**, #) ishlatma; oddiy matn, raqamlangan bo'limlar va ba'zi emojilar ishlat. Audioda dars bo'lmasa yoki faqat jimlik bo'lsa, shuni ayt."""


def save_chunk(b64):
    try:
        data = base64.b64decode(b64)
        with open(AUDIO_FILE, "ab") as f:
            f.write(data)
        audio_state["bytes"] += len(data)
    except Exception:
        pass


def track_added():
    audio_state["tracks"] += 1
    print(f"🎧 Audio treki ulandi (jami {audio_state['tracks']})")


async def send_long(p, text):
    """Uzun matnni Telegram uchun bo'laklarga bo'lib yuboradi."""
    parts, cur = [], ""
    for para in text.split("\n"):
        if len(cur) + len(para) + 1 > 3800:
            if cur:
                parts.append(cur)
            cur = para
        else:
            cur = (cur + "\n" + para) if cur else para
    if cur:
        parts.append(cur)
    for i, part in enumerate(parts, 1):
        head = f"📝 Konspekt ({i}/{len(parts)})\n\n" if len(parts) > 1 else "📝 Konspekt\n\n"
        await send_telegram(p, head + part)


def _pick_models(client):
    """Gemini modellar ro'yxatidan eng yangi 'flash' modellarni tanlaydi (model nomlari tez eskiradi)."""
    import re

    found = []
    try:
        for m in client.models.list():
            name = (getattr(m, "name", "") or "").replace("models/", "")
            acts = getattr(m, "supported_actions", None) or []
            if "generateContent" not in acts or "flash" not in name:
                continue
            if any(x in name for x in ("lite", "image", "tts", "live", "audio", "exp", "robotics", "thinking", "embed")):
                continue
            mt = re.search(r"gemini-(\d+(?:\.\d+)?)", name)
            found.append((float(mt.group(1)) if mt else 0.0, "preview" not in name, name))
    except Exception as e:
        print(f"⚠️ Model ro'yxatini olib bo'lmadi: {type(e).__name__}")
    found.sort(reverse=True)
    order = ([os.getenv("GEMINI_MODEL")] if os.getenv("GEMINI_MODEL") else []) + [n for _, _, n in found[:3]]
    order += ["gemini-3.5-flash", "gemini-2.5-flash"]
    seen, models = set(), []
    for n in order:
        if n and n not in seen:
            seen.add(n)
            models.append(n)
    return models


def _gemini_notes(audio_path=MP3_FILE, prompt=None):
    from google import genai

    client = genai.Client(api_key=GEMINI_API_KEY)
    f = client.files.upload(file=audio_path)
    for _ in range(40):
        state = str(getattr(f, "state", "") or "")
        if "FAILED" in state:
            raise RuntimeError("Gemini audio faylni qayta ishlay olmadi")
        if not state or "ACTIVE" in state:
            break
        time.sleep(5)
        f = client.files.get(name=f.name)
    last = None
    for model in _pick_models(client):
        try:
            resp = client.models.generate_content(model=model, contents=[f, prompt or NOTES_PROMPT])
            if resp.text:
                print(f"🤖 Gemini modeli: {model}")
                return resp.text
            last = RuntimeError(f"{model}: bo'sh javob")
        except Exception as e:
            last = e
            print(f"⚠️ Model {model}: {type(e).__name__}")
    raise last or RuntimeError("Model topilmadi")


async def make_notes(p):
    size = os.path.getsize(AUDIO_FILE) if os.path.exists(AUDIO_FILE) else 0
    print(f"🎧 Yozilgan audio: {size // 1024} KB")
    if size < 100_000:
        await send_telegram(p, "⚠️ Dars audiosi yozib olinmadi (ovoz oqimi ushlanmadi). Konspekt tayyorlanmadi.")
        return
    try:
        res = await asyncio.to_thread(
            subprocess.run,
            ["ffmpeg", "-y", "-i", AUDIO_FILE, "-ac", "1", "-ar", "16000", "-b:a", "32k", MP3_FILE],
            capture_output=True,
        )
        if res.returncode != 0 or not os.path.exists(MP3_FILE):
            raise RuntimeError("ffmpeg audioni o'zgartira olmadi")
        print(f"🎧 MP3 tayyor: {os.path.getsize(MP3_FILE) // 1024} KB. Gemini'ga yuborilmoqda...")
        text, last_err = None, ""
        for attempt in range(1, 3):
            try:
                text = await asyncio.to_thread(_gemini_notes)
                break
            except Exception as e:
                last_err = f"{type(e).__name__}: {str(e)[:250]}".replace(GEMINI_API_KEY or "x-none", "***")
                print(f"⚠️ Gemini urinish {attempt}/2 xato: {type(e).__name__}")
                await asyncio.sleep(60)
        if not text:
            await send_telegram(p, f"⚠️ Konspekt tayyorlanmadi: Gemini javob bermadi.\nSabab: {last_err}")
            return
        print("📝 Konspekt tayyor, Telegram'ga yuborilmoqda...")
        await send_long(p, text)
    except Exception as e:
        print(f"⚠️ Konspekt xatosi: {type(e).__name__}")
        await send_telegram(p, "⚠️ Konspekt tayyorlashda xato chiqdi.")


async def attend_lesson(p, page):
    """Dars davomida (80 daqiqa) xonada turadi va audio holatini kuzatadi."""
    await asyncio.sleep(180)
    if GEMINI_API_KEY:
        print(f"🎧 Audio holati: treklar={audio_state['tracks']}, yozilgan={audio_state['bytes'] // 1024} KB")
        if audio_state["bytes"] == 0:
            await send_telegram(p, "⚠️ Darsga kirildi, lekin ovoz hali ushlanmayapti. Konspekt chiqmasligi mumkin.")
    remaining = 4800 - 180
    while remaining > 0:
        step = min(600, remaining)
        await asyncio.sleep(step)
        remaining -= step
        if GEMINI_API_KEY:
            print(f"🎧 Audio holati: treklar={audio_state['tracks']}, yozilgan={audio_state['bytes'] // 1024} KB")
    if GEMINI_API_KEY:
        try:
            await page.evaluate("window.__stopRec && window.__stopRec()")
        except Exception:
            pass
        await asyncio.sleep(5)


async def whoami(page):
    """Sayt sizni kim deb bilishini tekshiradi (shaxsiy qiymatlarsiz, faqat tuzilma)."""
    try:
        res = await page.evaluate("""async () => {
            try {
                const r = await fetch('/bff/api/telegram/me', {credentials: 'include'});
                let j = null;
                try { j = await r.json(); } catch (e) {}
                const shape = {};
                if (j && typeof j === 'object') {
                    for (const k of Object.keys(j).slice(0, 15)) {
                        const v = j[k];
                        shape[k] = v === null ? 'null' : (typeof v === 'object' ? 'object' : typeof v);
                    }
                }
                return {status: r.status, shape: shape};
            } catch (e) { return {error: String(e)}; }
        }""")
        print(f"🪪 /me javobi: {res}")
        keys = await page.evaluate("() => Object.keys(localStorage)")
        print(f"🗂 localStorage kalitlari: {keys}")
    except Exception as e:
        print(f"⚠️ whoami xatosi: {e}")


async def dump_page(page):
    """Tugma topilmaganda: bot nimani ko'rayotganini logga chiqaradi."""
    try:
        print(f"🔎 Joriy manzil: {page.url}")
        print(f"🔎 Sahifa sarlavhasi: {await page.title()}")
        info = await page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('*').forEach(el => {
                const t = (el.innerText || '').trim();
                if (t.length > 0 && t.length < 40 && /kirish/i.test(t) && el.children.length < 3) {
                    const r = el.getBoundingClientRect();
                    out.push(el.tagName + ' | class=' + (el.className || '').toString().slice(0, 60)
                        + ' | text=' + t.replace(/\\s+/g, ' ')
                        + ' | ' + Math.round(r.width) + 'x' + Math.round(r.height));
                }
            });
            return out.slice(0, 15);
        }""")
        print(f"🔎 'Kirish' so'zi bor elementlar ({len(info)} ta):")
        for line in info:
            print("   -", line)
    except Exception as e:
        print(f"⚠️ Diagnostika xatosi: {e}")


async def load_remote_session(p):
    """Telegram orqali yangilangan sessiyani Worker'dan oladi (bo'lsa, GitHub Secret'lar o'rnini bosadi)."""
    global EDUON_COOKIES, EDUON_LOCALSTORAGE
    if not SESSION_URL or not SESSION_KEY:
        return
    api = None
    try:
        api = await p.request.new_context()
        r = await api.get(SESSION_URL.rstrip("/") + "/session", headers={"Authorization": f"Bearer {SESSION_KEY}"}, timeout=30000)
        if not r.ok:
            print(f"⚠️ Sessiya ombori javobi: {r.status} (GitHub Secret'lar ishlatiladi)")
            return
        data = await r.json()
        got = []
        if data.get("cookies"):
            EDUON_COOKIES = data["cookies"]
            got.append("cookies")
        if data.get("ls"):
            EDUON_LOCALSTORAGE = data["ls"]
            got.append("localStorage")
        print(f"☁️ Sessiya ombori: {', '.join(got) if got else 'bo`sh'} olindi.")
    except Exception as e:
        print(f"⚠️ Sessiya omboriga ulanib bo'lmadi: {type(e).__name__} (GitHub Secret'lar ishlatiladi)")
    finally:
        if api:
            await api.dispose()


async def run_bot():
    # Secret berilgan bo'lsa (cookies yoki localStorage), eski keshni ishlatmaymiz: kesh eskirgan sessiyani saqlab qolishi mumkin
    has_seed = bool(EDUON_COOKIES) or bool(EDUON_LOCALSTORAGE)
    print(f"🕒 Bot ishga tushdi: Toshkent vaqti {tashkent_now()}")
    async with async_playwright() as p:
        await load_remote_session(p)
        has_seed = bool(EDUON_COOKIES) or bool(EDUON_LOCALSTORAGE)
        exp = seed_token_exp()
        if exp:
            left_h = (exp - time.time()) / 3600
            print(f"🔑 Secret'dagi token muddati: {fmt_tashkent(exp)} Toshkent (qoldi {left_h:.0f} soat)")
            if 0 < left_h < 36:
                await send_telegram(p, f"⏰ Sessiya {left_h:.0f} soatdan keyin tugaydi ({fmt_tashkent(exp)}). Telegram'ga yangi cookies yuboring va LS bookmark bilan localStorage'ni yangilang, aks holda bot darsga kirolmaydi.")
        print("💡 [1/5] Brauzer ishga tushmoqda...")
        launch_args = ["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage",
                       "--autoplay-policy=no-user-gesture-required"]
        context_args = {
            "user_agent": USER_AGENT,
            "viewport": {"width": 1280, "height": 800},
            "timezone_id": "Asia/Tashkent",  # sayt dars vaqtini brauzer soatiga qarab hisoblaydi
            "locale": "uz-UZ",
        }
        if os.path.exists(COOKIES_FILE) and not has_seed:
            print("🍪 Saqlangan sessiya (kesh) yuklanmoqda...")
            context_args["storage_state"] = COOKIES_FILE
        elif has_seed:
            print("🍪 Secret'dagi sessiya ishlatiladi (kesh e'tiborga olinmaydi).")

        browser = await p.chromium.launch(headless=True, args=launch_args)
        context = await browser.new_context(**context_args)
        if EDUON_LOCALSTORAGE:
            try:
                json.loads(EDUON_LOCALSTORAGE)  # to'g'ri JSON ekanini tekshirish
                init_js = (
                    "(() => { if (location.hostname !== 'eduon.adu.uz') return;"
                    " let d = {}; try { d = JSON.parse(" + json.dumps(EDUON_LOCALSTORAGE) + "); } catch (e) {}"
                    " for (const k in d) { try { if (localStorage.getItem(k) === null)"
                    " localStorage.setItem(k, d[k]); } catch (e) {} } })();"
                )
                await context.add_init_script(init_js)
                print("🗂 Secret'dagi localStorage qo'yiladi.")
            except Exception as e:
                print(f"⚠️ EDUON_LOCALSTORAGE JSON emas: {e}")

        if GEMINI_API_KEY:
            for old_file in (AUDIO_FILE, MP3_FILE):
                if os.path.exists(old_file):
                    os.remove(old_file)
            await context.expose_function("__saveChunk", save_chunk)
            await context.expose_function("__trackAdded", track_added)
            await context.add_init_script(REC_JS)
            print("🎙 Dars audiosi yozib olinadi (konspekt uchun).")

        page = await context.new_page()
        page.set_default_timeout(45000)

        seen_urls = set()

        def log_response(resp):
            try:
                rtype = resp.request.resource_type
                path = resp.url.split("?")[0][:110]
                if rtype in ("xhr", "fetch") and (resp.status, path) not in seen_urls and len(seen_urls) < 60:
                    seen_urls.add((resp.status, path))
                    print(f"   🌐 {resp.status} {path}")
            except Exception:
                pass

        page.on("response", log_response)

        try:
            # Kesh bo'sh bo'lsa, boshidanoq Secret'dagi cookies'ni qo'yamiz
            seed_used = False
            if has_seed:
                seed = get_seed()
                if seed:
                    await context.add_cookies(seed)
                    seed_used = True
                    print("🍪 Boshlang'ich cookies (Secret) qo'yildi.")

            print("💡 [2/5] EduOn jonli darslar sahifasiga kirilmoqda...")
            logged_in = await check_session(page)

            if logged_in is None:
                print("❌ EduOn sayti 3 urinishda ham ochilmadi (tarmoq/IP muammosi).")
                await send_telegram(p, f"❌ EduOn ochilmadi (Toshkent {tashkent_now()}). Run'ni qayta ishga tushiring.")
                print("   Ishni qayta ishga tushiring (Re-run).")
                sys.exit(1)

            # Kesh eskirgan bo'lsa, Secret'dagi cookies bilan urinib ko'ramiz
            if not logged_in and has_seed and not seed_used:
                print("🍪 Kesh eskirgan, Secret'dagi cookies bilan urinilmoqda...")
                seed = get_seed()
                if seed:
                    await context.clear_cookies()
                    await context.add_cookies(seed)
                    logged_in = await check_session(page)
                    if logged_in is None:
                        print("❌ EduOn sayti ochilmadi.")
                        sys.exit(1)

            if logged_in:
                print("✔️ Sessiya faol, login talab qilinmadi.")
                await log_token_exp(context, "boshida")
                await whoami(page)
            else:
                print("⚠️ Tizim avtorizatsiya so'radi.")
                print("💡 [3/5] OneID orqali tizimga kirish boshlandi...")
                if not await oneid_login(page, context):
                    await send_telegram(p, f"❌ Login muvaffaqiyatsiz (Toshkent {tashkent_now()}). Sessiya muddati tugagan bo'lishi mumkin: Telegram'ga yangi cookies yuboring va LS bookmark bilan localStorage'ni yangilang, keyin /run yozing.")
                    await browser.close()
                    sys.exit(1)
                await page.goto(DARSLAR_URL, wait_until="domcontentloaded")
                await asyncio.sleep(3)

            await context.storage_state(path=COOKIES_FILE)

            if MODE == "schedule":
                await schedule_dump(p, page)
                return

            print("💡 [4/5] 'Jonli darslar' bo'limi tekshirilmoqda...")
            try:
                if "live" not in page.url:
                    await page.goto(DARSLAR_URL, wait_until="domcontentloaded")
                    await asyncio.sleep(3)

                # Matni aynan "Kirish" bo'lgan, ko'rinib turgan istalgan element (a, button, div...)
                kirish_btn = page.get_by_text("Kirish", exact=True).locator("visible=true").first

                print(f"🔍 'Kirish' tugmasi kutilmoqda (kutish: {WAIT_MINUTES} daqiqa)...")
                deadline = time.monotonic() + WAIT_MINUTES * 60
                found = False
                while True:
                    try:
                        # wait_for haqiqatan kutadi (is_visible esa kutmaydi)
                        await kirish_btn.wait_for(state="visible", timeout=10000)
                        found = True
                        break
                    except Exception:
                        pass
                    try:
                        await page.screenshot(path="kutish.png", full_page=True)
                    except Exception:
                        pass
                    if time.monotonic() >= deadline:
                        break
                    print("⏳ Tugma hali ko'rinmadi, 60 soniyadan keyin qayta tekshiriladi...")
                    await asyncio.sleep(60)
                    try:
                        await page.reload(wait_until="domcontentloaded", timeout=60000)
                        await asyncio.sleep(3)
                        if is_login_url(page.url):
                            print("⚠️ Kutish paytida sessiya tugadi.")
                            break
                    except Exception as e:
                        print(f"⚠️ Sahifani yangilab bo'lmadi: {str(e).splitlines()[0]}")

                if found:
                    await kirish_btn.click()
                    print("🎉 MUVAFFAQIYATLI: Jonli dars xonasiga kirildi!")
                    await asyncio.sleep(5)
                    await page.screenshot(path="darsga_kirildi.png", full_page=True)
                    await send_telegram(p, f"✅ Jonli darsga kirildi (Toshkent {tashkent_now()})", "darsga_kirildi.png")
                    await context.storage_state(path=COOKIES_FILE)

                    print("⏳ Dars boshlandi. 1 soat 20 daqiqa darsda qatnashilmoqda...")
                    await attend_lesson(p, page)
                    await log_token_exp(context, "dars oxirida")
                    await context.storage_state(path=COOKIES_FILE)
                    if GEMINI_API_KEY:
                        await make_notes(p)
                else:
                    print("📢 Faol dars topilmadi ('Kirish' tugmasi ko'rinmadi).")
                    await page.screenshot(path="dars_yoq.png", full_page=True)
                    await dump_page(page)
            except Exception as e:
                print(f"❌ Dars jarayonida xatolik: {e}")
                try:
                    await page.screenshot(path="dars_xato.png", full_page=True)
                except Exception:
                    pass
        finally:
            await context.close()
            await browser.close()

        print("🚀 [5/5] Bot o'z ishini yakunladi.")


if __name__ == "__main__":
    asyncio.run(run_bot())
