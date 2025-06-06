import json
import logging
from typing import Any, Text, Dict, List, Optional

from rasa_sdk import Action, Tracker, FormValidationAction
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, ActiveLoop
from rasa_sdk.types import DomainDict

logger = logging.getLogger(__name__)

# --- ZMĚNA START: Načítání části znalostní báze z externího souboru ---
KNOWLEDGE_BASE_FILE_PATH = './data/knowledge_base.json'
PRODUCTS_FILE_PATH = './data/products.json'
BASE_ESHOP_URL = "https://eshop.dermaestetik.cz"

def load_json_file(file_path: Text, description: Text) -> Dict:
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logger.info(f"Soubor '{description}' ('{file_path}') úspěšně načten.")
        return data
    except FileNotFoundError:
        logger.error(f"Soubor '{description}' ('{file_path}') nebyl nalezen.")
    except json.JSONDecodeError as e:
        logger.error(f"Chyba při dekódování JSON souboru '{description}' ('{file_path}'): {e}")
    except Exception as e:
        logger.error(f"Neočekávaná chyba při načítání souboru '{description}' ('{file_path}'): {e}")
    return {} # Vrací prázdný slovník v případě chyby

knowledge_base_data = load_json_file(KNOWLEDGE_BASE_FILE_PATH, "znalostní báze")

# Použití načtených dat, s fallbackem na prázdný seznam, pokud načtení selhalo nebo klíč chybí
KNOWN_BRANDS = knowledge_base_data.get("KNOWN_BRANDS", [])
KNOWN_SKIN_AREAS = knowledge_base_data.get("KNOWN_SKIN_AREAS", [])

# Ostatní KNOWN_... seznamy zatím zůstávají hardcoded
KNOWN_SKIN_TYPES = [
    "suchá", "mastná", "smíšená", "citlivá", "normální",
    "velmi suchá", "problematická", "zralá", "dehydrovaná"
]
KNOWN_PRODUCT_CATEGORIES = [
    "krém", "sérum", "čistič", "čistící gel", "oční krém", "maska", "tonikum",
    "peeling", "spf", "lokální péče", "fluid", "emulze", "tělové mléko",
    "pleťová voda", "make-up", "báze", "krém na ruce", "oční sérum",
    "péče o řasy", "čistící pěna", "čistící olej", "gelový krém", "olejové sérum",
    "micelární voda", "odličovač", "balzám na rty"
]
KNOWN_PRODUCT_ATTRIBUTES = [
    "veganské", "bez parabenů", "s spf", "bez alkoholu", "bez parfemace",
    "s niacinamidem", "s aha/bha", "matující", "intenzivní", "lehký",
    "pro těhotné", "s vitamínem c", "s retinalem", "pro muže", "bez silikonů",
    "nekomedogenní", "bez mýdla", "bez sulfátů (sls/sles)", "s bakuchiolem", "s peptidy",
    "jemný", "s pha kyselinami", "s kyselinou hyaluronovou", "antioxidační", "proti stárnutí", "rozjasňující",
    "stimulující růst",
    "výživný",
    "s kofeinem",
    "proti pigmentaci", 
    "hydratační"
]
KNOWN_SKIN_CONCERNS = [
    "akné", "vrásky", "pigmentace", "póry", "černé tečky", "zarudnutí",
    "hydratace", "dehydratace", "citlivost", "stárnutí", "zpevnění",
    "exfoliace", "mdlá pleť", "tmavé kruhy pod očima", "otoky očí",
    "šupinatá pleť", "růst řas", "růst obočí", "jemné linky", "podráždění",
    "ztráta elasticity", "nerovnoměrný tón pleti", "lesk pleti"
]
# --- ZMĚNA KONEC ---

