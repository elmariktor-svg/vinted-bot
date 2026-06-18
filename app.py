import json, os, re, threading, time
from datetime import datetime
from flask import Flask
import requests as req_lib
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

CONFIG = {
    "domain": "www.vinted.de",
    "price_max": 7,
    "brands": [
        "Tommy Hilfiger Polo",
        "Ralph Lauren Polo",
        "Ralph Lauren Short",
        "Tommy Hilfiger Short",
        "Nike Polo",
        "Adidas Polo",
        "Lacoste Polo",
        "Puma Fussball",
        "Levis Shorts",
    ],
    "exclude_keywords": [
        "schuhe", "sneaker", "boots", "stiefel", "sandalen", "turnschuhe",
        "loafer", "pumps", "schuh", "shoe", "shoes", "slipper",
        "absatz", "ballerina", "clogs", "crocs", "jordan", "yeezy",
        "vans", "converse", "hausschuhe", "flip flop", "sandale",
        "mütze", "cap", "beanie", "hut", "kappe", "snapback",
        "gürtel", "tasche", "bag", "rucksack", "parfum", "uhr",
        "schmuck", "brille", "handschuhe", "schal", "armband",
        "kette", "ring",
        "unterwäsche", "unterhose", "unterhosen", "unterhemd",
        "unterhemden", "boxer", "boxershorts", "slip", "bh",
        "strumpf", "tanga", "tangas", "string", "socken",
        "kleid", "kleider", "rock", "bluse", "leggings",
        "bikini", "badeanzug", "bademode",
        "baby", "kinder", "mädchen", "kids", "kinderbekleidung",
        "pyjama", "schlafanzug", "kostüm", "krawatte",
        "hose", "hosen", "jogginghose", "trainingshose", "jogger",
        "chino", "chinos", "jeans hose", "stoffhose",
        "t-shirt", "tshirt", "shirt", "longsleeve", "sweatshirt",
        "hoodie", "pullover", "jacke", "mantel",
    ],
    "defect_negations": [
        "keine fleck", "kein fleck", "ohne fleck",
        "keine mängel", "kein mangel", "ohne mängel",
        "keine beschädigung", "kein schaden", "ohne schaden",
        "makellos", "einwandfrei", "neuwertig", "tadellos",
        "keine kratzer", "kein kratzer",
        "keine löcher", "kein loch",
        "keine risse", "kein riss",
    ],
    "defect_keywords": [
        "fleck", "flecken", "blutfleck", "ölfleck", "weinfleck",
        "riss", "risse", "einriss",
        "loch", "löcher",
        "beschädigt", "beschädigung",
        "defekt", "kaputt",
        "kratzer",
        "abgenutzt", "abnutzung", "ausgeblichen", "verblasst",
        "makel", "gebrauchsspuren",
        "stain", "hole", "damaged", "worn",
        "pilling", "pillen",
        "verfärbt", "verfärbung", "farbabweichung",
        "schaden",
        "mangel", "mängel",
        "dreckig", "schmutzig",
        "gerissen", "abgerissen",
        "verwaschen", "ausgewaschen",
        "knopf fehlt", "knopf ab",
    ],
    "shipping_min": 3.0,
    "shipping_max": 5.0,
    "poll_interval": 20,
    "seen_ids_file": "seen_ids.json",
}

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "")
GECKODRIVER = "/usr/local/bin/geckodriver"

seen_ids = set()
total_found = 0
bot_status = "Startet..."
bot_log = []

def log(msg):
    global bot_log
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    bot_log.append(line)
    if len(bot_log) > 50:
        bot_log = bot_log[-50:]

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
        log("Starte frisch (keine seen_ids).")

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

def is_valid_title(title):
    t = title.lower()
    return not any(w in t for w in CONFIG["exclude_keywords"])

