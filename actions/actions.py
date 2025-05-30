import json
from typing import Any, Text, Dict, List, Optional

from rasa_sdk import Action, Tracker, FormValidationAction
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
from rasa_sdk.types import DomainDict

# Seznamy známých hodnot pro validaci
# Tyto seznamy by měly odpovídat hodnotám, které očekáváš a které máš v NLU/lookup tables
KNOWN_SKIN_TYPES = [
    "suchá", "mastná", "smíšená", "citlivá", "normální",
    "velmi suchá", "problematická", "zralá", "dehydrovaná"
]
KNOWN_PRODUCT_CATEGORIES = [
    "krém", "sérum", "čistič", "čistící gel", "oční krém", "maska", "tonikum",
    "peeling", "spf", "lokální péče", "fluid", "emulze", "tělové mléko",
    "pleťová voda", "make-up", "báze", "krém na ruce", "oční sérum",
    "péče o řasy", "čistící pěna", "čistící olej", "gelový krém", "olejové sérum"
]
KNOWN_SKIN_AREAS = [
    "obličej", "oční okolí", "tělo", "ruce", "krk", "dekolt", "záda",
    "lokální použití", "lokty", "kolena", "ramena"
]
KNOWN_BRANDS = [ # Pokud máš jen pár hlavních značek, doplň si je
    "medik8", "heliocare", "facevolution" # Příklad
]
KNOWN_PRODUCT_ATTRIBUTES = [ # Základní atributy, můžeš rozšířit
    "veganské", "bez parabenů", "s spf", "bez alkoholu", "bez parfemace",
    "s niacinamidem", "s aha/bha", "matující", "intenzivní", "lehký",
    "pro těhotné", "s vitamínem c", "s retinalem", "pro muže", "bez silikonů",
    "nekomedogenní", "bez mýdla", "bez sulfátů (sls/sles)", "s bakuchiolem", "s peptidy",
    "jemný"
]


