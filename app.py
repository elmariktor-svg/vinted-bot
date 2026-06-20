import json, os, re, threading, time
from datetime import datetime, timezone, timedelta
from flask import Flask
import requests as req_lib
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Deutsche Zeit (UTC+2 im Sommer)
DE = timezone(timedelta(hours=2))
def jetzt():
    return datetime.now(DE).strftime("%H:%M:%S")

CONFIG = {
    "domain": "www.vinted.de",
    "price_max": 7,
    "max_age_seconds": 4 * 3600,
    "brands": [
        {
            "search": "Tommy Hilfiger",
            "name": "Tommy Hilfiger",
            "require_one_of": ["polo", "poloshirt", "short", "shorts"],
            "exclude": ["hose", "hosen", "jogger", "unterwäsche", "unterhose",
                        "unterhemd", "boxer", "socken", "jeans", "jacke",
                        "mantel", "hoodie", "pullover", "check24"],
        },
        {
            "search": "Ralph Lauren",
            "name": "Ralph Lauren",
            "require_one_of": ["polo", "poloshirt", "short", "shorts"],
            "exclude": ["hose", "hosen", "jogger", "unterwäsche", "unterhose",
                        "unterhemd", "boxer", "socken", "jeans", "jacke",
                        "mantel", "hoodie", "pullover", "check24"],
        },
        {
            "search": "Lacoste",
            "name": "Lacoste",
            "require_one_of": ["polo", "poloshirt", "short", "shorts"],
            "exclude": ["hose", "hosen", "jogger", "unterwäsche", "unterhose",
                        "unterhemd", "boxer", "socken", "jeans", "jacke",
                        "mantel", "check24"],
        },
        {
            "search": "Nike Polo",
            "name": "Nike Polo",
            "require_one_of": ["polo", "poloshirt"],
            "exclude": ["hose", "hosen", "unterwäsche", "unterhose", "socken",
                        "shorts", "short", "jacke", "check24"],
        },
        {
            "search": "Nike Trikot",
            "name": "Nike Fussball",
            "require_one_of": ["trikot", "fußball", "fussball", "football", "soccer"],
            "exclude": ["hose", "hosen", "unterwäsche", "unterhose", "socken", "check24"],
        },
        {
            "search": "Adidas Trikot",
            "name": "Adidas Fussball",
            "require_one_of": ["trikot", "fußball", "fussball", "football", "soccer"],
            "exclude": ["hose", "hosen", "unterwäsche", "unterhose", "socken", "check24"],
        },
        {
            "search": "Adidas Polo",
            "name": "Adidas Polo",
            "require_one_of": ["polo", "poloshirt"],
            "exclude": ["hose", "hosen", "unterwäsche", "unterhose", "socken",
                        "shorts", "short", "jacke", "check24"],
        },
        {
            "search": "Puma Trikot",
            "name": "Puma Fussball",
            "require_one_of": ["trikot", "fußball", "fussball", "football", "soccer"],
            "exclude": ["hose", "hosen", "unterwäsche", "unterhose", "socken", "check24"],
        },
        {
            "search": "Levis Shorts",
            "name": "Levis",
            "require_one_of": ["short", "shorts"],
            "exclude": ["hose", "hosen", "jeans hose", "unterwäsche", "unterhose", "check24"],
        },
    ],
    "global_exclude": [
        "schuhe", "sneaker", "boots", "stiefel", "sandalen", "turnschuhe",
        "pumps", "schuh", "shoe", "shoes", "slipper", "ballerina",
        "clogs", "crocs", "jordan", "yeezy", "vans", "converse",
        "hausschuhe", "flip flop", "sandale",
        "mütze", "beanie", "hut", "kappe", "snapback",
        "gürtel", "tasche", "bag", "rucksack", "parfum", "uhr",
        "schmuck", "brille", "handschuhe", "schal", "armband", "kette", "ring",
        "unterwäsche", "unterhose", "unterhosen", "unterhemd",
        "boxer", "boxershorts", "slip", "bh", "tanga", "tangas", "string",
        "socken", "strümpfe", "kleid", "kleider", "rock", "bluse", "leggings",
        "bikini", "badeanzug", "baby", "kinder", "mädchen", "kids",
        "pyjama", "schlafanzug", "kostüm", "krawatte", "check24",
    ],
    "defect_negations": [
        "keine fleck", "kein fleck", "ohne fleck",
        "keine mängel", "kein mangel", "ohne mängel",
        "keine beschädigung", "kein schaden", "ohne schaden",
        "makellos", "einwandfrei", "neuwertig", "tadellos",
        "keine kratzer", "keine löcher", "keine risse",
    ],
    "defect_keywords": [
        "fleck", "flecken", "blutfleck", "ölfleck",
        "riss", "risse", "einriss", "gerissen",
        "loch", "löcher", "beschädigt", "beschädigung",
        "defekt", "kaputt", "kratzer", "abgenutzt",
        "ausgeblichen", "verblasst", "makel", "gebrauchsspuren",
        "pilling", "fussel", "stain", "hole", "damaged", "worn",
        "verfärbt", "verfärbung", "schaden", "mangel", "mängel",
        "dreckig", "schmutzig", "abgerissen", "verwaschen",
        "ausgewaschen", "knopf fehlt", "knopf ab",
    ],
    "shipping_min": 3.0,
    "shipping_max": 5.0,
    "poll_interval": 20,
    "seen_ids_file": "seen_ids.json",
}

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "")
seen_ids = set()
total_found = 0
bot_status = "Startet..."
bot_log = []