class ActionRecommendProduct(Action):
    def name(self) -> Text:
        return "action_recommend_product"

    def _normalize_string_value(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, str):
            return value.strip().lower()
        return str(value).strip().lower()

    def _load_products(self, dispatcher: CollectingDispatcher) -> List[Dict[Text, Any]]:
        # Použijeme obecnou funkci pro načítání JSON
        products_data = load_json_file(PRODUCTS_FILE_PATH, "katalog produktů")
        if not products_data: # products_data může být {} pokud load_json_file selže
             dispatcher.utter_message(text="Omlouvám se, momentálně nemohu načíst katalog produktů. Zkuste to prosím později.")
             return []
        if not isinstance(products_data, list): # Zajistíme, že data jsou seznam
            logger.error(f"Katalog produktů ('{PRODUCTS_FILE_PATH}') neobsahuje seznam produktů.")
            dispatcher.utter_message(text="Omlouvám se, v katalogu produktů je technická chyba.")
            return []
        return products_data


    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        logger.info(f"--- Akce ActionRecommendProduct ZAHÁJENA (ID konverzace: {tracker.sender_id}) ---")
        
        slot_skin_type = tracker.get_slot("skin_type")
        slot_skin_concern = tracker.get_slot("skin_concern")
        slot_product_category = tracker.get_slot("product_category")
        slot_product_attribute = tracker.get_slot("product_attribute")
        slot_brand = tracker.get_slot("brand")
        slot_skin_area = tracker.get_slot("skin_area")
        # PŘIDÁNO: Načtení slotu pro preferenci řazení (zatím jen konceptuálně)
        slot_sort_preference = tracker.get_slot("sort_preference") # Tento slot ještě není v domain.yml

        logger.info(f"Aktuální sloty PŘED zpracováním: "
                    f"skin_type={slot_skin_type}, "
                    f"skin_concern={slot_skin_concern}, "
                    f"product_category={slot_product_category}, "
                    f"brand={slot_brand}, "
                    f"product_attribute={slot_product_attribute}, "
                    f"skin_area={slot_skin_area}, "
                    f"sort_preference={slot_sort_preference}") # PŘIDÁNO logování

        products = self._load_products(dispatcher)
        if not products:
            return []

        active_skin_types = [st for st in slot_skin_type if st] if isinstance(slot_skin_type, list) else ([slot_skin_type] if slot_skin_type else [])
        active_skin_concerns = [sc for sc in slot_skin_concern if sc] if isinstance(slot_skin_concern, list) else ([slot_skin_concern] if slot_skin_concern else [])
        active_product_category = self._normalize_string_value(slot_product_category) 
        active_product_attributes = [pa for pa in slot_product_attribute if pa] if isinstance(slot_product_attribute, list) else ([slot_product_attribute] if slot_product_attribute else [])
        active_brand = self._normalize_string_value(slot_brand)
        active_skin_area = self._normalize_string_value(slot_skin_area)

        logger.info(f"Filtruji s (normalizovanými) sloty: "
                    f"skin_type: {active_skin_types}, "
                    f"skin_concern: {active_skin_concerns}, "
                    f"product_category: '{active_product_category}', "
                    f"product_attribute: {active_product_attributes}, "
                    f"brand: '{active_brand}', "
                    f"skin_area: '{active_skin_area}'")

        recommended_products = []
        for product in products:
            product_name_for_debug = product.get('name', f"NEZNÁMÉ ID: {product.get('id', 'N/A')}")
            
            product_skin_types = [self._normalize_string_value(st) for st in product.get("skin_types", []) if st]
            product_skin_concerns = [self._normalize_string_value(sc) for sc in product.get("skin_concerns", []) if sc]
            product_category_value = self._normalize_string_value(product.get("category", ""))
            product_attributes_list = [self._normalize_string_value(attr) for attr in product.get("attributes", []) if attr]
            product_brand_value = self._normalize_string_value(product.get("brand", ""))
            product_skin_areas_list = [self._normalize_string_value(sa) for sa in product.get("skin_areas", []) if sa]

            match_skin_type = not active_skin_types or any(st in product_skin_types for st in active_skin_types)
            match_skin_concern = not active_skin_concerns or any(
                any( (slot_sc and prod_sc) and (slot_sc in prod_sc or prod_sc in slot_sc) for prod_sc in product_skin_concerns)
                for slot_sc in active_skin_concerns
            )
            match_product_category = not active_product_category or active_product_category == product_category_value
            match_product_attributes = not active_product_attributes or all(attr in product_attributes_list for attr in active_product_attributes)
            match_brand = not active_brand or active_brand == product_brand_value
            match_skin_area = not active_skin_area or active_skin_area in product_skin_areas_list

            if match_skin_type and match_skin_concern and match_product_category and match_product_attributes and match_brand and match_skin_area:
                logger.info(f"Produkt '{product_name_for_debug}' ODPOVÍDÁ kritériím.")
                recommended_products.append(product)

        logger.info(f"Celkem nalezeno doporučených produktů: {len(recommended_products)}")

        if recommended_products:
            # ZMĚNA START: Rozšířená logika řazení
            sort_key = "name" # Výchozí řazení
            reverse_sort = False

            if slot_sort_preference == "price_asc":
                sort_key = "price"
                logger.info("Požadováno řazení podle ceny vzestupně.")
            elif slot_sort_preference == "price_desc":
                sort_key = "price"
                reverse_sort = True
                logger.info("Požadováno řazení podle ceny sestupně.")
            elif slot_sort_preference == "name_asc": # Explicitní volba řazení podle jména
                logger.info("Požadováno řazení podle názvu vzestupně.")
            # Pokud slot_sort_preference není nastaven nebo je neznámý, použije se výchozí (podle jména)
            
            if sort_key == "price":
                # Při řazení podle ceny je potřeba ošetřit chybějící cenu (např. dát je na konec)
                recommended_products.sort(
                    key=lambda p: (p.get(sort_key) is None, p.get(sort_key, float('inf' if not reverse_sort else -float('inf')))), 
                    reverse=reverse_sort
                )
            else: # default sort by name
                recommended_products.sort(key=lambda p: self._normalize_string_value(p.get('name', '')), reverse=reverse_sort)
            
            logger.info(f"Doporučené produkty seřazeny podle: '{sort_key}' ({'sestupně' if reverse_sort else 'vzestupně'}).")
            # ZMĚNA KONEC

            intro_parts = []
            if active_brand: intro_parts.append(f"značky '{active_brand}'") 
            if active_product_category: intro_parts.append(f"kategorie '{active_product_category}'")
            if active_skin_types: intro_parts.append(f"pro typ pleti: {', '.join(active_skin_types)}")
            if active_skin_concerns: intro_parts.append(f"řešící problémy: {', '.join(active_skin_concerns)}")
            if active_product_attributes: intro_parts.append(f"s vlastnostmi: {', '.join(active_product_attributes)}")
            if active_skin_area: intro_parts.append(f"pro oblast '{active_skin_area}'")
            
            if intro_parts:
                response_intro = f"Na základě Vašich požadavků ({'; '.join(intro_parts)}) jsem našla tyto produkty:"
            else:
                response_intro = "Zde je několik produktů z naší nabídky, které by Vás mohly zajímat:"
            dispatcher.utter_message(text=response_intro)

            for i, product_data in enumerate(recommended_products[:3]):
                product_name = product_data.get('name', 'Neznámý produkt')
                product_description = product_data.get('description', 'Popis není k dispozici.')
                product_link = product_data.get('link')
                product_price = product_data.get('price')
                message = f"{i+1}. **{product_name}**"
                if product_price:
                    message += f" (cena: {product_price} Kč)" # Cena se nyní zobrazuje, pokud je k dispozici
                message += f": {product_description}"
                
                corrected_link = None
                if product_link:
                    if not product_link.startswith("http"):
                        corrected_link = f"{BASE_ESHOP_URL}/{product_link.lstrip('/')}"
                    else:
                        corrected_link = product_link 
                
                if corrected_link:
                    message += f"\n   Více informací: {corrected_link}"
                
                dispatcher.utter_message(text=message)
                logger.info(f"Doporučen produkt: {product_name}")
            
            if len(recommended_products) > 3:
                dispatcher.utter_message(text=f"Našla jsem celkem {len(recommended_products)} produktů. Zobrazuji první tři. Pokud chcete vidět další nebo upravit vyhledávání, dejte mi vědět!")
            
        else:
            logger.info("Nebyly nalezeny žádné produkty odpovídající kritériím po filtrování.")
            dispatcher.utter_message(text="Omlouvám se, nenašla jsem žádný produkt, který by přesně odpovídal Vašim zadaným kritériím. Můžete zkusit Váš požadavek upravit (například ubrat některá kritéria, nebo zkusit méně specifický dotaz) nebo se podívejte na naši kompletní nabídku na e-shopu DermaEstetik.cz.")

        logger.info(f"--- Akce ActionRecommendProduct DOKONČENA ---")
        return []


