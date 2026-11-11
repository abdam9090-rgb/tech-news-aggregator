import os
import json
import hashlib
import html
import random
import requests
import feedparser
from groq import Groq

PROCESSED_FILE = "processed_deals.json"
SOURCES_FILE = "sources.json"
MAX_STORED_HASHES = 1000

AI_API_KEY = os.getenv("GROQ_API_KEY")
TG_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TG_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

CANDIDATE_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
    "llama-3.1-8b-instant",
    "allam-2-7b"
]

def load_json(filepath, default):
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[!] خطأ في قراءة {filepath}: {e}")
            return default
    return default

def save_json(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def is_duplicate(link, processed_list):
    link_hash = hashlib.sha256(link.strip().encode('utf-8')).hexdigest()
    return link_hash in processed_list

def mark_as_processed(link, processed_list):
    link_hash = hashlib.sha256(link.strip().encode('utf-8')).hexdigest()
    processed_list.append(link_hash)
    if len(processed_list) > MAX_STORED_HASHES:
        del processed_list[0]

def get_best_available_model(client):
    try:
        available = [m.id for m in client.models.list().data]
        for candidate in CANDIDATE_MODELS:
            if candidate in available:
                return candidate
        for m_id in available:
            if not any(x in m_id for x in ["whisper", "guard", "embed", "tts"]):
                return m_id
    except Exception as e:
        print(f"[!] تعذر جلب قائمة النماذج تلقائياً: {e}")
    return "openai/gpt-oss-120b"

def generate_seo_article(title, summary, link, source_name):
    prompt = f"""
بيانات المصدر:
- المصدر: {source_name}
- العنوان الأصلي: {title}
- التفاصيل والملخص: {summary}
- الرابط المرجعي: {link}

المتطلبات الإلزامية لصياغة المقال:
1. عنوان رئيسي جذاب يتضمن اسم البرنامج أو الأداة وكلمة دلالية متوافقة مع السيو (SEO).
2. كتابة ملخص قصير (Meta Description) في السطر الأول بعد العنوان مباشرة.
3. مقدمة أصيلة تشرح ما تقدمه هذه الأداة وقيمتها للمستخدم.
4. أقسام واضحة بعناوين فرعية:
   - ما الذي تقدمه هذه الأداة / التحديث؟
   - أبرز الميزات والوظائف الجديدة.
   - طريقة الحصول على العرض أو التفعيل أو التحميل بالخطوات.
5. جدول أو نقاط مختصرة بالمتطلبات ونوع الترخيص أو الأنظمة المدعومة.
6. فقرة ختامية تتضمن رابط المصدر الرسمي بوضوح.
7. لغة عربية صحفية سليمة، بدون ترجمة ركيكة وبمحتوى فريد يراعي معايير Google Helpful Content.
"""
    try:
        client = Groq(api_key=AI_API_KEY)
        chosen_model = get_best_available_model(client)
        print(f"[*] النموذج المختار للتوليد: {chosen_model}")

        response = client.chat.completions.create(
            model=chosen_model,
            messages=[
                {
                    "role": "system",
                    "content": "أنت صحفي تقني محترف وخبير في تحسين محركات البحث (SEO) وكتابة المقالات الحصرية باللغة العربية."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.6,
            max_tokens=2048
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"[!] خطأ أثناء استدعاء الذكاء الاصطناعي (Groq): {e}")
        return None

def split_text_smartly(text, max_len=3500):
    lines = text.split("\n")
    chunks = []
    current_chunk = ""
    for line in lines:
        if len(current_chunk) + len(line) + 1 > max_len:
            chunks.append(current_chunk)
            current_chunk = line + "\n"
        else:
            current_chunk += line + "\n"
    if current_chunk.strip():
        chunks.append(current_chunk)
    return chunks

def send_to_telegram(article_text, original_link, source_name):
    if not TG_BOT_TOKEN or not TG_CHANNEL_ID:
        print("[!] بيانات تيليجرام غير متوفرة.")
        return False
        
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    header = (
        f"📝 <b>مسودة مقال تقني جديد للمراجعة</b>\n"
        f"🌐 <b>المصدر:</b> {html.escape(source_name)}\n"
        f"🔗 <b>الرابط الأصلي:</b> <a href=\"{html.escape(original_link)}\">انقر هنا</a>\n"
        f"────────────────────\n\n"
    )
    
    full_message = header + html.escape(article_text)
    chunks = split_text_smartly(full_message, max_len=3500)
    
    for chunk in chunks:
        payload = {
            "chat_id": TG_CHANNEL_ID,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        res = requests.post(url, json=payload, timeout=20)
        if res.status_code != 200:
            payload.pop("parse_mode", None)
            requests.post(url, json=payload, timeout=20)
    return True

def fetch_feed_safely(url):
    try:
        headers = {"User-Agent": USER_AGENT}
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            return feedparser.parse(resp.content)
    except Exception as e:
        print(f"[!] تعذر جلب الرابط {url}: {e}")
    return None

def main():
    if not AI_API_KEY:
        print("[!] خطأ: مفتاح GROQ_API_KEY غير موجود.")
        return

    config = load_json(SOURCES_FILE, {"sources": []})
    processed = load_json(PROCESSED_FILE, [])
    
    active_sources = [s for s in config.get("sources", []) if s.get("enabled", True)]
    # خلط ترتيب المصادر عشوائياً في كل تشغيل لضمان تنوع المقالات
    random.shuffle(active_sources)

    print(f"[*] عدد الروابط المعالجة سابقاً في الذاكرة: {len(processed)}")
    print("[*] بدء فحص مصادر الأخبار والعروض (بترتيب عشوائي)...")
    new_found = False

    for source in active_sources:
        rss_url = source.get("rss_url")
        source_name = source.get("name")
        print(f"[*] فحص المصدر: {source_name}")
        
        feed = fetch_feed_safely(rss_url)
        if not feed or not feed.entries:
            print(f"[!] تم تخطي {source_name} لعدم توفر خلاصات حالياً.")
            continue

        for entry in feed.entries[:3]:
            link = entry.get("link", "").strip()
            title = entry.get("title", "").strip()
            summary = entry.get("summary", "") or entry.get("description", "")
            
            if not link:
                continue
                
            if is_duplicate(link, processed):
                continue
                
            print(f"[+] تم رصد محتوى جديد: {title}")
            print(f"[*] جاري توليد المقال الحصري من ({source_name})...")
            article = generate_seo_article(title, summary, link, source_name)
            
            if article:
                send_to_telegram(article, link, source_name)
                mark_as_processed(link, processed)
                print(f"[+] تم إرسال المقال إلى تيليجرام بنجاح وحفظ الرابط.")
                new_found = True
                break
            else:
                print(f"[!] فشل توليد المقال عبر Groq، لن يتم حفظ الرابط لإعادة المحاولة.")
        if new_found:
            break

    save_json(PROCESSED_FILE, processed)
    print("[*] اكتملت الدورة الحالية بنجاح.")

if __name__ == "__main__":
    main()
