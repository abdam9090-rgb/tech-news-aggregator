import os
import json
import hashlib
import html
import requests
import feedparser

PROCESSED_FILE = "processed_deals.json"
SOURCES_FILE = "sources.json"
MAX_STORED_HASHES = 1000

AI_API_KEY = os.getenv("GROQ_API_KEY")
TG_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TG_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")

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
    if link_hash in processed_list:
        return True
    processed_list.append(link_hash)
    if len(processed_list) > MAX_STORED_HASHES:
        del processed_list[0]
    return False

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
    api_url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {
                "role": "system",
                "content": "أنت صحفي تقني محترف وخبير في تحسين محركات البحث (SEO) وكتابة المقالات الحصرية باللغة العربية."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.6,
        "max_tokens": 2048
    }
    
    try:
        res = requests.post(api_url, headers=headers, json=payload, timeout=45)
        res.raise_for_status()
        data = res.json()
        return data['choices'][0]['message']['content']
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

def main():
    if not AI_API_KEY:
        print("[!] خطأ: مفتاح GROQ_API_KEY غير موجود.")
        return

    config = load_json(SOURCES_FILE, {"sources": []})
    processed = load_json(PROCESSED_FILE, [])
    
    print("[*] بدء فحص مصادر الأخبار والعروض...")
    new_found = False

    for source in config.get("sources", []):
        if not source.get("enabled", True):
            continue
            
        rss_url = source.get("rss_url")
        source_name = source.get("name")
        print(f"[*] فحص المصدر: {source_name}")
        
        feed = feedparser.parse(rss_url)
        for entry in feed.entries[:3]:
            link = entry.get("link", "").strip()
            title = entry.get("title", "").strip()
            summary = entry.get("summary", "") or entry.get("description", "")
            
            if not link or is_duplicate(link, processed):
                continue
                
            print(f"[+] تم رصد محتوى جديد: {title}")
            print("[*] جاري توليد المقال الحصري عبر Groq (Llama 3.3 70B)...")
            article = generate_seo_article(title, summary, link, source_name)
            
            if article:
                send_to_telegram(article, link, source_name)
                print(f"[+] تم إرسال المقال إلى تيليجرام بنجاح.")
                new_found = True
                break
        if new_found:
            break

    save_json(PROCESSED_FILE, processed)
    print("[*] اكتملت الدورة الحالية بنجاح.")

if __name__ == "__main__":
    main()
