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
from selenium.webdriver.common.keys import Keys

#TIME_LIMIT_SECONDS = 5 * 60  # 5 minutos
MAX_NON_GROUP_CHAT=1
EXCLUDE_TITLES = {
    "Rosmery Papel Asesora de Viajes Terandes",
    "Canal Comercial y Ventas | TLA CTA",
    "Salida fija Mex - Setiembre / 2025",
    "Salida fija Mex-Julio/Agosto",
    "Marketing Digital CTA TLA",
    "Ross Mery Asesora De Ventas",
    "Christian TLA",
    "Tierras de los andes",
    "TLA - CTA - ITT",
    "Marketing Team 🎸 TLA- CTA",
    "Ventas Interno",
    "OPERACIONES TERANDES",
    "Estrella Asesora de viajes a Perú",
    "VENTAS REDES SOCIALES INTERNO- LEADS Mercado Latino",
    "WhatsApp Business",
    "CULTURAS ANDINAS",
    "Salida fija Mex - Setiembre / 2025 🇲🇽✈️🇵🇪",
    "Salida fija Mex-Julio/Agosto",
    "Salida fija Mex - Octubre 2025 🥳🙌🏻"
}
META_BANNED_CHARS = {"*", "#", "•"} 

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
     # Filas del listado de chats (WhatsApp suele usar role="row")
    rows = pane.find_elements(By.XPATH, ".//div[@role='row']")

    titles = []
    seen = set()

    for row in rows:
        try:
            # Dentro de cada fila, el nombre/número del chat casi siempre es el primer span con title
            name_span = row.find_element(By.XPATH, ".//span[@title and normalize-space(@title)!='']")
            title = (name_span.get_attribute("title") or "").strip()

            if not title:
                continue
            if "\n" in title:
                continue
            if len(title) > 60:
                continue
            if title in ("Archivados", "WhatsApp"):
                continue

            if title not in seen:
                seen.add(title)
                titles.append(title)

        except Exception:
            # Si esa fila no tiene span title “usable”, la saltamos
            continue

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
########################################## normalizar titulo
def norm_title(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).lower()
EXCLUDE_TITLES_NORM = {norm_title(t) for t in EXCLUDE_TITLES}
######################################## detector del banner
def end_to_end_banner_present(driver) -> bool:
    """
    True si aparece el banner de cifrado E2E dentro del chat.
    """
    try:
        return len(driver.find_elements(
            By.XPATH,
            "//*[contains(., 'Los mensajes y las llamadas están cifrados de extremo a extremo')]"
        )) > 0
    except Exception:
        return False

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
######################################################### detector de audio
def bubble_has_audio(bubble) -> bool:
    """
    Detecta si una burbuja de mensaje parece ser un audio.
    WhatsApp suele renderizar audios con un botón de play y/o data-icon relacionado.
    """
    try:
        # 1) tag audio (a veces existe)
        if bubble.find_elements(By.TAG_NAME, "audio"):
            return True

        # 2) íconos típicos de play/audio
        if bubble.find_elements(By.XPATH, ".//*[@data-icon='audio-play' or @data-icon='audio-download']"):
            return True
        if bubble.find_elements(By.XPATH, ".//*[@data-icon='play' or @data-icon='msg-play']"):
            return True

        # 3) aria-label (ES/EN)
        if bubble.find_elements(By.XPATH, ".//*[contains(@aria-label,'Reproducir') or contains(@aria-label,'Play')]"):
            return True
        if bubble.find_elements(By.XPATH, ".//*[contains(@aria-label,'audio') or contains(@aria-label,'Audio')]"):
            return True
        if bubble.find_elements(By.XPATH, ".//*[contains(@aria-label,'nota de voz') or contains(@aria-label,'voice')]"):
            return True

        # 4) fallback: burbuja tiene un botón grande (play) y NO tiene texto
        btns = bubble.find_elements(By.XPATH, ".//button")
        if btns:
            txt = (bubble.text or "").strip()
            if not txt:
                return True

    except Exception:
        pass
    return False
####################################################### archivo adjunto

####################################################################################################################

def get_chat_scroller(driver):
    """
    Contenedor REAL que scrollea los mensajes del chat.
    (confirmado por tu consola: policy 'wa.web.conversation.messages')
    """
    return WebDriverWait(driver, 25).until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, "div.copyable-area [data-scrolltracepolicy='wa.web.conversation.messages']")
        )
    )

def get_scroll_metrics(driver, el):
    return driver.execute_script(
        "return {st: arguments[0].scrollTop, sh: arguments[0].scrollHeight, ch: arguments[0].clientHeight};",
        el
    )
def scroll_chat_step(driver, scroller):
    # métricas
    st = driver.execute_script("return arguments[0].scrollTop;", scroller) or 0
    sh = driver.execute_script("return arguments[0].scrollHeight;", scroller) or 0
    ch = driver.execute_script("return arguments[0].clientHeight;", scroller) or 0
    delta = sh - ch

    step = max(120, min(900, int(delta * 0.8)))

    if st > 5:
        driver.execute_script(
            "arguments[0].scrollTop = Math.max(0, arguments[0].scrollTop - arguments[1]);",
            scroller,
            step
        )
        time.sleep(1.2)
        return "scrolled"
    else:
        # arriba; espera a que cargue más
        time.sleep(2.5)
        return "at_top"