class ValidateProductRecommendationForm(FormValidationAction):
    def name(self) -> Text:
        return "validate_product_recommendation_form"

    @staticmethod
    def _normalize_value(value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, str):
            return value.strip().lower()
        return str(value).strip().lower()

    async def _validate_list_slot(
        self,
        slot_name: Text,
        slot_value: Any,
        known_values: Optional[List[Text]], 
        dispatcher: CollectingDispatcher,
        tracker: Tracker, 
        domain: DomainDict, 
    ) -> Dict[Text, Any]:
        if slot_value is None:
            logger.debug(f"Validace '{slot_name}': Hodnota je None, vracím None.")
            return {slot_name: None}

        current_values_from_slot = []
        if isinstance(slot_value, list):
            current_values_from_slot = slot_value
        elif isinstance(slot_value, str):
            temp_values = slot_value.replace(" a ", ",").split(',')
            current_values_from_slot = [v.strip() for v in temp_values if v.strip()]
        else:
            logger.warning(f"Validace '{slot_name}': Neočekávaný typ hodnoty '{type(slot_value)}'. Vracím None.")
            return {slot_name: None}

        if not current_values_from_slot: 
            return {slot_name: None}

        validated_items = []
        unrecognized_items = []
        custom_concerns_extracted = [] 

        for item_str in current_values_from_slot:
            normalized_item = self._normalize_value(item_str)
            if not normalized_item:
                continue
            
            # ZMĚNA START: Použití globálních KNOWN_... seznamů přímo, pokud jsou načteny
            # Toto je relevantní hlavně pro sloty, jejichž KNOWN_... seznamy nebyly externalizovány.
            # Pro externalizované (KNOWN_BRANDS, KNOWN_SKIN_AREAS) se použije 'known_values' předané do metody.
            active_known_values = known_values
            if slot_name == "skin_type": active_known_values = KNOWN_SKIN_TYPES
            elif slot_name == "skin_concern": active_known_values = KNOWN_SKIN_CONCERNS # Pro logování
            elif slot_name == "product_attribute": active_known_values = KNOWN_PRODUCT_ATTRIBUTES
            # Pro KNOWN_BRANDS a KNOWN_SKIN_AREAS se spoléháme na 'known_values' parametr,
            # který bude obsahovat data načtená z JSON.
            # Pro KNOWN_PRODUCT_CATEGORIES se 'known_values' předává do _validate_text_slot.
            # ZMĚNA KONEC

            is_known = active_known_values and normalized_item in active_known_values
            
            if slot_name == "skin_concern": 
                if normalized_item not in validated_items:
                    validated_items.append(normalized_item)
                # Používáme globální KNOWN_SKIN_CONCERNS pro kontrolu, zda je to "nový" concern
                if normalized_item not in KNOWN_SKIN_CONCERNS: 
                    if normalized_item not in custom_concerns_extracted:
                         custom_concerns_extracted.append(normalized_item)
            elif is_known: 
                if normalized_item not in validated_items:
                    validated_items.append(normalized_item)
            elif active_known_values : # Pokud existuje seznam známých hodnot a hodnota v něm není
                 unrecognized_items.append(str(item_str)) 
        
        if custom_concerns_extracted:
            logger.info(f"Validace 'skin_concern': Uživatel zadal tyto problémy, které nejsou v globálním KNOWN_SKIN_CONCERNS: {custom_concerns_extracted}. Byly přijaty pro doporučení.")

        if unrecognized_items: 
            if not validated_items : 
                # ZMĚNA START: Použití active_known_values pro příklady
                example_values = active_known_values[:3] if active_known_values and len(active_known_values) > 2 else (active_known_values if active_known_values else [])
                # ZMĚNA KONEC
                example_text = f"Můžete zkusit například: {', '.join(example_values)}..." if example_values else "Zkuste to prosím znovu."
                
                utter_action = f"utter_ask_{slot_name}"
                if slot_name in domain.get("responses", {}): 
                     dispatcher.utter_message(response=utter_action)
                else:
                     dispatcher.utter_message(
                        text=f"Bohužel nerozumím žádné ze zadaných hodnot pro '{slot_name}': {', '.join(unrecognized_items)}. {example_text}"
                     )
                logger.info(f"Validace '{slot_name}': Nic nerozpoznáno. Vstup: {unrecognized_items}.")
                return {slot_name: None} 
            else: 
                logger.info(f"Validace '{slot_name}': Částečně rozpoznáno. Nerozpoznáno: {unrecognized_items}. Rozpoznáno a použito: {validated_items}")
        
        if not validated_items:
            logger.debug(f"Validace '{slot_name}': Po validaci nezůstaly žádné položky. Vracím None.")
            return {slot_name: None}

        logger.info(f"Validace '{slot_name}': Úspěšně validováno na: {validated_items}")
        return {slot_name: validated_items}

    async def _validate_text_slot(
        self,
        slot_name: Text,
        slot_value: Any,
        known_values: Optional[List[Text]], # Tento parametr se použije pro KNOWN_PRODUCT_CATEGORIES, KNOWN_BRANDS, KNOWN_SKIN_AREAS
        dispatcher: CollectingDispatcher,
        domain: DomainDict, 
    ) -> Dict[Text, Any]:
        normalized_input_value = self._normalize_value(slot_value) 

        if not normalized_input_value:
            logger.debug(f"Validace '{slot_name}': Hodnota je None nebo prázdná po normalizaci. Vracím None.")
            return {slot_name: None}
        
        reset_keywords = ["nevim", "žádný", "zadny", "je mi to jedno", "nezalezi", "cokoliv", "jakykoliv", "nechci", "nepotřebuji", "nepotrebuji", "preskocit", "přeskočit"]
        if normalized_input_value in reset_keywords:
            logger.info(f"Validace '{slot_name}': Slot resetován na None kvůli vstupu '{normalized_input_value}' (uživatel nespecifikuje/nechce/přeskakuje).")
            return {slot_name: None}

        if known_values and normalized_input_value not in known_values:
            for known_val in known_values:
                if normalized_input_value.startswith(known_val) or known_val.startswith(normalized_input_value) or \
                   (len(normalized_input_value) > 3 and normalized_input_value in known_val) or \
                   (len(known_val) > 3 and known_val in normalized_input_value):
                    logger.info(f"Validace '{slot_name}': Nalezena podobná/částečná shoda '{known_val}' pro vstup '{normalized_input_value}'. Používám '{known_val}'.")
                    return {slot_name: known_val}
            
            example_values = known_values[:3] if known_values and len(known_values) > 2 else (known_values if known_values else [])
            example_text = f"Podporované jsou například: {', '.join(example_values)}..." if example_values else "Zkuste to prosím znovu."
            
            utter_action = f"utter_ask_{slot_name}"
            if slot_name in domain.get("responses", {}): 
                 dispatcher.utter_message(response=utter_action)
            else:
                 dispatcher.utter_message(
                    text=f"Hodnotu '{slot_value}' pro '{slot_name}' bohužel neznám. {example_text}"
                 )
            logger.info(f"Validace '{slot_name}': Nerozpoznaná hodnota '{slot_value}' (normalizováno na '{normalized_input_value}'). Není v known_values ani nenalezena podobná.")
            return {slot_name: None}
        
        logger.info(f"Validace '{slot_name}': Úspěšně validováno na: '{normalized_input_value}'")
        return {slot_name: normalized_input_value}

    async def validate_skin_type(
        self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict,
    ) -> Dict[Text, Any]:
        logger.debug(f"Validuji slot 'skin_type' s hodnotou: {slot_value}")
        # Použije globální KNOWN_SKIN_TYPES uvnitř _validate_list_slot
        return await self._validate_list_slot("skin_type", slot_value, KNOWN_SKIN_TYPES, dispatcher, tracker, domain)

    async def validate_skin_concern(
        self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict,
    ) -> Dict[Text, Any]:
        logger.debug(f"Validuji slot 'skin_concern' s hodnotou: {slot_value}")
        # 'None' pro known_values znamená, že _validate_list_slot přijme cokoli, ale použije globální KNOWN_SKIN_CONCERNS pro logování
        return await self._validate_list_slot("skin_concern", slot_value, None, dispatcher, tracker, domain)

    async def validate_product_category(
        self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict,
    ) -> Dict[Text, Any]:
        logger.debug(f"Validuji slot 'product_category' s hodnotou: {slot_value}")
        return await self._validate_text_slot("product_category", slot_value, KNOWN_PRODUCT_CATEGORIES, dispatcher, domain)

    async def validate_product_attribute(
        self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict,
    ) -> Dict[Text, Any]:
        logger.debug(f"Validuji slot 'product_attribute' s hodnotou: {slot_value}")
        # Použije globální KNOWN_PRODUCT_ATTRIBUTES uvnitř _validate_list_slot
        return await self._validate_list_slot("product_attribute", slot_value, KNOWN_PRODUCT_ATTRIBUTES, dispatcher, tracker, domain)

    async def validate_brand(
        self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict,
    ) -> Dict[Text, Any]:
        logger.debug(f"Validuji slot 'brand' s hodnotou: {slot_value}")
        # KNOWN_BRANDS je nyní načítán z JSON a dostupný globálně v tomto modulu
        return await self._validate_text_slot("brand", slot_value, KNOWN_BRANDS, dispatcher, domain)

    async def validate_skin_area(
        self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict,
    ) -> Dict[Text, Any]:
        logger.debug(f"Validuji slot 'skin_area' s hodnotou: {slot_value}")
        # KNOWN_SKIN_AREAS je nyní načítán z JSON a dostupný globálně v tomto modulu
        return await self._validate_text_slot("skin_area", slot_value, KNOWN_SKIN_AREAS, dispatcher, domain)

    async def required_slots(
        self,
        slots_mapped_in_domain: List[Text], 
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Optional[List[Text]]:
        
        form_name = tracker.active_loop.get("name") if tracker.active_loop else None
        base_required_slots = []
        active_domain_for_forms = domain 
        if form_name and active_domain_for_forms.get("forms", {}).get(form_name):
            base_required_slots = active_domain_for_forms.get("forms", {}).get(form_name, {}).get("required_slots", [])
        
        if not base_required_slots: 
             logger.warning(f"Pro formulář '{form_name}' nejsou v domain.yml definovány žádné 'required_slots' nebo je seznam prázdný. Používám fallback: ['skin_type', 'skin_concern']")
             base_required_slots = ["skin_type", "skin_concern"]

        current_required_slots = list(base_required_slots)
        
        skin_concern_values = tracker.get_slot("skin_concern") 
        product_category_value = tracker.get_slot("product_category")
        
        if isinstance(skin_concern_values, list) and "růst řas" in skin_concern_values:
            is_product_category_already_filled = product_category_value is not None
            if not is_product_category_already_filled and "product_category" not in current_required_slots:
                current_required_slots.append("product_category")
                logger.info(f"Dynamicky přidán 'product_category' jako povinný slot kvůli 'růst řas', protože ještě není vyplněn.")
            elif is_product_category_already_filled:
                 logger.info(f"'product_category' je již vyplněn ({product_category_value}), nepřidávám jej znovu jako povinný i přes 'růst řas'.")
            elif "product_category" in current_required_slots:
                 logger.info(f"'product_category' je již mezi explicitně povinnými sloty, neřeším dynamické přidání kvůli 'růst řas'.")
        
        logger.info(f"Metoda required_slots pro formulář '{form_name}' určila tyto povinné sloty: {current_required_slots}")
        return current_required_slots