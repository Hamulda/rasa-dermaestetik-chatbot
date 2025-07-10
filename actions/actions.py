# rasa-chatbot/actions/actions.py

import json
import logging
from typing import Any, Text, Dict, List, Optional
import requests

from rasa_sdk import Action, Tracker, FormValidationAction
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.types import DomainDict
from rasa_sdk.events import SlotSet, ActiveLoop, AllSlotsReset, ConversationPaused

# --- Profesionální nastavení logování ---
# Umožňuje detailní sledování chování a chyb v produkčním prostředí.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Načtení dat s robustním ošetřením chyb ---
# Data se načtou pouze jednou při startu, což zajišťuje vysoký výkon.
# Pokud soubory chybí nebo jsou poškozené, bot nespadne, ale zaloguje kritickou chybu.
try:
    with open("data/products.json", 'r', encoding='utf-8') as f:
        ALL_PRODUCTS = json.load(f)
    with open("data/knowledge_base.json", 'r', encoding='utf-8') as f:
        KNOWLEDGE_BASE = json.load(f)
except FileNotFoundError as e:
    logger.critical(f"FATÁLNÍ CHYBA: Datový soubor nebyl nalezen. Chatbot nemůže doporučovat produkty. Chyba: {e}")
    ALL_PRODUCTS, KNOWLEDGE_BASE = [], {}
except json.JSONDecodeError as e:
    logger.critical(f"FATÁLNÍ CHYBA: Chyba v JSON formátu datového souboru. Chatbot nemůže doporučovat produkty. Chyba: {e}")
    ALL_PRODUCTS, KNOWLEDGE_BASE = [], {}

# --- Globální konstanty ---
PRODUCTS_PER_PAGE = 3
BASE_ESHOP_URL = "https://eshop.dermaestetik.cz/"

# --- Pomocná funkce pro zobrazení produktů ---
def display_products(dispatcher: CollectingDispatcher, products: List[Dict[Text, Any]], title: Optional[Text] = None):
    """
    Inteligentně formátuje a odesílá uživateli seznam produktů.
    Přidává prodejní prvky jako "Bestseller" pro zvýšení konverze.
    """
    if not products:
        dispatcher.utter_message(response="utter_no_products_found")
        return

    if title:
        dispatcher.utter_message(text=title)

    elements = []
    for product in products:
        payload = f'/get_product_details{{"product_name": "{product["name"]}"}}'
        buttons = [
            {"title": "Více informací", "payload": payload, "type": "postback"},
            {"title": "Koupit na e-shopu", "url": product.get('link', BASE_ESHOP_URL), "type": "web_url"}
        ]
        
        # Přidání prodejních "badges" pro vytvoření urgence a sociálního důkazu
        subtitle = f"Cena: {product.get('price', 'N/A')} Kč"
        if product.get('bestseller'):
            subtitle = f"🔥 BESTSELLER | {subtitle}"
        if product.get('stock_level') == 'low':
            subtitle = f"⚠️ POSLEDNÍ KUSY | {subtitle}"

        elements.append({
            "title": f"{product.get('brand', 'N/A')} - {product.get('name', 'Produkt')}",
            "subtitle": subtitle,
            "image_url": product.get('image_url', f'https://placehold.co/600x400/E8E8E8/444444?text={product.get("name")}'),
            "buttons": buttons
        })
    
    dispatcher.utter_message(attachment={"type": "template", "payload": {"template_type": "generic", "elements": elements}})

# ==============================================================================
# KLÍČOVÉ AKCE CHATBOTA
# ==============================================================================