########################################################################################################################
def get_message_bubble_from_meta_el(meta_el):
    # sube al contenedor del mensaje (burbuja) más cercano
    return meta_el.find_element(By.XPATH, "./ancestor::div[@role='row'][1]")
###################################################################################################################
def bubble_has_attachment(bubble) -> bool:
    try:
        # tu caso: "Abrir foto" / "Abrir video"
        if bubble.find_elements(By.XPATH, ".//*[@role='button' and @aria-label and contains(@aria-label,'Abrir')]"):
            return True
        if bubble.find_elements(By.XPATH, ".//*[@role='button' and @aria-label and contains(@aria-label,'Open')]"):
            return True

        # fallback: img o video dentro de la burbuja
        if bubble.find_elements(By.XPATH, ".//img | .//video"):
            return True
    except Exception:
        pass
    return False

def scrape_messages_from_current_chat(driver, contact):
    WebDriverWait(driver, 25).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "div.copyable-area"))
    )
    scroller = get_chat_scroller(driver)

    messages = {}
    idle = 0
    last_len = 0

    while True:
        # 1) Recolectar visible
        elements = driver.find_elements(By.XPATH, "//*[@data-pre-plain-text]")
        for el in elements:
            meta = (el.get_attribute("data-pre-plain-text") or "").strip()
            text = (el.text or "").strip()
            # 🔥 AQUÍ VA: subir al contenedor burbuja del mensaje
            try:
                bubble = get_message_bubble_from_meta_el(el)
                if bubble:
                    labels = [x.get_attribute("aria-label") for x in bubble.find_elements(By.XPATH, ".//*[@role='button' and @aria-label]")]
                    if labels:
                        print("DEBUG labels:", labels[:5])
            except Exception:
                bubble = None
            # Si no hay texto, detectar adjunto (foto/video) y marcarlo
            if not text:
                if bubble and bubble_has_attachment(bubble):
                    text="[ADJUNTO]"
            # si tampoco hay meta, no guardes
            if not meta and text !="[ADJUNTO]":
                continue
            if any(el in meta for el in META_BANNED_CHARS):
                continue
            if not meta and not text:
                continue    
            key = f"{meta}||{text}"
            if key not in messages:
                messages[key] = {"contact": contact, "meta": meta, "text": text}

        # 2) ¿ya llegamos al inicio?
        if end_to_end_banner_present(driver):
            print("🔒 Banner de cifrado detectado. Fin del historial alcanzado.")
            break

        # 3) Click “mensajes anteriores del teléfono” si aparece
        if click_load_older_if_present(driver):
            time.sleep(1.8)
            continue

        # 4) Un SOLO paso de scroll
        scroll_chat_step(driver, scroller)

        # 5) Watchdog suave (para no colgarse infinito)
        if len(messages) == last_len:
            idle += 1
        else:
            idle = 0
        last_len = len(messages)

        if idle >= 30:
            print("⚠️ No está avanzando (WhatsApp no carga más).")
            input("Presiona ENTER para seguir intentando...")
            idle = 0

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

    try:
        non_group_count=0
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

            for title in new_titles:
                # ✅ corte global si ya llegamos a 200 chats NO-grupo
                if non_group_count >= MAX_NON_GROUP_CHAT:
                    print(f"🛑 Límite alcanzado: {MAX_NON_GROUP_CHAT} chats (sin contar grupos).")
                    break
                   
                print(f"📌 Abriendo chat: {title}")
                
                    
                    # si es grupo salta
                if norm_title(title) in EXCLUDE_TITLES_NORM:
                    print("⛔ En lista de excluidos. Saltando (no se scrapea).")
                    processed.add(title)
                    continue
                try:
                    open_chat_by_title(driver, title)
                    print("📩 Extrayendo mensajes...")
                    
                    rows = scrape_messages_from_current_chat(driver, title)
                    
                    print(f"✅ Mensajes: {len(rows)}")

                    all_rows.extend(rows)
                    processed.add(title)
                    # solo chats no grupo
                    non_group_count+=1
                    print(f"✅ Chats no-grupo procesados: {non_group_count}/{MAX_NON_GROUP_CHAT}")
                except Exception as e:
                    print(f"⚠️ Error en chat '{title}': {e}")
                    processed.add(title)
                    continue
            if non_group_count >= MAX_NON_GROUP_CHAT:
                break             
            scroll_left_pane(driver, pane_step)

    finally:
        # Guardar lo que haya (si hubo)
        print(f"\n📊 Chats procesados: {len(processed)}")
        print(f"📊 Mensajes totales recolectados: {len(all_rows)}")

        if all_rows:
            try:
                save_to_csv(output_csv, all_rows)
                print(f"\n✅ CSV generado correctamente: {output_csv}")
            except Exception as e:
                print("⚠️ Error guardando CSV:", e)
        else:
            print("⚠️ No se recolectaron mensajes. No se generará CSV.")

        # Cerrar el driver siempre al final
        try:
            driver.quit()
        except Exception:
            pass

if __name__ == "__main__":
    main()