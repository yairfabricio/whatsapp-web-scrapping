import csv
import time
import os
import re
from datetime import datetime, timedelta

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


# ======================================================
# 1) DRIVER (perfil persistente)
# ======================================================

def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-logging"])

    profile_dir = os.path.join(os.path.expanduser("~"), "whatsapp_selenium_profile")
    chrome_options.add_argument(f"--user-data-dir={profile_dir}")

    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)


def wait_for_whatsapp_login(driver):
    print("\n" + "=" * 60)
    print("INICIA SESIÓN EN WHATSAPP WEB")
    print("1) Escanea el QR si es necesario")
    print("2) Espera a que cargue la lista de chats")
    print("3) Vuelve aquí y presiona ENTER")
    print("=" * 60 + "\n")
    input("Presiona ENTER cuando WhatsApp Web esté listo...")

    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.ID, "pane-side"))
    )


# ======================================================
# 2) WHATSAPP – PRIMER CHAT
# ======================================================

def get_first_chat_name(driver):
    pane = WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.ID, "pane-side"))
    )
    spans = pane.find_elements(By.XPATH, ".//span[@title]")

    for s in spans:
        title = (s.get_attribute("title") or "").strip()
        if title:
            return title
    return None


def open_chat_by_title(driver, contact):
    user = WebDriverWait(driver, 20).until(
        EC.element_to_be_clickable(
            (By.XPATH, f'//*[@id="pane-side"]//span[contains(@title, "{contact}")]')
        )
    )
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", user)
    user.click()
    time.sleep(2)

def get_visible_chat_titles(driver):
    """
    Devuelve los títulos (nombres) de chats visibles en el panel izquierdo,
    en el orden en que aparecen (WhatsApp: más recientes arriba).
    """
    pane = WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.ID, "pane-side"))
    )
    WebDriverWait(driver,30).until(
        lambda d:len(pane.find_elements(By.XPATH,".//span[@title]"))>0
    )
    spans = pane.find_elements(By.XPATH, ".//span[@title]")
    titles = []
    seen = set()

    for s in spans:
        title = (s.get_attribute("title") or "").strip()
        if not title:
            continue
        if "\n" in title:
            continue
        if len (title)>60:
            continue
        # (opcional) descarta cosas típicas que no son chats
        if title in ("Archivados","WhatsApp"):
            continue
        if title not in seen:
            seen.add(title)
            titles.append(title)        
    return titles


def scroll_left_pane(driver, step=900):
    """
    Baja el panel izquierdo para cargar chats más antiguos.
    """
    pane = WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.ID, "pane-side"))
    )
    driver.execute_script("arguments[0].scrollTop = arguments[0].scrollTop + arguments[1];", pane, step)
    time.sleep(1.2)
# ======================================================
# 3) FECHA (si luego quieres filtrar)
# ======================================================

def parse_date_from_meta(meta: str):
    if not meta:
        return None
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b", meta)
    if not m:
        return None

    d1, d2, y = m.group(1), m.group(2), m.group(3)
    y = int("20" + y) if len(y) == 2 else int(y)

    day = int(d1)
    month = int(d2)

    try:
        return datetime(y, month, day).date()
    except ValueError:
        return None


# ======================================================
# 4) CLICK "mensajes anteriores del teléfono"
# ======================================================

def click_load_older_if_present(driver):
    """
    Si aparece el aviso: 'Haz clic aquí para obtener mensajes anteriores de tu teléfono',
    hace click y espera. Devuelve True si clickeó.
    """
    try:
        # Caso común: un botón que contiene ese texto
        btns = driver.find_elements(
            By.XPATH,
            "//button[.//div[contains(., 'Haz clic aquí para obtener mensajes anteriores')]]"
        )
        if btns:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btns[0])
            time.sleep(0.3)
            btns[0].click()
            time.sleep(2.5)
            return True

        # Fallback: a veces es un div/spam clickeable
        divs = driver.find_elements(
            By.XPATH,
            "//*[contains(., 'Haz clic aquí para obtener mensajes anteriores') and (self::div or self::span)]"
        )
        if divs:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", divs[0])
            time.sleep(0.3)
            divs[0].click()
            time.sleep(2.5)
            return True

    except Exception:
        pass

    return False


