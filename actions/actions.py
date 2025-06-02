import json
import logging
from typing import Any, Text, Dict, List, Optional

from rasa_sdk import Action, Tracker, FormValidationAction
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, ActiveLoop
from rasa_sdk.types import DomainDict

logger = logging.getLogger(__name__)

# Seznamy známých hodnot pro validaci
# Měly by být synchronizovány s NLU (lookup tables, synonyma) a product_data.json
# Ujistěte se, že tyto seznamy obsahují POUZE normalizované, základní tvary.
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
KNOWN_SKIN_AREAS = [
    "obličej", "oční okolí", "tělo", "ruce", "krk", "dekolt", "záda",
    "lokální použití", "lokty", "kolena", "ramena", "rty", "vlasy", "pokožka hlavy"
]
KNOWN_BRANDS = [
    "medik8", "heliocare", "facevolution", "ukázkováznačka",
    "revitalash", "dermalogica", "la roche-posay", "bioderma"
]
KNOWN_PRODUCT_ATTRIBUTES = [
    "veganské", "bez parabenů", "s spf", "bez alkoholu", "bez parfemace",
    "s niacinamidem", "s aha/bha", "matující", "intenzivní", "lehký",
    "pro těhotné", "s vitamínem c", "s retinalem", "pro muže", "bez silikonů",
    "nekomedogenní", "bez mýdla", "bez sulfátů (sls/sles)", "s bakuchiolem", "s peptidy",
    "jemný", "pha kyseliny", "s kyselinou hyaluronovou", "antioxidační", "proti stárnutí", "rozjasňující"
]

PRODUCTS_FILE_PATH = './data/products.json'

