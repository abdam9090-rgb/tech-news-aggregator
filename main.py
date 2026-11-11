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
TARGET_CATEGORY = (os.getenv("TARGET_CATEGORY") or "").strip().lower() or "all"

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

def generate_seo_article(title, summary, link, source_name, category):
    if category == "tech":
        prompt_style = """
نوع المقال المطلوب: [تقرير إخباري وتقني حصري]
المتطلبات:
1. صياغة عنوان إخباري شيق يتناول الحدث أو التحديث التقني (بدون أسلوب ترويجي أو تجاري).
2. ملخص إخباري سريع في السطر الأول بعد العنوان.
3. تفاصيل الخبر وما أعلنته الشركة أو كشف عنه التقرير.
4. التأثير التقني لهذا التطور وأهميته للمستخدمين وصناع القرار.
5. فقرة ختامية توثق المصدر التقني الرسمي.
تنبيه: تجنب تماماً أسلوب العروض أو الشراء أو التخفيضات.
"""
    elif category == "software":
        prompt_style = """
نوع المقال المطلوب: [مراجعة أداة / برنامج كمبيوتر وتطبيق]
المتطلبات:
1. عنوان احترافي يوضح اسم البرنامج ووظيفته الأساسية وما يميزه.
2. ملخص عن مهام الأداة في السطر الأول.
3. أبرز ما تقدمه الأداة، المميزات الجديدة في هذا الإصدار، ولماذا قد يحتاجها المستخدم.
4. الأنظمة المدعومة (ويندوز، لينكس، أندرويد...) وطبيعة الرخصة (مجاني، مفتوح المصدر...).
5. خاتمة تتضمن رابط التنزيل أو المصدر الرسمي.
"""
    else:
        prompt_style = """
نوع المقال المطلوب: [عرض وتخفيضات برمجية مجانية]
المتطلبات:
1. عنوان جذاب يوضح العرض والخصم أو الترخيص المجاني المتاح.
2. ملخص يوضح القيمة الموفرة.
3. مميزات البرنامج وكيفية الاستفادة من العرض خطوة بخطوة.
4. مدة الصلاحية أو متطلبات الحصول عليه.
5. رابط العرض الرسمي.
"""

    prompt = f"""
بيانات المصدر:
- المصدر: {source_name}
- التصنيف: {category}
- العنوان الأصلي: {title}
- التفاصيل والملخص: {summary}
- الرابط المرجعي: {link}

{prompt_style}

معايير الجودة:
- لغة عربية صحفية سليمة ورصينة تلائم معايير Google Helpful Content.
- محتوى غني ومنسق بعناوين واضحة وفقرات منظمة.
"""

    try:
        client = Groq(api_key=AI_API_KEY)
        chosen_model = get_best_available_model(client)
        print(f"[*] النموذج المختار: {chosen_model} | التصنيف: {category}")

        response = client.chat.completions.create(
            model=chosen_model,
            messages=[
                {"role": "system", "content": "أنت محرر تقني وصحفي محترف متخصص في صياغة المقالات والأخبار الحصرية باللغة العربية."},
                {"role": "user", "content": prompt}
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

def send_to_telegram(article_text, original_link, source_name, category):
    if not TG_BOT_TOKEN or not TG_CHANNEL_ID:
        print("[!] بيانات تيليجرام غير متوفرة.")
        return False
        
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    
    badge = "⚡ <b>خبر وتقنية</b>" if category == "tech" else ("💾 <b>برامج وتطبيقات</b>" if category == "software" else "🎁 <b>عرض وتخفيض</b>")
    
    header = (
        f"{badge}\n"
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
    
    all_sources = config.get("sources", [])
    if TARGET_CATEGORY != "all":
        active_sources = [s for s in all_sources if s.get("enabled", True) and s.get("category") == TARGET_CATEGORY]
        print(f"[*] تصفية المصادر للتصنيف: [{TARGET_CATEGORY}] (عدد المصادر: {len(active_sources)})")
    else:
        active_sources = [s for s in all_sources if s.get("enabled", True)]
        print(f"[*] فحص جميع المصادر (عدد المصادر: {len(active_sources)})")

    if not active_sources:
        print("[!] لم يتم العثور على مصادر مطابقة.")
        return

    random.shuffle(active_sources)
    new_found = False

    for source in active_sources:
        rss_url = source.get("rss_url")
        source_name = source.get("name")
        source_category = source.get("category", "tech")
        print(f"[*] فحص المصدر: {source_name}")
        
        feed = fetch_feed_safely(rss_url)
        if not feed or not feed.entries:
            continue

        for entry in feed.entries[:3]:
            link = entry.get("link", "").strip()
            title = entry.get("title", "").strip()
            summary = entry.get("summary", "") or entry.get("description", "")
            
            if not link or is_duplicate(link, processed):
                continue
                
            print(f"[+] تم رصد مادة جديدة: {title}")
            print(f"[*] جاري توليد المقال بأسلوب ({source_category})...")
            article = generate_seo_article(title, summary, link, source_name, source_category)
            
            if article:
                send_to_telegram(article, link, source_name, source_category)
                mark_as_processed(link, processed)
                print(f"[+] تم الإرسال بنجاح.")
                new_found = True
                break
        if new_found:
            break

    save_json(PROCESSED_FILE, processed)
    print("[*] اكتملت الدورة بنجاح.")

if __name__ == "__main__":
    main()