# ======================================================
# 5) SCRAPEAR MENSAJES DEL CHAT ABIERTO
# ======================================================

def scrape_messages_from_current_chat(driver, contact):
    # Esperar zona del chat
    WebDriverWait(driver, 25).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "div.copyable-area"))
    )

    # Contenedor scrolleable real (según tu inspector)
    scroll_container = WebDriverWait(driver, 25).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "div[data-tab='8']"))
    )

    messages = {}
    prev_len = 0
    stable_rounds = 0
    step = 1200  # scroll inicial

    while True:
        elements = driver.find_elements(By.XPATH, "//div[contains(@class,'copyable-text')]")

        for el in elements:
            meta = (el.get_attribute("data-pre-plain-text") or "").strip()
            text = (el.text or "").strip()
            if not meta and not text:
                continue

            key = meta + "||" + text
            if key not in messages:
                messages[key] = {"contact": contact, "meta": meta, "text": text}

        # Si WhatsApp pide click para traer mensajes antiguos, clickeamos y re-leemos
        if click_load_older_if_present(driver):
            continue

        # cortar si ya no aparecen mensajes nuevos en 2 vueltas seguidas
        if len(messages) == prev_len:
            stable_rounds += 1
            if stable_rounds >= 2:
                break
        else:
            stable_rounds = 0

        prev_len = len(messages)

        # ✅ IMPORTANTE: este scroll debe estar DENTRO del while
        driver.execute_script(
            "arguments[0].scrollTop = arguments[0].scrollTop - arguments[1];",
            scroll_container,
            step
        )
        time.sleep(2.0)
        step = min(step + 400, 4000)

    return list(messages.values())


# ======================================================
# 6) CSV
# ======================================================

def save_to_csv(filename, rows):
    headers = ["contact", "meta", "text"]
    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


# ======================================================
# 7) MAIN
# ======================================================

def main():
    driver = setup_driver()
    driver.get("https://web.whatsapp.com/")
    wait_for_whatsapp_login(driver)

    output_name = input("Nombre del archivo CSV (sin .csv): ").strip()
    safe_name = "".join(c for c in output_name if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "-")
    if not safe_name:
        safe_name = "todos_los_chats"
    output_csv = f"{safe_name}.csv"

    all_rows = []
    processed = set()

    max_rounds = 80
    pane_step = 1200

    print("\n🚀 Recorriendo chats: del más reciente al más antiguo...")

    for r in range(max_rounds):
        titles = get_visible_chat_titles(driver)
        print("DEBUG: titles visibles =", titles[:8], " total =", len(titles))

        new_titles = [t for t in titles if t not in processed]

        if not new_titles:
            scroll_left_pane(driver, pane_step)
            titles2 = get_visible_chat_titles(driver)
            new_titles = [t for t in titles2 if t not in processed]

            if not new_titles:
                print("✅ No hay más chats nuevos en el panel. Terminando.")
                break

        # ✅ ESTE FOR VA FUERA DEL IF
        for title in new_titles:
            print(f"📌 Abriendo chat: {title}")
            try:
                open_chat_by_title(driver, title)
                print("📩 Extrayendo mensajes...")
                rows = scrape_messages_from_current_chat(driver, title)
                print(f"✅ Mensajes: {len(rows)}")

                all_rows.extend(rows)
                processed.add(title)

            except Exception as e:
                print(f"⚠️ Error en chat '{title}': {e}")
                processed.add(title)
                continue

        scroll_left_pane(driver, pane_step)

    driver.quit()

    print(f"\n📊 Chats procesados: {len(processed)}")
    print(f"📊 Mensajes totales recolectados: {len(all_rows)}")

    if not all_rows:
        print("⚠️ No se recolectaron mensajes. No se generará CSV.")
        return

    save_to_csv(output_csv, all_rows)
    print(f"\n✅ CSV generado correctamente: {output_csv}")

if __name__ == "__main__":
    main()