class ActionRecommendProduct(Action):
    """Hlavní akce pro doporučení produktů s implementovanou cross-sell logikou."""
    def name(self) -> Text: return "action_recommend_product"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict) -> List[Dict]:
        if not ALL_PRODUCTS:
            dispatcher.utter_message(text="Omlouvám se, databáze produktů není momentálně dostupná.")
            return []

        skin_type = tracker.get_slot('skin_type') or []
        skin_concern = tracker.get_slot('skin_concern') or []
        logger.info(f"Filtruji produkty s kritérii: Pleť={skin_type}, Problém={skin_concern}")

        filtered_products = [p for p in ALL_PRODUCTS if (not skin_type or any(st.lower() in [s.lower() for s in p.get('skin_types', [])] for st in skin_type)) and (not skin_concern or any(sc.lower() in [s.lower() for s in p.get('skin_concerns', [])] for sc in skin_concern))]

        if not filtered_products:
            dispatcher.utter_message(response="utter_no_products_found")
            return []

        display_products(dispatcher, filtered_products[:PRODUCTS_PER_PAGE], title=f"Našla jsem {len(filtered_products)} skvělých produktů. Zde jsou ty nejlepší:")
        
        # --- PRODEJNÍ STRATEGIE: CROSS-SELL ---
        if len(filtered_products) > 0:
            first_product = filtered_products[0]
            complementary_ids = first_product.get('complementary_products', [])
            if complementary_ids:
                complementary_product = next((p for p in ALL_PRODUCTS if p.get('id') in complementary_ids), None)
                if complementary_product:
                    payload = f'/get_product_details{{"product_name": "{complementary_product["name"]}"}}'
                    dispatcher.utter_message(
                        text=f"💡 **PRO TIP:** Pro maximální účinek doporučuji k produktu **{first_product['name']}** přidat i **{complementary_product['name']}**. Posílí jeho efekt a dodá pleti komplexní péči.",
                        buttons=[{"title": f"Zjistit víc o {complementary_product['name']}", "payload": payload, "type": "postback"}]
                    )

        return [SlotSet("last_recommended_ids", [p['id'] for p in filtered_products]), SlotSet("recommendation_page", 1.0)]

class ActionRecommendRoutine(Action):
    """Sestaví a doporučí kompletní pečující rutinu, čímž zvyšuje hodnotu objednávky."""
    def name(self) -> Text: return "action_recommend_routine"
    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict) -> List[Dict]:
        routine_type = next(tracker.get_latest_entity_values("routine_type"), "kompletní")
        skin_concern = tracker.get_slot("skin_concern") or []

        if not skin_concern:
            dispatcher.utter_message(text="Abych vám mohla sestavit rutinu, potřebuji vědět, jaký hlavní problém řešíte (např. akné, vrásky).")
            return [SlotSet("skin_concern", None)]
        
        logger.info(f"Sestavuji '{routine_type}' rutinu pro problém: {skin_concern}")
        
        # Zde by byla komplexní logika. Pro ukázku vybíráme klíčové kategorie.
        # V reálném světě by tato logika mohla být mnohem sofistikovanější.
        routine_map = {
            "cleanser": next((p for p in ALL_PRODUCTS if "čisticí" in p.get('category','').lower() and any(sc.lower() in p.get('skin_concerns', []) for sc in skin_concern)), None),
            "serum": next((p for p in ALL_PRODUCTS if "sérum" in p.get('category','').lower() and any(sc.lower() in p.get('skin_concerns', []) for sc in skin_concern)), None),
            "cream": next((p for p in ALL_PRODUCTS if "krém" in p.get('category','').lower() and any(sc.lower() in p.get('skin_concerns', []) for sc in skin_concern)), None),
            "spf": next((p for p in ALL_PRODUCTS if "spf" in p.get('category','').lower()), None) if routine_type == "ranní" else None
        }
        routine_products = [p for p in routine_map.values() if p]

        if len(routine_products) < 2: # Rutina nedává smysl, pokud nemá aspoň 2 produkty
            dispatcher.utter_message(response="utter_suggest_consultation")
            return []
            
        total_price = sum(p.get('price', 0) for p in routine_products)
        display_products(dispatcher, routine_products, title=f"Sestavila jsem pro vás ideální **{routine_type} rutinu** pro řešení problému **{skin_concern[0]}**. Celková cena: {total_price} Kč.")
        return []

class ActionGetProductDetails(Action):
    """Získá a zobrazí detailní informace o konkrétním produktu."""
    def name(self) -> Text: return "action_get_product_details"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict) -> List[Dict]:
        product_name = next(tracker.get_latest_entity_values("product_name"), None)
        if not product_name:
            dispatcher.utter_message(text="Omlouvám se, nerozpoznala jsem, na který produkt se ptáte.")
            return []

        product = next((p for p in ALL_PRODUCTS if p['name'].lower() == product_name.lower()), None)
        if not product:
            dispatcher.utter_message(text=f"Produkt '{product_name}' se mi nepodařilo najít v databázi.")
            return []
        
        description = product.get("description", "Popis není k dispozici.")
        message = f"**{product.get('brand')} - {product.get('name')}**\n\n{description}"
        dispatcher.utter_message(text=message)
        dispatcher.utter_message(response="utter_anything_else")
        return []