def log(msg):
    global bot_log
    line = f"[{jetzt()}] {msg}"
    print(line, flush=True)
    bot_log.append(line)
    if len(bot_log) > 100:
        bot_log = bot_log[-100:]

def load_seen_ids():
    global seen_ids
    if os.path.exists(CONFIG["seen_ids_file"]):
        try:
            with open(CONFIG["seen_ids_file"]) as f:
                seen_ids = set(json.load(f))
            log(f"{len(seen_ids)} bekannte Artikel geladen.")
        except:
            seen_ids = set()
    else:
        log("Starte frisch.")

def save_seen_ids():
    try:
        with open(CONFIG["seen_ids_file"], "w") as f:
            json.dump(list(seen_ids), f)
    except:
        pass

def get_price(raw):
    if raw is None:
        return 0.0
    if isinstance(raw, dict):
        v = raw.get("amount") or raw.get("cents") or 0
        try:
            v = float(v)
            if v > 100:
                v = v / 100
            return round(v, 2)
        except:
            return 0.0
    try:
        return round(float(raw), 2)
    except:
        return 0.0

def calc_service_fee(price):
    return round(price * 0.05 + 0.70, 2)

def is_valid_title(title, brand_config):
    t = title.lower()
    if any(w in t for w in CONFIG["global_exclude"]):
        return False
    if any(w in t for w in brand_config.get("exclude", [])):
        return False
    required = brand_config.get("require_one_of", [])
    if required and not any(w in t for w in required):
        return False
    return True

def is_valid_size(size_title):
    if not size_title or size_title.strip() in ["", "?", "-"]:
        return False
    s = size_title.upper().strip()
    if re.search(r'\bXL\b', s):
        return True
    if re.search(r'\bL\b', s) and not re.search(r'\bXXL\b|\bXS\b', s):
        return True
    return False

def is_fresh(item):
    ts = item.get("created_at_ts") or item.get("created_at") or 0
    if not ts:
        return True
    return (time.time() - float(ts)) < CONFIG["max_age_seconds"]

def check_defects(title, desc):
    text = (title + " " + desc).lower()
    for neg in CONFIG["defect_negations"]:
        text = text.replace(neg, "")
    return any(w in text for w in CONFIG["defect_keywords"])

CONDITION_MAP = {
    "neu mit etikett": "🟢 Neu mit Etikett",
    "neu, mit etikett": "🟢 Neu mit Etikett",
    "new with tags": "🟢 Neu mit Etikett",
    "brand new": "🟢 Neu mit Etikett",
    "neu ohne etikett": "🟡 Neu ohne Etikett",
    "neu, ohne etikett": "🟡 Neu ohne Etikett",
    "new without tags": "🟡 Neu ohne Etikett",
    "wie neu": "🔵 Wie neu",
    "like new": "🔵 Wie neu",
    "sehr gut": "🔵 Sehr gut",
    "sehr guter zustand": "🔵 Sehr gut",
    "very good": "🔵 Sehr gut",
    "gut": "🟠 Gut",
    "guter zustand": "🟠 Gut",
    "good": "🟠 Gut",
}
CONDITION_ID_MAP = {
    6: "🟢 Neu mit Etikett",
    1: "🟡 Neu ohne Etikett",
    2: "🔵 Sehr gut",
    3: "🟠 Gut",
}