class ActionRecommendProduct(Action):
    def name(self) -> Text:
        return "action_recommend_product"

    def _load_products(self, dispatcher: CollectingDispatcher) -> List[Dict[Text, Any]]:
        try:
            with open(PRODUCTS_FILE_PATH, 'r', encoding='utf-8') as f:
                products = json.load(f)
            logger.info(f"Soubor s produkty '{PRODUCTS_FILE_PATH}' úspěšně načten. Počet produktů: {len(products)}")
            return products
        except FileNotFoundError:
            logger.error(f"Soubor s produkty nebyl nalezen na cestě: {PRODUCTS_FILE_PATH}")
            dispatcher.utter_message(text="Omlouvám se, momentálně nemohu načíst katalog produktů. Zkuste to prosím později.")
            return []
        except json.JSONDecodeError as e:
            logger.error(f"Chyba při dekódování JSON souboru s produkty ({PRODUCTS_FILE_PATH}): {e}")
            dispatcher.utter_message(text="Omlouvám se, v katalogu produktů je technická chyba a nemohu Vám teď poradit.")
            return []
        except Exception as e:
            logger.error(f"Neočekávaná chyba při načítání souboru s produkty: {e}")
            dispatcher.utter_message(text="Omlouvám se, nastala neočekávaná chyba při hledání produktů.")
            return []

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        logger.info(f"--- Akce ActionRecommendProduct ZAHÁJENA (ID konverzace: {tracker.sender_id}) ---")
        logger.info(f"Aktuální sloty PŘED filtrováním: "
                    f"skin_type={tracker.get_slot('skin_type')}, "
                    f"skin_concern={tracker.get_slot('skin_concern')}, "
                    f"product_category={tracker.get_slot('product_category')}, "
                    f"brand={tracker.get_slot('brand')}, "
                    f"product_attribute={tracker.get_slot('product_attribute')}, "
                    f"skin_area={tracker.get_slot('skin_area')}")

        products = self._load_products(dispatcher)
        if not products:
            return self._reset_slots()

        skin_type_slot = tracker.get_slot("skin_type")
        skin_concern_slot = tracker.get_slot("skin_concern")
        product_category_slot = tracker.get_slot("product_category")
        product_attribute_slot = tracker.get_slot("product_attribute")
        brand_slot = tracker.get_slot("brand")
        skin_area_slot = tracker.get_slot("skin_area")

        active_skin_types = skin_type_slot if isinstance(skin_type_slot, list) else []
        active_skin_concerns = skin_concern_slot if isinstance(skin_concern_slot, list) else []
        active_product_category = product_category_slot
        active_product_attributes = product_attribute_slot if isinstance(product_attribute_slot, list) else []
        active_brand = brand_slot
        active_skin_area = skin_area_slot

        logger.info(f"Filtruji s (již validovanými/normalizovanými) sloty: "
                    f"skin_type: {active_skin_types}, "
                    f"skin_concern: {active_skin_concerns}, "
                    f"product_category: '{active_product_category}', "
                    f"product_attribute: {active_product_attributes}, "
                    f"brand: '{active_brand}', "
                    f"skin_area: '{active_skin_area}'")

        recommended_products = []
        for product in products:
            product_name_for_debug = product.get('name', f"NEZNÁMÉ ID: {product.get('id', 'N/A')}")
            product_skin_types = [st.lower() for st in product.get("skin_types", []) if isinstance(st, str)]
            product_skin_concerns = [sc.lower() for sc in product.get("skin_concerns", []) if isinstance(sc, str)]
            product_category_value = product.get("category", "").lower()
            product_attributes_list = [attr.lower() for attr in product.get("attributes", []) if isinstance(attr, str)]
            product_brand_value = product.get("brand", "").lower()
            product_skin_areas_list = [sa.lower() for sa in product.get("skin_areas", []) if isinstance(sa, str)]

            match_skin_type = not active_skin_types or any(st in product_skin_types for st in active_skin_types)
            match_skin_concern = not active_skin_concerns or any(
                any(slot_sc in prod_sc or prod_sc in slot_sc for prod_sc in product_skin_concerns)
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
            intro_parts = []
            if brand_slot: intro_parts.append(f"značky '{brand_slot}'")
            if product_category_slot: intro_parts.append(f"kategorie '{product_category_slot}'")
            if skin_type_slot: intro_parts.append(f"pro typ pleti: {', '.join(skin_type_slot)}")
            if skin_concern_slot: intro_parts.append(f"řešící problémy: {', '.join(skin_concern_slot)}")
            if product_attribute_slot: intro_parts.append(f"s vlastnostmi: {', '.join(product_attribute_slot)}")
            if skin_area_slot: intro_parts.append(f"pro oblast '{skin_area_slot}'")
            
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
                    message += f" (cena: {product_price} Kč)"
                message += f": {product_description}"
                if product_link:
                    corrected_link = product_link.replace("www.vas-eshop.cz", "eshop.dermaestetik.cz")
                    message += f"\n   Více informací: {corrected_link}"
                dispatcher.utter_message(text=message)
                logger.info(f"Doporučen produkt: {product_name}")
            
            if len(recommended_products) > 3:
                dispatcher.utter_message(text=f"Našla jsem celkem {len(recommended_products)} produktů. Zobrazuji první tři. Pokud chcete vidět další nebo upravit vyhledávání, dejte mi vědět!")
            
            # Odebráno dispatcher.utter_message(response="utter_anything_else") odsud, bude řešeno v příbězích/pravidlech
        else:
            logger.info("Nebyly nalezeny žádné produkty odpovídající kritériím po filtrování.")
            dispatcher.utter_message(text="Omlouvám se, nenašla jsem žádný produkt, který by přesně odpovídal Vašim zadaným kritériím. Můžete zkusit Váš požadavek upravit (například ubrat některá kritéria) nebo se podívejte na naši kompletní nabídku na e-shopu DermaEstetik.cz.")
            # Odebráno dispatcher.utter_message(response="utter_anything_else") odsud

        logger.info(f"--- Akce ActionRecommendProduct DOKONČENA ---")
        # Resetování slotů by mělo být součástí logiky formuláře, ne nutně této akce,
        # pokud chceme, aby si uživatel mohl upravit kritéria.
        # Prozatím ponecháme reset, ale zvažte, zda je to žádoucí chování.
        # Pokud se sloty resetují zde, příběh musí počítat s tím, že po action_recommend_product jsou sloty None.
        # return self._reset_slots()
        # Prozatím nebudeme resetovat sloty zde, aby je mohl uživatel případně upravit.
        # Reset by měl být spíše součástí nového spuštění formuláře nebo explicitní akce.
        return [] # Akce končí, sloty zůstávají pro případné další upřesnění

    def _reset_slots(self) -> List[Dict[Text, Any]]: # Tato metoda se nyní nepoužívá v run()
        slots_to_reset = [
            "skin_type", "skin_concern", "product_category",
            "product_attribute", "brand", "skin_area"
        ]
        logger.info(f"Metoda _reset_slots volána pro: {', '.join(slots_to_reset)}")
        return [SlotSet(slot, None) for slot in slots_to_reset]


class ValidateProductRecommendationForm(FormValidationAction):
    def name(self) -> Text:
        return "validate_product_recommendation_form"

    @staticmethod
    def _normalize_value(value: Any) -> Optional[str]:
        if value is None:
            return None
        # Odstranění diakritiky před převodem na malá písmena může pomoci s konzistencí
        # import unicodedata
        # if isinstance(value, str):
        #     value_no_diacritics = ''.join(c for c in unicodedata.normalize('NFD', value) if unicodedata.category(c) != 'Mn')
        #     return value_no_diacritics.strip().lower()
        # return str(value).strip().lower()
        # Prozatím ponecháme jednodušší normalizaci, ale diakritika je důležitá pro češtinu.
        # NLU by mělo zvládnout synonyma s/bez diakritiky.
        if isinstance(value, str):
            return value.strip().lower()
        return str(value).strip().lower()


    async def _validate_list_slot(
        self,
        slot_name: Text,
        slot_value: Any,
        known_values: Optional[List[Text]],
        dispatcher: CollectingDispatcher,
    ) -> Dict[Text, Any]:
        if slot_value is None:
            logger.debug(f"Validace '{slot_name}': Hodnota je None, vracím None.")
            return {slot_name: None}

        current_values_from_slot = []
        if isinstance(slot_value, list):
            current_values_from_slot = slot_value
        elif isinstance(slot_value, str):
            current_values_from_slot = [slot_value]
        else:
            logger.warning(f"Validace '{slot_name}': Neočekávaný typ hodnoty '{type(slot_value)}'. Vracím None.")
            return {slot_name: None}

        validated_items = []
        unrecognized_items = []

        for item_str in current_values_from_slot:
            normalized_item = self._normalize_value(item_str)
            if not normalized_item:
                continue
            
            # Pro skin_concern nevalidujeme proti seznamu, přijmeme cokoliv (po normalizaci)
            if slot_name == "skin_concern" or (known_values and normalized_item in known_values):
                if normalized_item not in validated_items:
                    validated_items.append(normalized_item)
            elif known_values: # Pouze pokud known_values existují a hodnota v nich není
                 unrecognized_items.append(str(item_str))
            # else: # Pokud known_values neexistují (kromě skin_concern), a není to ani skin_concern, taky je to OK? To by nemělo nastat.
                # validated_items.append(normalized_item) # Toto by přijalo cokoliv, pokud known_values nejsou definovány

        if unrecognized_items:
            if not validated_items : # Pokud NENÍ nic rozpoznáno a VŠECHNO je nerozpoznané
                example_text = f"Můžete zkusit například: {', '.join(known_values[:3])}..." if known_values and len(known_values) > 0 else "Zkuste to prosím znovu."
                dispatcher.utter_message(
                    text=f"Bohužel nerozumím žádné ze zadaných hodnot pro '{slot_name}': {', '.join(unrecognized_items)}. {example_text}"
                )
                logger.info(f"Validace '{slot_name}': Nic nerozpoznáno. Vstup: {unrecognized_items}.")
                return {slot_name: None} # Zamítnutí, pokud nic nebylo validní
            # else: # Pokud je něco rozpoznáno a něco ne, můžeme se rozhodnout neposílat zprávu, aby to nebylo moc ukecané
            #     logger.info(f"Validace '{slot_name}': Částečně rozpoznáno. Nerozpoznáno: {unrecognized_items}. Rozpoznáno: {validated_items}")
        
        if not validated_items:
            logger.debug(f"Validace '{slot_name}': Po validaci nezůstaly žádné položky (např. prázdný vstup). Vracím None.")
            return {slot_name: None}

        logger.info(f"Validace '{slot_name}': Úspěšně validováno na: {validated_items}")
        return {slot_name: validated_items}


    async def _validate_text_slot(
        self,
        slot_name: Text,
        slot_value: Any,
        known_values: Optional[List[Text]],
        dispatcher: CollectingDispatcher,
    ) -> Dict[Text, Any]:
        # NLU by mělo pomocí synonym (např. "krémem" -> "krém") poslat již normalizovanou hodnotu.
        # Tato validace pak ověří, zda je tato normalizovaná hodnota v seznamu známých.
        
        # Normalizujeme hodnotu, kterou jsme dostali (mohla by být ještě nenormalizovaná, pokud NLU selže nebo synonymum chybí)
        normalized_input_value = self._normalize_value(slot_value) 

        if not normalized_input_value:
            logger.debug(f"Validace '{slot_name}': Hodnota je None nebo prázdná po normalizaci. Vracím None.")
            return {slot_name: None}
        
        if normalized_input_value in ["nevim", "žádný", "zadny", "je mi to jedno", "nezalezi", "cokoliv", "jakykoliv"]:
            logger.info(f"Validace '{slot_name}': Slot resetován na None kvůli vstupu '{normalized_input_value}' (uživatel nespecifikuje).")
            return {slot_name: None}

        if known_values and normalized_input_value not in known_values:
            example_text = f"Podporované jsou například: {', '.join(known_values[:3])}..." if known_values and len(known_values) > 0 else "Zkuste to prosím znovu."
            dispatcher.utter_message(
                text=f"Hodnotu '{slot_value}' pro '{slot_name}' bohužel neznám. {example_text}"
            )
            logger.info(f"Validace '{slot_name}': Nerozpoznaná hodnota '{slot_value}' (normalizováno na '{normalized_input_value}'). Není v known_values.")
            return {slot_name: None}
        
        logger.info(f"Validace '{slot_name}': Úspěšně validováno na: '{normalized_input_value}'")
        return {slot_name: normalized_input_value}

    async def validate_skin_type(
        self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict,
    ) -> Dict[Text, Any]:
        logger.debug(f"Validuji slot 'skin_type' s hodnotou: {slot_value}")
        return await self._validate_list_slot("skin_type", slot_value, KNOWN_SKIN_TYPES, dispatcher)

    async def validate_skin_concern(
        self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict,
    ) -> Dict[Text, Any]:
        logger.debug(f"Validuji slot 'skin_concern' s hodnotou: {slot_value}")
        # Pro skin_concern nevalidujeme proti pevnému seznamu, přijmeme cokoliv (po normalizaci)
        return await self._validate_list_slot("skin_concern", slot_value, None, dispatcher)

    async def validate_product_category(
        self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict,
    ) -> Dict[Text, Any]:
        logger.debug(f"Validuji slot 'product_category' s hodnotou: {slot_value}")
        # NLU by mělo z "krémem" udělat "krém" díky synonymu.
        # Tato funkce pak ověří, zda "krém" je v KNOWN_PRODUCT_CATEGORIES.
        # Pokud NLU pošle "krémem" a to není v KNOWN_PRODUCT_CATEGORIES, vrátí se None.
        return await self._validate_text_slot("product_category", slot_value, KNOWN_PRODUCT_CATEGORIES, dispatcher)

    async def validate_product_attribute(
        self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict,
    ) -> Dict[Text, Any]:
        logger.debug(f"Validuji slot 'product_attribute' s hodnotou: {slot_value}")
        return await self._validate_list_slot("product_attribute", slot_value, KNOWN_PRODUCT_ATTRIBUTES, dispatcher)

    async def validate_brand(
        self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict,
    ) -> Dict[Text, Any]:
        logger.debug(f"Validuji slot 'brand' s hodnotou: {slot_value}")
        return await self._validate_text_slot("brand", slot_value, KNOWN_BRANDS, dispatcher)

    async def validate_skin_area(
        self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict,
    ) -> Dict[Text, Any]:
        logger.debug(f"Validuji slot 'skin_area' s hodnotou: {slot_value}")
        return await self._validate_text_slot("skin_area", slot_value, KNOWN_SKIN_AREAS, dispatcher)

    async def required_slots(
        self,
        slots_mapped_in_domain: List[Text],
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Optional[List[Text]]:
        form_name = self.form_name()
        form_definition = domain.get("forms", {}).get(form_name, {})
        base_required_slots = form_definition.get("required_slots", [])
        
        if not base_required_slots:
             logger.warning(f"Pro formulář '{form_name}' nejsou v domain.yml definovány žádné 'required_slots'. Používám fallback: ['skin_type', 'skin_concern']")
             base_required_slots = ["skin_type", "skin_concern"]

        current_required_slots = list(base_required_slots)
        skin_concern_values = tracker.get_slot("skin_concern") # Toto by měla být již validovaná hodnota
        
        # Pokud je skin_concern "růst řas", přidáme product_category jako povinný, pokud ještě není vyplněn.
        if isinstance(skin_concern_values, list) and "růst řas" in skin_concern_values:
            # Pokud 'product_category' ještě není vyplněn A není již v seznamu povinných
            if tracker.get_slot("product_category") is None and "product_category" not in current_required_slots:
                current_required_slots.append("product_category")
                logger.info(f"Dynamicky přidán 'product_category' jako povinný slot kvůli 'růst řas'.")
        
        logger.info(f"Metoda required_slots pro formulář '{form_name}' určila tyto povinné sloty: {current_required_slots}")
        return current_required_slots