def is_valid_size(size_title):
    if not size_title or size_title.strip() in ["", "?", "-"]:
        return False
    s = size_title.upper().strip()
    if re.search(r'\bXL\b', s):
        return True
    if re.search(r'\bL\b', s) and not re.search(r'\bXXL\b|\bXS\b', s):
        return True
    return False

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
    "zufriedenstellend": "🔴 Zufriedenstellend",
    "satisfactory": "🔴 Zufriedenstellend",
    "akzeptabel": "🔴 Akzeptabel",
    "fair": "🔴 Akzeptabel",
}
CONDITION_ID_MAP = {
    6: "🟢 Neu mit Etikett",
    1: "🟡 Neu ohne Etikett",
    2: "🔵 Sehr gut",
    3: "🟠 Gut",
    4: "🔴 Zufriedenstellend",
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
    log("Starte Firefox...")
    options = webdriver.FirefoxOptions()
    options.add_argument("--headless")
    service = Service(GECKODRIVER)
    driver = webdriver.Firefox(service=service, options=options)
    driver.set_window_size(1920, 1080)
    log("Firefox gestartet!")
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
        log("Cookies bereits akzeptiert oder nicht gefunden.")

def fetch_items(driver, search_query):
    js = f"""
    var xhr = new XMLHttpRequest();
    xhr.open('GET', 'https://{CONFIG["domain"]}/api/v2/catalog/items?search_text={search_query.replace(" ", "+")}&price_to={CONFIG["price_max"]}&order=newest_first&status_ids[]=6&status_ids[]=1&status_ids[]=2&per_page=96', false);
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
            title = item.get("title", search_query)
            iid = str(item.get("id", ""))
            size_title = item.get("size_title", "") or ""
            if not iid or not is_valid_title(title) or not is_valid_size(size_title):
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
                "brand": search_query,
                "price": price,
                "size": size_title,
                "zustand": get_zustand(item),
                "photo": photo,
                "time": datetime.now().strftime("%H:%M:%S"),
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
            log(f"Fehler ({search_query}): {e}")
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
        data = json.loads(response).get("item", {})
        desc = data.get("description", "") or ""
        price = get_price(data.get("price", 0)) or item["price"]
        service_fee = get_price(data.get("service_fee", 0)) or calc_service_fee(price)
        new_zustand = get_zustand(data)
        if not new_zustand.startswith("❓"):
            item["zustand"] = new_zustand
        item["price"] = price
        item["description"] = desc[:300]
        item["service_fee"] = service_fee
        item["size"] = data.get("size_title", item["size"]) or item["size"]
        item["total_min"] = round(price + service_fee + CONFIG["shipping_min"], 2)
        item["total_max"] = round(price + service_fee + CONFIG["shipping_max"], 2)
        item["has_defect"] = check_defects(item["title"], desc)
    except:
        pass
    return item

def send_discord(item):
    if not DISCORD_WEBHOOK:
        log("Kein Discord Webhook konfiguriert!")
        return
    try:
        mangel_text = "⚠️ MÄNGEL ERWÄHNT!" if item["has_defect"] else "✅ Keine Mängel"
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
            fields.append({"name": "📝 Beschreibung", "value": item["description"], "inline": False})
        embed = {
            "title": f"🎯 {item['title']}",
            "url": item["url"],
            "color": color,
            "image": {"url": item["photo"]},
            "fields": fields,
            "footer": {"text": f"Vinted Snipe Bot | {item['time']}"},
        }
        r = req_lib.post(DISCORD_WEBHOOK, json={"embeds": [embed]}, timeout=10)
        log(f"Discord gesendet: {r.status_code}")
    except Exception as e:
        log(f"Discord Fehler: {e}")

def bot_loop():
    global total_found, bot_status
    load_seen_ids()
    first_run = len(seen_ids) == 0
    driver = None
    while True:
        try:
            if driver is None:
                driver = start_browser()
                setup(driver)
            for search_query in CONFIG["brands"]:
                items = fetch_items(driver, search_query)
                log(f"[{search_query}] {len(items)} gefunden")
                for item in items:
                    if item["id"] not in seen_ids:
                        seen_ids.add(item["id"])
                        if not first_run:
                            item = enrich_item(driver, item)
                            send_discord(item)
                            total_found += 1
                            log(f"NEU: {item['title']} | {item['total_min']}-{item['total_max']}€ | {item['zustand']}")
                time.sleep(1)
            if first_run:
                log(f"Erstinitialisierung: {len(seen_ids)} Artikel markiert. Ab jetzt werden neue gemeldet.")
                first_run = False
            save_seen_ids()
            bot_status = f"Läuft ✅ | Treffer: {total_found} | {datetime.now().strftime('%H:%M:%S')}"
            time.sleep(CONFIG["poll_interval"])
        except Exception as e:
            bot_status = f"Fehler: {e}"
            log(f"FEHLER im Bot-Loop: {e}")
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
    logs_html = "<br>".join(bot_log[-30:])
    return f"""
    <h2>🎯 Vinted Snipe Bot</h2>
    <b>Status:</b> {bot_status}<br><br>
    <b>Log:</b><br>{logs_html}
    """

threading.Thread(target=bot_loop, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