class ActionShowNextProducts(Action):
    """Zobrazí další stránku produktů z předchozího vyhledávání."""
    def name(self) -> Text: return "action_show_next_products"
    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict) -> List[Dict]:
        last_recommended_ids = tracker.get_slot("last_recommended_ids") or []
        page = tracker.get_slot("recommendation_page") or 1.0

        if not last_recommended_ids:
            dispatcher.utter_message(text="Nejprve musíme najít nějaké produkty. Zkuste nové vyhledávání.")
            return []

        start_index = int(page * PRODUCTS_PER_PAGE)
        if start_index >= len(last_recommended_ids):
            dispatcher.utter_message(text="Už jsem vám ukázala všechny nalezené produkty.")
            return []

        end_index = start_index + PRODUCTS_PER_PAGE
        next_product_ids = last_recommended_ids[start_index:end_index]
        products_to_show = [p for p in ALL_PRODUCTS if p['id'] in next_product_ids]

        display_products(dispatcher, products_to_show)
        return [SlotSet("recommendation_page", page + 1.0)]


# ==============================================================================
# FORMA A VALIDACE
# ==============================================================================

class ValidateProductRecommendationForm(FormValidationAction):
    """Validuje vstupy pro formulář a zajišťuje, že jsou smysluplné."""
    def name(self) -> Text: return "validate_product_recommendation_form"

    def _validate_input(self, value: Any, known_values_key: str) -> Optional[List[Text]]:
        if not isinstance(value, list): value = [value]
        known_values = [v.lower() for v in KNOWLEDGE_BASE.get(known_values_key, [])]
        validated = [item for item in value if item.lower() in known_values]
        return validated or None

    async def validate_skin_type(self, value: Any, dispatcher: CollectingDispatcher, **kwargs) -> Dict[Text, Any]:
        validated = self._validate_input(value, "KNOWN_SKIN_TYPES")
        if not validated:
            dispatcher.utter_message(text=f"Typ pleti '{value}' neznám. Zkuste prosím jednu z možností: suchá, mastná, smíšená, citlivá.")
            return {"skin_type": None}
        return {"skin_type": validated}

    async def validate_skin_concern(self, value: Any, dispatcher: CollectingDispatcher, **kwargs) -> Dict[Text, Any]:
        validated = self._validate_input(value, "KNOWN_SKIN_CONCERNS")
        if not validated:
            dispatcher.utter_message(text=f"Problém '{value}' neznám. Zkuste prosím: akné, vrásky, póry, pigmentace.")
            return {"skin_concern": None}
        return {"skin_concern": validated}

# ==============================================================================
# GDPR A UTILITNÍ AKCE
# ==============================================================================

class ActionSetGdprConsent(Action):
    """Nastaví souhlas s GDPR."""
    def name(self) -> Text: return "action_set_gdpr_consent"
    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict) -> List[Dict]:
        return [SlotSet("gdpr_consent", True)]

class ActionManageGdpr(Action):
    """Zpracovává export a mazání uživatelských dat."""
    def name(self) -> Text: return "action_manage_gdpr"
    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict) -> List[Dict]:
        intent_name = tracker.latest_message['intent'].get('name')
        
        if intent_name == "gdpr_export":
            dispatcher.utter_message(response="utter_gdpr_export_info")
            events = json.dumps(tracker.events, indent=2)
            dispatcher.utter_message(text=f"```json\n{events}\n```")
            logger.info(f"Export dat pro uživatele {tracker.sender_id}")
        elif intent_name == "gdpr_delete" or (tracker.latest_action_name == "utter_gdpr_delete_confirm" and intent_name == "affirm"):
            logger.info(f"Požadavek na smazání dat pro uživatele {tracker.sender_id}.")
            dispatcher.utter_message(response="utter_gdpr_deleted")
            # V reálném nasazení by zde bylo volání API pro smazání dat
            # Pro simulaci ukončíme konverzaci a po dalším startu bude prázdná.
            return [ConversationPaused(), AllSlotsReset()]
        return []

class ActionResetSlots(Action):
    """Akce pro resetování všech slotů a restart konverzace."""
    def name(self) -> Text: return "action_reset_slots"
    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict) -> List[Dict]:
        return [AllSlotsReset()]
        
class ActionDefaultFallback(Action):
    """
    Inteligentní fallback. Pokud si bot není jistý, nabídne nejčastější akce
    nebo konzultaci.
    """
    def name(self) -> Text:
        return "action_default_fallback"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict) -> List[Dict[Text, Any]]:
        dispatcher.utter_message(
            text="Omlouvám se, teď jsem vám úplně nerozuměla. Mohu pro vás zkusit:",
            buttons=[
                {"title": "Doporučit produkt", "payload": "/ask_product_recommendation"},
                {"title": "Sestavit rutinu", "payload": "/ask_for_routine"},
                {"title": "Objednat konzultaci", "payload": "/book_consultation"},
            ]
        )
        return []