def get_zustand(data):
    for key in ["status", "condition", "item_status", "state", "status_title", "condition_title"]:
        v = data.get(key)
        if v is None:
            continue
        if isinstance(v, dict):
            v = v.get("title") or v.get("name") or v.get("id")
        if v is None:
            continue
        s = str(v).strip().lower().replace(",", "")
        if s in CONDITION_MAP:
            return CONDITION_MAP[s]
        try:
            iv = int(v)
            if iv in CONDITION_ID_MAP:
                return CONDITION_ID_MAP[iv]
        except:
            pass
        return f"❔ {v}"
    return "❓ Unbekannt"

def start_browser():
    log("Starte Chromium...")
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.binary_location = "/usr/bin/chromium"
    service = Service("/usr/bin/chromedriver")
    driver = webdriver.Chrome(service=service, options=options)
    log("Chromium gestartet!")
    return driver

def setup(driver):
    log("Verbinde mit Vinted...")
    driver.get(f"https://{CONFIG['domain']}")
    time.sleep(4)
    try:
        WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
        ).click()
        time.sleep(2)
        log("Cookies akzeptiert!")
    except:
        log("Cookies OK.")

def fetch_items(driver, brand_config):
    search = brand_config["search"].replace(" ", "+")
    url = (f"https://{CONFIG['domain']}/api/v2/catalog/items"
           f"?search_text={search}"
           f"&price_to={CONFIG['price_max']}"
           f"&order=newest_first"
           f"&status_ids[]=6&status_ids[]=1&status_ids[]=2"
           f"&per_page=96")
    js = f"""
    var xhr = new XMLHttpRequest();
    xhr.open('GET', '{url}', false);
    xhr.setRequestHeader('Accept', 'application/json');
    xhr.send();
    return xhr.responseText;
    """
    try:
        response = driver.execute_script(js)
        if not response or response.strip() == "":
            return []
        data = json.loads(response)
        items = []
        for item in data.get("items", []):
            title = item.get("title", "")
            iid = str(item.get("id", ""))
            size_title = item.get("size_title", "") or ""
            if not iid:
                continue
            if not is_fresh(item):
                continue
            if not is_valid_title(title, brand_config):
                continue
            if not is_valid_size(size_title):
                continue
            photo = ""
            try:
                photo = item["photo"]["url"]
            except:
                pass
            price = get_price(item.get("price", 0))
            service_fee = get_price(item.get("service_fee", 0)) or calc_service_fee(price)
            total_min = round(price + service_fee + CONFIG["shipping_min"], 2)
            total_max = round(price + service_fee + CONFIG["shipping_max"], 2)
            items.append({
                "id": iid,
                "url": f"https://{CONFIG['domain']}/items/{iid}",
                "title": title,
                "brand": brand_config["name"],
                "price": price,
                "size": size_title,
                "zustand": get_zustand(item),
                "photo": photo,
                "time": jetzt(),
                "description": "",
                "service_fee": service_fee,
                "shipping_min": CONFIG["shipping_min"],
                "shipping_max": CONFIG["shipping_max"],
                "total_min": total_min,
                "total_max": total_max,
                "has_defect": False,
            })
        return items
    except Exception as e:
        if "Expecting value" not in str(e):
            log(f"Fehler ({brand_config['name']}): {e}")
        return []

def enrich_item(driver, item):
    js = f"""
    var xhr = new XMLHttpRequest();
    xhr.open('GET', 'https://{CONFIG["domain"]}/api/v2/items/{item["id"]}', false);
    xhr.setRequestHeader('Accept', 'application/json');
    xhr.send();
    return xhr.responseText;
    """
    try:
        response = driver.execute_script(js)
        if not response or response.strip() == "":
            return item
        raw = json.loads(response).get("item", {})
        desc = raw.get("description", "") or ""
        price = get_price(raw.get("price", 0)) or item["price"]
        service_fee = get_price(raw.get("service_fee", 0)) or calc_service_fee(price)
        new_zustand = get_zustand(raw)
        if not new_zustand.startswith("❓"):
            item["zustand"] = new_zustand
        item["price"] = price
        item["description"] = desc[:400]
        item["service_fee"] = service_fee
        item["size"] = raw.get("size_title", item["size"]) or item["size"]
        item["total_min"] = round(price + service_fee + CONFIG["shipping_min"], 2)
        item["total_max"] = round(price + service_fee + CONFIG["shipping_max"], 2)
        item["has_defect"] = check_defects(item["title"], desc)
        if item["has_defect"]:
            log(f"⚠️ Mängel: {item['title'][:40]}")
    except Exception as e:
        log(f"Enrich Fehler: {e}")
    return item

