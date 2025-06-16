import json
import logging
from typing import Any, Text, Dict, List, Optional

from rasa_sdk import Action, Tracker, FormValidationAction
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, ActiveLoop, AllSlotsReset
from rasa_sdk.types import DomainDict

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)

KNOWLEDGE_BASE_FILE_PATH = './data/knowledge_base.json'
PRODUCTS_FILE_PATH = './data/products.json'
BASE_ESHOP_URL = "https://eshop.dermaestetik.cz"
PRODUCTS_PER_PAGE = 3

def load_json_file(file_path: Text, description: Text) -> Any:
    """Načte a parsuje JSON soubor s robustním error handlingem."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logger.info(f"Soubor '{description}' ('{file_path}') byl úspěšně načten.")
        return data
    except FileNotFoundError:
        logger.error(f"Kritická chyba: Soubor '{description}' ('{file_path}') nebyl nalezen.")
        return []
    except json.JSONDecodeError as e:
        logger.error(f"Kritická chyba: Chyba při dekódování JSON souboru '{description}': {e}")
        return []
    except Exception as e:
        logger.error(f"Kritická chyba: Neočekávaná chyba při načítání souboru '{description}': {e}")
        return []

knowledge_base_data = load_json_file(KNOWLEDGE_BASE_FILE_PATH, "znalostní báze")
products_data = load_json_file(PRODUCTS_FILE_PATH, "katalog produktů")

KNOWN_BRANDS = knowledge_base_data.get("KNOWN_BRANDS", [])
KNOWN_SKIN_AREAS = knowledge_base_data.get("KNOWN_SKIN_AREAS", [])
KNOWN_SKIN_TYPES = knowledge_base_data.get("KNOWN_SKIN_TYPES", [])
KNOWN_PRODUCT_CATEGORIES = knowledge_base_data.get("KNOWN_PRODUCT_CATEGORIES", [])
KNOWN_PRODUCT_ATTRIBUTES = knowledge_base_data.get("KNOWN_PRODUCT_ATTRIBUTES", [])
KNOWN_SKIN_CONCERNS = knowledge_base_data.get("KNOWN_SKIN_CONCERNS", [])
NEGATION_TRIGGERS = ["nechci", "bez", "ne", "kromě", "vynechat"]
AMBIGUOUS_CATEGORIES = {"krém": ["denní krém", "noční krém", "oční krém"]}


def display_products(dispatcher: CollectingDispatcher, products_to_display: List[Dict], start_index: int = 0):
    """Pomocná funkce pro zobrazení seznamu produktů s číslováním."""
    if not products_to_display:
        return

    for i, product in enumerate(products_to_display):
        name = product.get('name', 'Neznámý název')
        desc = product.get('description', 'Popis není k dispozici.')
        link = product.get('link')
        price = product.get('price')
        message = f"**{start_index + i + 1}. {name}**" + (f" (cena: {price} Kč)" if price else "") + f": {desc}"
        if link:
            full_link = link if link.startswith('http') else f'{BASE_ESHOP_URL}/{link.lstrip("/")}'
            message += f"\n   Více zde: {full_link}"
        dispatcher.utter_message(text=message)

def _get_product_from_tracker(tracker: Tracker, order_text: Text) -> Optional[Dict]:
    """Získá produkt na základě pořadí ('první', 'druhý'...) z posledního doporučení."""
    order_map = {"první": 0, "druhý": 1, "třetí": 2, "čtvrtý": 3, "pátý": 4}
    idx = order_map.get(order_text.lower())
    if idx is None:
        return None

    last_ids = tracker.get_slot("last_recommended_ids")
    if not last_ids or idx >= len(last_ids):
        return None

    product_id = last_ids[idx]
    return next((p for p in products_data if p.get('id') == product_id), None)


class ActionRecommendProduct(Action):
    """Hlavní akce, která filtruje produkty, doporučuje je a spravuje kontext."""

    def name(self) -> Text:
        return "action_recommend_product"

    @staticmethod
    def _normalize_string(value: Any) -> Optional[str]:
        return str(value).strip().lower() if value else None

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        logger.info(f"--- Akce '{self.name()}' ZAHÁJENA ---")

        product_category = self._normalize_string(tracker.get_slot("product_category"))
        if product_category and product_category in AMBIGUOUS_CATEGORIES:
            options = AMBIGUOUS_CATEGORIES[product_category]
            buttons = [{"title": opt.capitalize(), "payload": f'/inform{{"product_category":"{opt}"}}'} for opt in options]
            dispatcher.utter_message(
                text=f"Jistě, jaký typ krému máte na mysli?",
                buttons=buttons
            )
            return [SlotSet("product_category", None)]

        active_filters = {
            "skin_type": [self._normalize_string(st) for st in (tracker.get_slot("skin_type") or [])],
            "skin_concern": [self._normalize_string(sc) for sc in (tracker.get_slot("skin_concern") or [])],
            "product_category": product_category,
            "product_attribute": [self._normalize_string(pa) for pa in (tracker.get_slot("product_attribute") or [])],
            "brand": self._normalize_string(tracker.get_slot("brand")),
            "skin_area": self._normalize_string(tracker.get_slot("skin_area")),
        }
        excluded_filters = {
            "product_category": [self._normalize_string(pc) for pc in (tracker.get_slot("excluded_product_category") or [])],
            "brand": [self._normalize_string(b) for b in (tracker.get_slot("excluded_brand") or [])]
        }

        if not products_data or not isinstance(products_data, list):
            dispatcher.utter_message(text="Omlouvám se, mám potíže s přístupem ke katalogu produktů.")
            return []

        recommended_products = []
        for product in products_data:
            match_skin_type = not active_filters["skin_type"] or any(st in [self._normalize_string(p) for p in product.get("skin_types", [])] for st in active_filters["skin_type"])
            match_skin_concern = not active_filters["skin_concern"] or any(sc in [self._normalize_string(p) for p in product.get("skin_concerns", [])] for sc in active_filters["skin_concern"])
            match_product_category = not active_filters["product_category"] or active_filters["product_category"] == self._normalize_string(product.get("category", ""))
            match_product_attributes = not active_filters["product_attribute"] or all(attr in [self._normalize_string(p) for p in product.get("attributes", [])] for attr in active_filters["product_attribute"])
            match_brand = not active_filters["brand"] or active_filters["brand"] == self._normalize_string(product.get("brand", ""))
            match_skin_area = not active_filters["skin_area"] or active_filters["skin_area"] in [self._normalize_string(p) for p in product.get("skin_areas", [])]

            exclude_by_category = excluded_filters["product_category"] and self._normalize_string(product.get("category", "")) in excluded_filters["product_category"]
            exclude_by_brand = excluded_filters["brand"] and self._normalize_string(product.get("brand", "")) in excluded_filters["brand"]

            if all([match_skin_type, match_skin_concern, match_product_category, match_product_attributes, match_brand, match_skin_area]) and not (exclude_by_category or exclude_by_brand):
                recommended_products.append(product)

        logger.info(f"Po filtrování nalezeno {len(recommended_products)} produktů.")

        if not recommended_products:
            dispatcher.utter_message(text="Je mi líto, ale nenašla jsem žádný produkt, který by přesně odpovídal Vašim požadavkům. Zkuste prosím upravit kritéria.")
            return [SlotSet("last_recommended_ids", [])]

        slot_sort_preference = tracker.get_slot("sort_preference")
        if slot_sort_preference == "price_asc":
            recommended_products.sort(key=lambda p: (p.get("price") is None, p.get("price", float('inf'))))
        elif slot_sort_preference == "price_desc":
            recommended_products.sort(key=lambda p: (p.get("price") is None, p.get("price", -float('inf'))), reverse=True)
        else:
            recommended_products.sort(key=lambda p: (p.get("name") is None, p.get("name", "")))

        recommended_ids = [p.get('id') for p in recommended_products if p.get('id')]

        dispatcher.utter_message(text=f"Našla jsem celkem {len(recommended_products)} produktů. Zde jsou první z nich:")
        display_products(dispatcher, recommended_products[:PRODUCTS_PER_PAGE], start_index=0)

        events = [
            SlotSet("sort_preference", None),
            SlotSet("last_recommended_ids", recommended_ids),
            SlotSet("recommendation_page", 1)
        ]

        if len(recommended_products) > PRODUCTS_PER_PAGE:
            dispatcher.utter_message(text="Pokud si přejete vidět další, stačí napsat \"ukaž další\". Můžete si také nechat produkty porovnat (např. 'porovnej první a druhý') nebo si je uložit ('přidej první do oblíbených').")

        if active_filters["product_category"]:
            cat = active_filters["product_category"]
            if cat in ["čistící gel", "čistící pěna", "čistící olej"]:
                dispatcher.utter_message(text="Mohu Vám k tomuto čisticímu produktu doporučit i vhodné sérum pro další krok péče?", buttons=[{"title": "Ano, najít sérum", "payload": "/inform{\"product_category\":\"sérum\"}"}, {"title": "Ne, děkuji", "payload": "/deny"}])
            elif cat == "sérum":
                dispatcher.utter_message(text="Chcete k tomuto séru doporučit i vhodný hydratační krém?", buttons=[{"title": "Ano, najít krém", "payload": "/inform{\"product_category\":\"krém\"}"}, {"title": "Ne, děkuji", "payload": "/deny"}])

        return events


class ActionShowNextProducts(Action):
    """Akce pro zobrazení další stránky produktů (paginace)."""
    def name(self) -> Text: return "action_show_next_products"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        last_ids = tracker.get_slot("last_recommended_ids")
        page = tracker.get_slot("recommendation_page") or 0

        if not last_ids:
            dispatcher.utter_message(text="Omlouvám se, nemám žádné předchozí výsledky k zobrazení.")
            return []

        start_index = page * PRODUCTS_PER_PAGE
        all_recommended_products = [p for p in products_data if p.get('id') in last_ids]
        all_recommended_products.sort(key=lambda p: last_ids.index(p.get('id')))

        products_to_show = all_recommended_products[start_index : start_index + PRODUCTS_PER_PAGE]

        if not products_to_show:
            dispatcher.utter_message(text="To už jsou všechny produkty, které jsem podle zadaných kritérií našla.")
            return []

        dispatcher.utter_message(text=f"Jistě, zde jsou další produkty:")
        display_products(dispatcher, products_to_show, start_index=start_index)

        new_page = page + 1
        if len(all_recommended_products) > start_index + PRODUCTS_PER_PAGE:
             dispatcher.utter_message(text="Přejete si zobrazit další?")

        return [SlotSet("recommendation_page", new_page)]


class ActionRefilterByPrice(Action):
    """Akce, která vezme doporučené produkty a přefiltruje je podle ceny."""
    def name(self) -> Text: return "action_refilter_by_price"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        last_recommended_ids = tracker.get_slot("last_recommended_ids")
        intent_name = tracker.latest_message['intent'].get('name')
        if not last_recommended_ids:
            dispatcher.utter_message(text="Omlouvám se, ale nejdříve musím něco doporučit, abych to mohl přefiltrovat.")
            return []

        last_recommended_products = [p for p in products_data if p.get('id') in last_recommended_ids]
        if not last_recommended_products:
            dispatcher.utter_message(text="Omlouvám se, nedaří se mi najít původně doporučené produkty.")
            return []

        prices = [p.get("price") for p in last_recommended_products if p.get("price") is not None]
        if not prices:
             dispatcher.utter_message(text="Omlouvám se, u těchto produktů nemám informaci o ceně, takže je nemohu porovnat.")
             return []
        avg_price = sum(prices) / len(prices)

        refiltered_products = []
        if intent_name == "inform_cheaper":
            refiltered_products = [p for p in last_recommended_products if p.get("price") and p.get("price") < avg_price]
            refiltered_products.sort(key=lambda p: p.get("price", 0), reverse=True)
        elif intent_name == "inform_expensive":
            refiltered_products = [p for p in last_recommended_products if p.get("price") and p.get("price") > avg_price]
            refiltered_products.sort(key=lambda p: p.get("price", 0))

        if not refiltered_products:
            message = "Bohužel v původním výběru žádné další výrazně levnější produkty nejsou." if intent_name == "inform_cheaper" else "Bohužel v původním výběru žádné další výrazně dražší produkty nejsou."
            dispatcher.utter_message(text=message)
        else:
            dispatcher.utter_message(text=f"Jistě, našla jsem v původním výběru {len(refiltered_products)} {'levnějších' if intent_name == 'inform_cheaper' else 'dražších'} produktů:")
            display_products(dispatcher, refiltered_products[:PRODUCTS_PER_PAGE])
        return []


class ActionResetFilters(Action):
    """Akce pro vymazání všech filtrů a resetování konverzace."""
    def name(self) -> Text: return "action_reset_filters"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        dispatcher.utter_message(text="Dobře, zapomněla jsem všechna přechozí kritéria. S čím vám mohu pomoci nyní?")
        return [AllSlotsReset()]


class ActionShowCurrentFilters(Action):
    """Akce, která uživateli ukáže, jaké filtry jsou aktuálně nastaveny."""
    def name(self) -> Text: return "action_show_current_filters"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        active_filters_text = []
        if tracker.get_slot("skin_type"): active_filters_text.append(f"typ pleti: **{', '.join(tracker.get_slot('skin_type'))}**")
        if tracker.get_slot("skin_concern"): active_filters_text.append(f"problém pleti: **{', '.join(tracker.get_slot('skin_concern'))}**")
        if tracker.get_slot("product_category"): active_filters_text.append(f"kategorie produktu: **{tracker.get_slot('product_category')}**")
        if tracker.get_slot("brand"): active_filters_text.append(f"značka: **{tracker.get_slot('brand')}**")
        if tracker.get_slot("excluded_product_category"): active_filters_text.append(f"nechci kategorii: **{', '.join(tracker.get_slot('excluded_product_category'))}**")
        if tracker.get_slot("excluded_brand"): active_filters_text.append(f"nechci značku: **{', '.join(tracker.get_slot('excluded_brand'))}**")

        if not active_filters_text:
            dispatcher.utter_message("Momentálně nemám nastavené žádné filtry.")
        else:
            dispatcher.utter_message(f"Aktuálně hledám podle těchto kritérií: {'; '.join(active_filters_text)}.")
        return []


class ActionCompareProducts(Action):
    """Porovná dva produkty z posledního doporučení."""
    def name(self) -> Text: return "action_compare_products"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        entities = tracker.latest_message.get("entities", [])
        product_orders = [e["value"] for e in entities if e["entity"] == "product_order"]

        if len(product_orders) < 2:
            dispatcher.utter_message("Prosím, řekněte mi, které dva produkty mám porovnat (např. 'porovnej první a druhý').")
            return []

        product1 = _get_product_from_tracker(tracker, product_orders[0])
        product2 = _get_product_from_tracker(tracker, product_orders[1])

        if not product1 or not product2:
            dispatcher.utter_message("Omlouvám se, nenašla jsem produkty, které chcete porovnat. Zkuste prosím jiné.")
            return []

        p1_name = product1.get('name', 'N/A')
        p2_name = product2.get('name', 'N/A')
        p1_price = product1.get('price', 'N/A')
        p2_price = product2.get('price', 'N/A')
        p1_concerns = ', '.join(product1.get('skin_concerns', [])) or 'N/A'
        p2_concerns = ', '.join(product2.get('skin_concerns', [])) or 'N/A'

        message = (
            f"Zde je porovnání:\n\n"
            f"| Vlastnost      | **{p1_name}** | **{p2_name}** |\n"
            f"|----------------|----------------|----------------|\n"
            f"| Cena (Kč)      | {p1_price}     | {p2_price}     |\n"
            f"| Řeší problémy  | {p1_concerns}  | {p2_concerns}  |"
        )
        dispatcher.utter_message(message)
        return []


class ActionManageWishlist(Action):
    """Spravuje seznam přání (přidání, zobrazení)."""
    def name(self) -> Text: return "action_manage_wishlist"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        intent_name = tracker.latest_message['intent'].get('name')
        wishlist = tracker.get_slot("wishlist") or []

        if intent_name == 'show_wishlist':
            if not wishlist:
                dispatcher.utter_message("Váš seznam přání je prázdný.")
                return []

            wishlist_products = [p for p in products_data if p.get('id') in wishlist]
            dispatcher.utter_message("Zde jsou produkty z vašeho seznamu přání:")
            display_products(dispatcher, wishlist_products)
            return []

        elif intent_name == 'add_to_wishlist':
            entities = tracker.latest_message.get("entities", [])
            product_order = next((e["value"] for e in entities if e["entity"] == "product_order"), None)

            if not product_order:
                dispatcher.utter_message("Prosím, řekněte mi, který produkt mám přidat (např. 'přidej první').")
                return []

            product_to_add = _get_product_from_tracker(tracker, product_order)
            if not product_to_add:
                dispatcher.utter_message("Tento produkt nemohu najít.")
                return []

            product_id = product_to_add.get('id')
            if product_id in wishlist:
                dispatcher.utter_message(f"Produkt **{product_to_add.get('name')}** již máte v seznamu přání.")
            else:
                wishlist.append(product_id)
                dispatcher.utter_message(f"Přidala jsem **{product_to_add.get('name')}** do vašeho seznamu přání.")
            return [SlotSet("wishlist", wishlist)]

        return []


class ValidateProductRecommendationForm(FormValidationAction):
    """Validuje sloty pro formulář, nyní i s podporou negací."""
    def name(self) -> Text: return "validate_product_recommendation_form"

    @staticmethod
    def _normalize_value(value: Any) -> Optional[str]:
        return str(value).strip().lower() if value else None

    def _extract_negations(self, text: str, entities: List[Dict]) -> Dict[Text, List[Text]]:
        """Extrahování negovaných entit z textu."""
        negated = {"brand": [], "product_category": []}
        text_lower = text.lower()

        for trigger in NEGATION_TRIGGERS:
            if trigger in text_lower:
                for entity in entities:
                    if trigger in text_lower[max(0, entity['start'] - 10):entity['end'] + 10]:
                        if entity['entity'] in negated:
                            negated[entity['entity']].append(entity['value'])
        return negated

    async def validate(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> List[Dict[Text, Any]]:
        """Hlavní validační metoda, která zpracovává i negace."""
        latest_message = tracker.latest_message
        text = latest_message.get("text", "")
        entities = latest_message.get("entities", [])

        negated_entities = self._extract_negations(text, entities)

        events = []
        if negated_entities["brand"]:
            events.append(SlotSet("excluded_brand", list(set(negated_entities["brand"]))))
            logger.info(f"Detekována negace pro značky: {negated_entities['brand']}")
        if negated_entities["product_category"]:
            events.append(SlotSet("excluded_product_category", list(set(negated_entities["product_category"]))))
            logger.info(f"Detekována negace pro kategorie: {negated_entities['product_category']}")

        events.extend(await super().validate(dispatcher, tracker, domain))
        return events

    async def _validate_list_slot(self, slot_name: Text, value: Any, known_values: List[Text], dispatcher: CollectingDispatcher) -> Dict[Text, Any]:
        if not value: return {slot_name: None}
        items_to_check = [v.strip() for v in str(value).replace(" a ", ",").split(',')] if isinstance(value, str) else value
        validated_items, unrecognized_items = [], []
        for item in items_to_check:
            normalized_item = self._normalize_value(item)
            if not normalized_item: continue
            if normalized_item in known_values or slot_name == "skin_concern":
                if normalized_item not in validated_items: validated_items.append(normalized_item)
            else:
                unrecognized_items.append(item)
        if unrecognized_items:
            dispatcher.utter_message(text=f"Některým hodnotám pro '{slot_name}' nerozumím: {', '.join(unrecognized_items)}.")
        return {slot_name: validated_items or None}

    async def _validate_text_slot(self, slot_name: Text, value: Any, known_values: List[Text], dispatcher: CollectingDispatcher) -> Dict[Text, Any]:
        normalized_value = self._normalize_value(value)
        reset_keywords = ["nevim", "žádný", "zadny", "je mi to jedno", "nezalezi", "cokoliv", "jakykoliv", "nechci", "nepotřebuji", "nepotrebuji", "preskocit", "přeskočit"]
        if not normalized_value or normalized_value in reset_keywords:
            return {slot_name: None}
        if normalized_value in known_values:
            return {slot_name: normalized_value}
        for known_val in known_values:
            if normalized_value in known_val:
                logger.info(f"Nalezena podobnost pro '{normalized_value}', použito '{known_val}'.")
                return {slot_name: known_val}
        dispatcher.utter_message(text=f"Hodnotu '{value}' pro '{slot_name}' bohužel neznám. Zkuste například: {', '.join(known_values[:3])}")
        return {slot_name: None}

    async def validate_skin_type(self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> Dict[Text, Any]:
        return await self._validate_list_slot("skin_type", slot_value, KNOWN_SKIN_TYPES, dispatcher)
    async def validate_skin_concern(self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> Dict[Text, Any]:
        return await self._validate_list_slot("skin_concern", slot_value, KNOWN_SKIN_CONCERNS, dispatcher)
    async def validate_product_category(self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> Dict[Text, Any]:
        text = tracker.latest_message.get("text", "").lower()
        if any(trigger in text for trigger in NEGATION_TRIGGERS):
            return {}
        return await self._validate_text_slot("product_category", slot_value, KNOWN_PRODUCT_CATEGORIES, dispatcher)
    async def validate_product_attribute(self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> Dict[Text, Any]:
        return await self._validate_list_slot("product_attribute", slot_value, KNOWN_PRODUCT_ATTRIBUTES, dispatcher)
    async def validate_brand(self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> Dict[Text, Any]:
        text = tracker.latest_message.get("text", "").lower()
        if any(trigger in text for trigger in NEGATION_TRIGGERS):
            return {}
        return await self._validate_text_slot("brand", slot_value, KNOWN_BRANDS, dispatcher)
    async def validate_skin_area(self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> Dict[Text, Any]:
        return await self._validate_text_slot("skin_area", slot_value, KNOWN_SKIN_AREAS, dispatcher)


class ValidateAppointmentForm(FormValidationAction):
    """Validuje sloty pro formulář rezervace, nyní rozšířený."""
    def name(self) -> Text: return "validate_appointment_form"

    def validate_appointment_service(self, value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> Dict[Text, Any]:
        """Validuje zadanou službu."""
        if not value:
            dispatcher.utter_message("Jakou službu si přejete rezervovat?")
            return {"appointment_service": None}
        return {"appointment_service": value}

    def validate_appointment_date(self, value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> Dict[Text, Any]:
        """Validuje zadané datum."""
        if not value:
            dispatcher.utter_message("Prosím, zadejte datum, které vám vyhovuje.")
            return {"appointment_date": None}
        return {"appointment_date": value}

    def validate_appointment_time(self, value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> Dict[Text, Any]:
        """Validuje zadaný čas."""
        if not value:
            dispatcher.utter_message("A v kolik hodin?")
            return {"appointment_time": None}
        return {"appointment_time": value}


class ActionBookAppointment(Action):
    """Zpracuje finální žádost o rezervaci a potvrdí ji."""
    def name(self) -> Text: return "action_book_appointment"
    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        service = tracker.get_slot("appointment_service")
        date = tracker.get_slot("appointment_date")
        time = tracker.get_slot("appointment_time")

        dispatcher.utter_message(text=f"Děkuji. Přijala jsem Váš požadavek na rezervaci služby **{service}** na **{date} v {time}**. Brzy se Vám ozveme s potvrzením na kontaktní údaje, které máme k dispozici.")
        return [SlotSet("appointment_service", None), SlotSet("appointment_date", None), SlotSet("appointment_time", None)]


class ActionManageGDPR(Action):
    """Tato akce demonstruje, jak přistupovat k personalizaci v souladu s GDPR."""
    def name(self) -> Text: return "action_manage_gdpr"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        intent_name = tracker.latest_message['intent'].get('name')

        if intent_name == 'request_personalization':
            message = (
                "Abych si mohla pamatovat Vaše preference (např. typ pleti) pro příští návštěvy, "
                "potřebuji Váš souhlas se zpracováním těchto údajů. "
                "Vaše data budou použita výhradně pro vylepšení Vašeho zážitku zde a nebudou sdílena. "
                "Souhlas můžete kdykoliv odvolat napsáním 'zapomeň si mě'. Souhlasíte?"
            )
            buttons = [{"title": "Ano, souhlasím", "payload": "/gdpr_consent_grant"}, {"title": "Ne, děkuji", "payload": "/gdpr_consent_deny"}]
            dispatcher.utter_message(message, buttons=buttons)

        elif intent_name == 'gdpr_consent_grant':
            dispatcher.utter_message("Děkuji za důvěru! Odteď si budu pamatovat Vaše preference.")

        elif intent_name == 'gdpr_consent_deny':
            dispatcher.utter_message("Rozumím. Vaše preference si nebudu ukládat.")

        elif intent_name == 'request_forget_me':
            dispatcher.utter_message("Je mi to líto, ale respektuji Vaše rozhodnutí. Všechny uložené preference byly smazány.")

        return []


class ActionDefaultFallback(Action):
    """Vlastní fallback akce pro případy, kdy si bot není jistý."""
    def name(self) -> Text: return "action_default_fallback"
    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        logger.warning(f"Fallback pro text: '{tracker.latest_message.get('text')}'.")
        dispatcher.utter_message(text="Omlouvám se, tomuto jsem úplně nerozuměla. Mohu Vám pomoci s výběrem produktů, nebo ukázat své možnosti?")
        return []