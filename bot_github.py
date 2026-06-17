import json, os, sys, re, time
from datetime import datetime
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
        "Tommy Hilfiger", "Ralph Lauren", "Nike",
        "Adidas", "Lacoste", "Puma", "Levis Shorts"
    ],
    "exclude_keywords": [
        "schuhe", "sneaker", "boots", "stiefel", "sandalen", "turnschuhe",
        "loafer", "pumps", "schuh", "shoe", "shoes", "nike air", "slipper",
        "absatz", "ballerina", "clogs", "crocs", "jordan", "yeezy", "vans",
        "converse", "hausschuhe", "flip flop", "sandale",
        "mütze", "cap", "beanie", "hut", "kappe", "snapback",
        "gürtel", "tasche", "bag", "rucksack", "parfum", "uhr", "schmuck",
        "brille", "handschuhe", "schal", "armband", "kette", "ring",
        "unterwäsche", "unterhose", "boxer", "slip", "bh", "strumpf",
        "tanga", "tangas", "string",
        "socken", "kleid", "kleider", "rock", "bluse", "leggings",
        "bikini", "badeanzug", "baby", "kinder", "mädchen", "kids",
        "pyjama", "schlafanzug", "kostüm", "staubbeutel", "krawatte",
    ],
    "brand_extra_exclude": {
        "Adidas": ["hose", "hosen", "short", "shorts", "jogger", "jogginghose", "trainingshose"],
        "Nike": ["hose", "hosen", "short", "shorts", "jogger", "jogginghose", "trainingshose"],
    },
    "defect_keywords": [
        "fleck", "flecken", "riss", "loch", "beschädigt", "defekt",
        "kratzer", "abgenutzt", "ausgeblichen", "verblasst", "kaputt",
        "makel", "gebrauchsspuren", "kleine", "bisschen", "etwas",
        "minimal", "leicht", "kaum", "stain", "hole", "damaged",
        "worn", "pilling", "verfärb", "schaden", "mangel", "mängel",
        "dreckig", "schmutzig", "gerissen", "löcher",
    ],
    "shipping_min": 3.0,
    "shipping_max": 5.0,
    "seen_ids_file": "seen_ids.json",
    "max_job_minutes": 330,
}

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "")
GECKODRIVER = "/usr/local/bin/geckodriver"

def load_seen_ids():
    if os.path.exists(CONFIG["seen_ids_file"]):
        with open(CONFIG["seen_ids_file"]) as f:
            return set(json.load(f))
    return set()

def save_seen_ids(seen_ids):
    with open(CONFIG["seen_ids_file"], "w") as f:
        json.dump(list(seen_ids), f)

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

def is_valid_title(title, brand=None):
    t = title.lower()
    if any(w in t for w in CONFIG["exclude_keywords"]):
        return False
    extra = CONFIG["brand_extra_exclude"].get(brand, [])
    if any(w in t for w in extra):
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

CONDITION_MAP = {
    "neu mit etikett": "🟢 Neu mit Etikett", "neu, mit etikett": "🟢 Neu mit Etikett",
    "new with tags": "🟢 Neu mit Etikett", "brand new": "🟢 Neu mit Etikett",
    "neu ohne etikett": "🟡 Neu ohne Etikett", "neu, ohne etikett": "🟡 Neu ohne Etikett",
    "new without tags": "🟡 Neu ohne Etikett",
    "sehr gut": "🔵 Sehr gut", "sehr guter zustand": "🔵 Sehr gut", "very good": "🔵 Sehr gut",
    "gut": "🟠 Gut", "guter zustand": "🟠 Gut", "good": "🟠 Gut",
    "zufriedenstellend": "🔴 Zufriedenstellend", "satisfactory": "🔴 Zufriedenstellend",
    "akzeptabel": "🔴 Akzeptabel", "fair": "🔴 Akzeptabel",
}
CONDITION_ID_MAP = {
    6: "🟢 Neu mit Etikett", 1: "🟡 Neu ohne Etikett",
    2: "🔵 Sehr gut", 3: "🟠 Gut", 4: "🔴 Zufriedenstellend",
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
    options = webdriver.FirefoxOptions()
    options.add_argument("--headless")
    service = Service(GECKODRIVER)
    driver = webdriver.Firefox(service=service, options=options)
    driver.set_window_size(1920, 1080)
    return driver

def setup(driver):
    driver.get(f"https://{CONFIG['domain']}")
    time.sleep(4)
    try:
        WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
        ).click()
        time.sleep(2)
    except:
        pass

def fetch_items(driver, brand):
    js = f"""
    var xhr = new XMLHttpRequest();
    xhr.open('GET', 'https://{CONFIG["domain"]}/api/v2/catalog/items?search_text={brand.replace(" ", "+")}&price_to={CONFIG["price_max"]}&order=newest_first&status_ids[]=6&status_ids[]=1&status_ids[]=2&per_page=96', false);
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
            title = item.get("title", brand)
            iid = str(item.get("id", ""))
            size_title = item.get("size_title", "") or ""
            if not iid or not is_valid_title(title, brand) or not is_valid_size(size_title):
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
                "id": iid, "url": f"https://{CONFIG['domain']}/items/{iid}",
                "title": title, "brand": brand, "price": price, "size": size_title,
                "zustand": get_zustand(item), "photo": photo,
                "time": datetime.now().strftime("%H:%M:%S"),
                "description": "", "service_fee": service_fee,
                "shipping_min": CONFIG["shipping_min"], "shipping_max": CONFIG["shipping_max"],
                "total_min": total_min, "total_max": total_max, "has_defect": False,
            })
        return items
    except Exception as e:
        if "Expecting value" not in str(e):
            print(f"  Fehler ({brand}): {e}")
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
        desc_lower = (desc + " " + item["title"]).lower()
        item["has_defect"] = any(w in desc_lower for w in CONFIG["defect_keywords"])
    except:
        pass
    return item

def send_discord(item):
    if not DISCORD_WEBHOOK:
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
            "title": f"🎯 {item['title']}", "url": item["url"], "color": color,
            "image": {"url": item["photo"]}, "fields": fields,
            "footer": {"text": f"Vinted Snipe Bot | {item['time']}"},
        }
        req_lib.post(DISCORD_WEBHOOK, json={"embeds": [embed]}, timeout=10)
    except Exception as e:
        print(f"  Discord Fehler: {e}")

def main():
    start_time = time.time()
    seen_ids = load_seen_ids()
    first_run = len(seen_ids) == 0
    driver = start_browser()
    setup(driver)
    print("Bot läuft jetzt durchgehend (bis Zeitlimit, dann übernimmt sofort der nächste Lauf)...")
    try:
        while (time.time() - start_time) < CONFIG["max_job_minutes"] * 60:
            for brand in CONFIG["brands"]:
                items = fetch_items(driver, brand)
                print(f"[{brand}] {len(items)} gefunden")
                for item in items:
                    if item["id"] not in seen_ids:
                        seen_ids.add(item["id"])
                        if not first_run:
                            item = enrich_item(driver, item)
                            send_discord(item)
                            print(f"NEU: {item['title']} | {item['total_min']}-{item['total_max']}€")
                time.sleep(1)
            if first_run:
                print(f"Erstinitialisierung: {len(seen_ids)} Artikel markiert.")
                first_run = False
            save_seen_ids(seen_ids)
            time.sleep(20)
    finally:
        driver.quit()
    save_seen_ids(seen_ids)
    print("Lauf beendet (Zeitlimit) - naechster Lauf in der Warteschlange uebernimmt automatisch.")

if __name__ == "__main__":
    main()