class ActionRecommendProduct(Action):
    """
    Vlastní akce pro doporučení produktů na základě uživatelem poskytnutých slotů.
    Načte data o produktech z JSON souboru a filtruje produkty
    odpovídající kritériím ze slotů.
    """

    def name(self) -> Text:
        """Unikátní identifikátor akce."""
        return "action_recommend_product"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        """
        Spustí akci.
        1. Načte data o produktech.
        2. Získá hodnoty slotů z trackeru.
        3. Filtruje produkty na základě hodnot slotů.
        4. Odešle uživateli zprávu s doporučeními nebo fallback.
        5. Resetuje sloty.
        """

        print("---------------------------------------------------------------------------")
        print(f"!!! Akce ActionRecommendProduct byla ZAVOLÁNA (ID konverzace: {tracker.sender_id}) !!!")
        print("---------------------------------------------------------------------------")

        products_file_path = './data/products.json' # Ujisti se, že cesta je správná vzhledem k místu spuštění Action Serveru
        products = []

        try:
            with open(products_file_path, 'r', encoding='utf-8') as f:
                products = json.load(f)
            print(f"INFO: Soubor s produkty '{products_file_path}' úspěšně načten. Počet produktů: {len(products)}")
        except FileNotFoundError:
            print(f"CHYBA: Soubor s produkty nebyl nalezen na cestě: {products_file_path}")
            dispatcher.utter_message(text="Omlouvám se, momentálně nemohu načíst katalog produktů. Zkuste to prosím později.")
            return [SlotSet(s, None) for s in ["skin_type", "skin_concern", "product_category", "product_attribute", "brand", "skin_area"]]
        except json.JSONDecodeError:
            print(f"CHYBA: V souboru s produkty ({products_file_path}) je chyba (není validní JSON) a nelze ho zpracovat.")
            dispatcher.utter_message(text="Omlouvám se, v katalogu produktů je technická chyba a nemohu Vám teď poradit.")
            return [SlotSet(s, None) for s in ["skin_type", "skin_concern", "product_category", "product_attribute", "brand", "skin_area"]]
        except Exception as e:
            print(f"CHYBA: Neočekávaná chyba při načítání souboru s produkty: {e}")
            dispatcher.utter_message(text="Omlouvám se, nastala neočekávaná chyba při hledání produktů.")
            return [SlotSet(s, None) for s in ["skin_type", "skin_concern", "product_category", "product_attribute", "brand", "skin_area"]]

        # Získání původních hodnot slotů pro zobrazení uživateli
        skin_type_slot_orig = tracker.get_slot("skin_type")
        skin_concern_slot_orig = tracker.get_slot("skin_concern")
        product_category_slot_orig = tracker.get_slot("product_category")
        product_attribute_slot_orig = tracker.get_slot("product_attribute")
        brand_slot_orig = tracker.get_slot("brand")
        skin_area_slot_orig = tracker.get_slot("skin_area")

        # Pro filtrování používáme normalizované hodnoty (malá písmena, seznamy)
        active_skin_types = [st.lower() for st in skin_type_slot_orig if isinstance(st, str)] if isinstance(skin_type_slot_orig, list) else []
        active_skin_concerns = [sc.lower() for sc in skin_concern_slot_orig if isinstance(sc, str)] if isinstance(skin_concern_slot_orig, list) else []
        active_product_category = product_category_slot_orig.lower() if isinstance(product_category_slot_orig, str) else None
        active_product_attributes = [attr.lower() for attr in product_attribute_slot_orig if isinstance(attr, str)] if isinstance(product_attribute_slot_orig, list) else []
        active_brand = brand_slot_orig.lower() if isinstance(brand_slot_orig, str) else None
        active_skin_area = skin_area_slot_orig.lower() if isinstance(skin_area_slot_orig, str) else None

        print(f"INFO (ActionRecommendProduct): Filtruji s normalizovanými sloty -> "
              f"skin_type: {active_skin_types}, "
              f"skin_concern: {active_skin_concerns}, "
              f"product_category: '{active_product_category}', "
              f"product_attribute: {active_product_attributes}, "
              f"brand: '{active_brand}', "
              f"skin_area: '{active_skin_area}'")

        recommended_products = []

        if not products:
            print("VAROVÁNÍ (ActionRecommendProduct): Seznam produktů je prázdný po načtení JSONu.")
            dispatcher.utter_message(text="Omlouvám se, momentálně nemáme v nabídce žádné produkty k doporučení.")
            return [SlotSet(s, None) for s in ["skin_type", "skin_concern", "product_category", "product_attribute", "brand", "skin_area"]]

        for product in products:
            product_name_for_debug = product.get('name', f"NEZNÁMÉ ID: {product.get('id', 'N/A')}")

            # Normalizace dat produktu pro porovnání
            product_skin_types = [st.lower() for st in product.get("skin_types", []) if isinstance(st, str)]
            product_skin_concerns = [sc.lower() for sc in product.get("skin_concerns", []) if isinstance(sc, str)]
            product_category_value = product.get("category", "").lower()
            product_attributes_list = [attr.lower() for attr in product.get("attributes", []) if isinstance(attr, str)]
            product_brand_value = product.get("brand", "").lower()
            product_skin_areas_list = [sa.lower() for sa in product.get("skin_areas", []) if isinstance(sa, str)]

            # Logika shody
            # Pokud slot není aktivní (None nebo prázdný list), kritérium se ignoruje (považuje za shodu)
            match_skin_type = not active_skin_types or any(st in product_skin_types for st in active_skin_types)
            
            match_skin_concern = not active_skin_concerns or any(
                any(p_concern_item in slot_concern_item or slot_concern_item in p_concern_item for p_concern_item in product_skin_concerns)
                for slot_concern_item in active_skin_concerns
            )
            
            match_product_category = not active_product_category or active_product_category == product_category_value
            
            # Pro atributy musí produkt obsahovat VŠECHNY atributy specifikované uživatelem
            match_product_attributes = not active_product_attributes or all(attr in product_attributes_list for attr in active_product_attributes)
            
            match_brand = not active_brand or active_brand == product_brand_value
            
            match_skin_area = not active_skin_area or active_skin_area in product_skin_areas_list

            if match_skin_type and match_skin_concern and match_product_category and match_product_attributes and match_brand and match_skin_area:
                print(f"INFO (ActionRecommendProduct): Produkt '{product_name_for_debug}' ODPOVÍDÁ kritériím.")
                recommended_products.append(product)
            # else:
            #     print(f"DEBUG: Produkt '{product_name_for_debug}' NEODPOVÍDÁ. Shody -> skin_type: {match_skin_type}, skin_concern: {match_skin_concern}, category: {match_product_category}, attributes: {match_product_attributes}, brand: {match_brand}, skin_area: {match_skin_area}")


        print(f"INFO (ActionRecommendProduct): Celkem nalezeno doporučených produktů: {len(recommended_products)}")

        if recommended_products:
            response_intro_parts = []
            # Pro zobrazení použijeme původní (ne-normalizované) hodnoty slotů, pokud jsou dostupné
            if brand_slot_orig: response_intro_parts.append(f"značky '{brand_slot_orig}'")
            if product_category_slot_orig: response_intro_parts.append(f"kategorie '{product_category_slot_orig}'")
            if skin_type_slot_orig: response_intro_parts.append(f"pro typy pleti: {', '.join(skin_type_slot_orig)}")
            if skin_concern_slot_orig: response_intro_parts.append(f"řešící problémy: {', '.join(skin_concern_slot_orig)}")
            if product_attribute_slot_orig: response_intro_parts.append(f"s vlastnostmi: {', '.join(product_attribute_slot_orig)}")
            if skin_area_slot_orig: response_intro_parts.append(f"pro oblast '{skin_area_slot_orig}'")

            if response_intro_parts:
                response_intro = f"Pro Vaše požadavky ({'; '.join(response_intro_parts)}) bych Vám mohla doporučit:"
            else:
                response_intro = "Na základě Vašeho dotazu bych Vám mohla nabídnout tyto produkty:" # Obecnější, pokud nejsou specifikovány žádné filtry
            dispatcher.utter_message(text=response_intro)

            for i, product_data in enumerate(recommended_products[:3]): # Zobrazíme max 3 produkty
                product_name = product_data.get('name', 'Neznámý produkt')
                product_description = product_data.get('description', 'Popis není k dispozici.')
                product_link = product_data.get('link') # Odkaz na produkt, pokud existuje
                
                message = f"{i+1}. **{product_name}**: {product_description}"
                if product_link:
                    message += f"\n   Více zde: {product_link}"
                dispatcher.utter_message(text=message)
                print(f"INFO (ActionRecommendProduct): Doporučen produkt: {product_name}")
            
            if len(recommended_products) > 3:
                dispatcher.utter_message(text=f"Našla jsem celkem {len(recommended_products)} produktů. Zobrazuji první tři. Pokud chcete vidět další nebo upravit vyhledávání, dejte mi vědět!")
            # Není potřeba elif not recommended_products zde, protože to je pokryto vnějším else

        else: # Pokud nebyly nalezeny žádné produkty po filtrování
            print("INFO (ActionRecommendProduct): Nebyly nalezeny žádné produkty odpovídající kritériím po filtrování.")
            dispatcher.utter_message(text="Omlouvám se, nenašla jsem žádný produkt, který by přesně odpovídal Vašemu požadavku. Můžete zkusit upřesnit, co hledáte, nebo se podívejte na naši kompletní nabídku na e-shopu.")
        
        print("---------------------------------------------------------------------------")
        print("!!! Akce ActionRecommendProduct DOKONČENA !!!")
        print("---------------------------------------------------------------------------")
        
        # Resetování všech relevantních slotů po dokončení akce
        return [
            SlotSet("skin_type", None), 
            SlotSet("skin_concern", None), 
            SlotSet("product_category", None),
            SlotSet("product_attribute", None),
            SlotSet("brand", None),
            SlotSet("skin_area", None) 
        ]