def send_discord(item):
    if not DISCORD_WEBHOOK:
        return
    try:
        mangel_text = "⚠️ MÄNGEL ERWÄHNT – PRÜFEN!" if item["has_defect"] else "✅ Keine Mängel"
        color = 0xff4444 if item["has_defect"] else 0x00ff88
        fields = [
            {"name": "💶 Artikelpreis", "value": f"**{item['price']}€**", "inline": True},
            {"name": "🚚 Versand", "value": f"**{item['shipping_min']} - {item['shipping_max']}€**", "inline": True},
            {"name": "🛡️ Käuferschutz", "value": f"**{item['service_fee']}€**", "inline": True},
            {"name": "💰 GESAMT", "value": f"**{item['total_min']} - {item['total_max']}€**", "inline": False},
            {"name": "📐 Größe", "value": item["size"], "inline": True},
            {"name": "✨ Zustand", "value": item["zustand"], "inline": True},
            {"name": "🏷️ Marke", "value": item["brand"], "inline": True},
            {"name": "🔍 Mängel", "value": mangel_text, "inline": False},
            {"name": "🔗 Link", "value": item["url"], "inline": False},
        ]
        if item["description"]:
            fields.append({"name": "📝 Beschreibung", "value": item["description"][:300], "inline": False})
        embed = {
            "title": f"🎯 {item['title']}",
            "url": item["url"],
            "color": color,
            "image": {"url": item["photo"]},
            "fields": fields,
            "footer": {"text": f"Vinted Snipe Bot | {item['time']} Uhr (DE)"},
        }
        r = req_lib.post(DISCORD_WEBHOOK, json={"embeds": [embed]}, timeout=10)
        log(f"✅ Discord: {item['title'][:35]} ({r.status_code})")
    except Exception as e:
        log(f"Discord Fehler: {e}")

def bot_loop():
    global total_found, bot_status
    load_seen_ids()
    driver = None
    while True:
        try:
            if driver is None:
                driver = start_browser()
                setup(driver)
            for brand_config in CONFIG["brands"]:
                items = fetch_items(driver, brand_config)
                neu = 0
                for item in items:
                    if item["id"] not in seen_ids:
                        seen_ids.add(item["id"])
                        item = enrich_item(driver, item)
                        send_discord(item)
                        total_found += 1
                        neu += 1
                        log(f"🎯 NEU [{item['brand']}] {item['title'][:35]} | {item['total_min']}-{item['total_max']}€ | {item['zustand']}")
                log(f"[{brand_config['name']}] {len(items)} Artikel, {neu} NEU")
                time.sleep(2)
            save_seen_ids()
            bot_status = f"✅ Läuft | Treffer: {total_found} | {jetzt()} Uhr (DE)"
            time.sleep(CONFIG["poll_interval"])
        except Exception as e:
            bot_status = f"❌ Fehler: {e}"
            log(f"FEHLER: {e}")
            try:
                if driver:
                    driver.quit()
            except:
                pass
            driver = None
            log("Neustart in 15 Sekunden...")
            time.sleep(15)

app = Flask(__name__)

@app.route("/")
def home():
    logs_html = "<br>".join(reversed(bot_log[-50:]))
    return f"""<html><body style="background:#0d1117;color:white;font-family:Arial;padding:20px">
    <h2>🎯 Vinted Snipe Bot</h2>
    <p><b>Status:</b> {bot_status}</p>
    <p><b>Treffer gesamt:</b> {total_found}</p>
    <hr style="border-color:#333;margin:15px 0">
    <p><b>Live Log (Deutsche Zeit):</b></p>
    <p style="font-size:12px;color:#aaa;line-height:2">{logs_html}</p>
    </body></html>"""

threading.Thread(target=bot_loop, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