class ValidateProductRecommendationForm(FormValidationAction):
    """Validuje sloty formuláře product_recommendation_form."""

    def name(self) -> Text:
        """Unikátní identifikátor validační akce formuláře."""
        return "validate_product_recommendation_form"

    @staticmethod
    def _normalize_value(value: Any) -> Optional[str]:
        """Normalizuje hodnotu na string a malá písmena, pokud je to možné."""
        if isinstance(value, str):
            return value.strip().lower()
        return None

    async def _validate_generic_list_slot(
        self,
        slot_name: Text,
        slot_value: Any,
        known_values: Optional[List[Text]],
        dispatcher: CollectingDispatcher,
    ) -> Dict[Text, Any]:
        """Obecná validační metoda pro sloty typu list."""
        if slot_value is None:
            return {slot_name: None}

        # Pokud NLU vrátilo jeden string (což by nemělo pro listový slot, ale pro jistotu), převeď ho na list
        current_values = []
        if isinstance(slot_value, list):
            current_values = slot_value
        elif isinstance(slot_value, str):
            # Pokud je to string, předpokládáme, že to je jedna hodnota pro list
            # (např. pokud NLU extrahovalo entitu jako string místo listu)
            normalized_single = self._normalize_value(slot_value)
            if normalized_single:
                current_values = [normalized_single]
            else: # Prázdný nebo nevalidní string
                # dispatcher.utter_message(text=f"Prosím, zadejte platné hodnoty pro '{slot_name}'.")
                return {slot_name: None} # Nebo vrať původní slot_value, pokud to má zpracovat FormPolicy jinak
        else: # Jiný nečekaný typ
            dispatcher.utter_message(text=f"Obdržela jsem nečekaný formát pro '{slot_name}'. Zkuste to prosím znovu.")
            return {slot_name: None}
        
        validated_items = []
        unrecognized_items = []

        for item in current_values:
            normalized_item = self._normalize_value(item) # Normalizujeme každou položku
            if not normalized_item: # Přeskoč prázdné nebo nevalidní položky
                continue
            
            if known_values and normalized_item not in known_values:
                unrecognized_items.append(str(item)) # Ulož původní hodnotu pro zprávu
            else:
                # I když jsou known_values None (např. pro skin_concern), ukládáme normalizovanou hodnotu
                validated_items.append(normalized_item) 

        if unrecognized_items:
            if validated_items:
                dispatcher.utter_message(
                    text=f"Některým zadaným hodnotám pro '{slot_name}' jsem nerozuměla: {', '.join(unrecognized_items)}. "
                         f"Pokračuji s rozpoznanými: {', '.join(validated_items)}."
                )
            else:
                dispatcher.utter_message(
                    text=f"Bohužel nerozumím žádné ze zadaných hodnot pro '{slot_name}': {', '.join(unrecognized_items)}. "
                         f"Zkuste to prosím znovu s podporovanými hodnotami."
                )
                return {slot_name: None}
        
        if not validated_items: # Pokud po všem čištění nic nezbylo
            # dispatcher.utter_message(text=f"Prosím, zadejte alespoň jednu platnou hodnotu pro '{slot_name}'.")
            return {slot_name: None}

        print(f"VALIDATE_FORM: Slot '{slot_name}' validován na: {validated_items}")
        return {slot_name: validated_items}


    async def _validate_generic_text_slot(
        self,
        slot_name: Text,
        slot_value: Any,
        known_values: Optional[List[Text]],
        dispatcher: CollectingDispatcher,
    ) -> Dict[Text, Any]:
        """Obecná validační metoda pro sloty typu text."""
        normalized_value = self._normalize_value(slot_value)

        if not normalized_value: # Pokud je None nebo prázdný string po normalizaci
            return {slot_name: None}
        
        # Umožní uživateli explicitně říct "žádný" nebo "nevím" pro vyčištění slotu
        if normalized_value in ["none", "nevim", "žádný", "zadny"]:
            print(f"VALIDATE_FORM: Slot '{slot_name}' resetován na None kvůli vstupu '{normalized_value}'.")
            return {slot_name: None}

        if known_values and normalized_value not in known_values:
            dispatcher.utter_message(
                text=f"Bohužel hodnotu '{slot_value}' pro '{slot_name}' neznám. "
                     f"Zkuste to prosím znovu."
                     # Můžeš zvážit výpis známých hodnot, pokud jich není příliš mnoho
                     # f" Podporované hodnoty jsou např.: {', '.join(known_values[:3])}..."
            )
            return {slot_name: None}
        
        print(f"VALIDATE_FORM: Slot '{slot_name}' validován na: '{normalized_value}'")
        return {slot_name: normalized_value} # Vracíme normalizovanou hodnotu

    async def validate_skin_type(
        self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict,
    ) -> Dict[Text, Any]:
        return await self._validate_generic_list_slot("skin_type", slot_value, KNOWN_SKIN_TYPES, dispatcher)

    async def validate_skin_concern(
        self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict,
    ) -> Dict[Text, Any]:
        # Pro skin_concern nemusíme mít pevný seznam známých hodnot, protože může být volnější
        return await self._validate_generic_list_slot("skin_concern", slot_value, None, dispatcher)

    async def validate_product_category(
        self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict,
    ) -> Dict[Text, Any]:
        return await self._validate_generic_text_slot("product_category", slot_value, KNOWN_PRODUCT_CATEGORIES, dispatcher)

    async def validate_product_attribute(
        self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict,
    ) -> Dict[Text, Any]:
        return await self._validate_generic_list_slot("product_attribute", slot_value, KNOWN_PRODUCT_ATTRIBUTES, dispatcher)

    async def validate_brand(
        self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict,
    ) -> Dict[Text, Any]:
        return await self._validate_generic_text_slot("brand", slot_value, KNOWN_BRANDS, dispatcher)

    async def validate_skin_area(
        self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict,
    ) -> Dict[Text, Any]:
        return await self._validate_generic_text_slot("skin_area", slot_value, KNOWN_SKIN_AREAS, dispatcher)

    async def required_slots(
        self,
        slots_mapped_in_domain: List[Text], # Seznam všech slotů, které může formulář vyplnit (z domain.yml)
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict, # Celá načtená doména
    ) -> List[Text]:
        """Dynamicky určuje, které sloty jsou povinné."""
        
        # Získáme definici formuláře z domény, abychom znali původně povinné sloty
        form_name = self.form_name() # Název aktuálního formuláře
        form_definition = domain.get("forms", {}).get(form_name, {})
        
        # Získáme sloty definované jako 'required_slots' v domain.yml pro tento formulář
        # Pokud v domain.yml nejsou 'required_slots' pro formulář, použijeme prázdný seznam jako základ
        base_required_slots_from_domain = form_definition.get("required_slots", [])
        
        # Pokud by se náhodou stalo, že v domain.yml nejsou žádné, můžeme mít fallback
        # nebo se spolehnout, že FormPolicy bude vyžadovat alespoň jeden, pokud je formulář aktivován.
        # Pro robustnost je lepší mít základní povinné sloty definované v domain.yml.
        # Pokud base_required_slots_from_domain je prázdný, můžeme použít výchozí:
        if not base_required_slots_from_domain:
             print(f"VAROVÁNÍ (required_slots): Pro formulář '{form_name}' nejsou v domain.yml definovány žádné 'required_slots'. Používám fallback: ['skin_type', 'skin_concern']")
             base_required_slots_from_domain = ["skin_type", "skin_concern"]

        current_required_slots = list(base_required_slots_from_domain) # Vytvoříme kopii pro modifikaci
        
        skin_concern_values = tracker.get_slot("skin_concern") # Získáme aktuální hodnotu slotu
        
        # Příklad dynamické logiky: Pokud je problém "růst řas", udělej "kategorii produktu" povinnou.
        if isinstance(skin_concern_values, list):
            # Normalizujeme hodnoty ze slotu pro porovnání
            normalized_skin_concerns = [sc.lower() for sc in skin_concern_values if isinstance(sc, str)]
            if "růst řas" in normalized_skin_concerns:
                # Pokud product_category ještě není vyplněn A není mezi aktuálně povinnými
                if tracker.get_slot("product_category") is None and "product_category" not in current_required_slots:
                    current_required_slots.append("product_category")
                    print(f"VALIDATE_FORM: Dynamicky přidán 'product_category' jako povinný slot kvůli 'růst řas'.")
        
        print(f"VALIDATE_FORM: Metoda required_slots určila tyto povinné sloty pro formulář '{form_name}': {current_required_slots}")
        # FormPolicy se sama postará o to, aby se zeptala na ty z tohoto seznamu, které ještě nejsou vyplněny,
        # v pořadí, v jakém jsou v tomto vráceném seznamu.
        return current_required_slots