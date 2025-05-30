import json
from typing import Any, Text, Dict, List

from rasa_sdk import Action, Tracker, FormValidationAction
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
from rasa_sdk.types import DomainDict

class ActionRecommendProduct(Action):
    """
    Custom action to recommend products based on user-provided slots.
    It loads product data from a JSON file and filters products
    matching the criteria from the slots.
    """

    def name(self) -> Text:
        """Unique identifier of the action."""
        return "action_recommend_product"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        """
        Executes the action.
        1. Loads product data.
        2. Retrieves slot values from the tracker.
        3. Filters products based on slot values.
        4. Sends a message to the user with recommendations or a fallback.
        5. Resets the slots (if this action is a form submit action).
        """

        print("---------------------------------------------------------------------------")
        print(f"!!! Akce ActionRecommendProduct byla ZAVOLÁNA (ID konverzace: {tracker.sender_id}) !!!")
        print("---------------------------------------------------------------------------")

        products_file_path = './data/products.json'
        products = [] # Initialize products as an empty list

        # --- 1. Načtení produktů z JSON souboru s ošetřením chyb ---
        try:
            with open(products_file_path, 'r', encoding='utf-8') as f:
                products = json.load(f)
            print(f"INFO: Soubor s produkty '{products_file_path}' úspěšně načten. Počet produktů: {len(products)}")
        except FileNotFoundError:
            print(f"CHYBA: Soubor s produkty nebyl nalezen na cestě: {products_file_path}")
            dispatcher.utter_message(text="Omlouvám se, momentálně nemohu načíst katalog produktů.")
            return [SlotSet(s, None) for s in ["skin_type", "skin_concern", "product_category", "product_attribute", "brand", "skin_area"]]
        except json.JSONDecodeError:
            print(f"CHYBA: V souboru s produkty ({products_file_path}) je chyba (není validní JSON) a nelze ho zpracovat.")
            dispatcher.utter_message(text="Omlouvám se, v katalogu produktů je technická chyba a nemohu Vám teď poradit.")
            return [SlotSet(s, None) for s in ["skin_type", "skin_concern", "product_category", "product_attribute", "brand", "skin_area"]]
        except Exception as e:
            print(f"CHYBA: Neočekávaná chyba při načítání souboru s produkty: {e}")
            dispatcher.utter_message(text="Omlouvám se, nastala neočekávaná chyba při hledání produktů.")
            return [SlotSet(s, None) for s in ["skin_type", "skin_concern", "product_category", "product_attribute", "brand", "skin_area"]]

        # --- 2. Získání hodnot slotů z trackeru ---
        skin_type_slot = tracker.get_slot("skin_type")
        skin_concern_slot = tracker.get_slot("skin_concern")
        product_category_slot = tracker.get_slot("product_category")
        product_attribute_slot = tracker.get_slot("product_attribute")
        brand_slot = tracker.get_slot("brand")
        skin_area_slot = tracker.get_slot("skin_area")

        print(f"INFO (ActionRecommendProduct): Přijaté sloty -> "
              f"skin_type: {skin_type_slot} (typ: {type(skin_type_slot)}), "
              f"skin_concern: {skin_concern_slot} (typ: {type(skin_concern_slot)}), "
              f"product_category: '{product_category_slot}' (typ: {type(product_category_slot)}), "
              f"product_attribute: {product_attribute_slot} (typ: {type(product_attribute_slot)}), "
              f"brand: '{brand_slot}' (typ: {type(brand_slot)}), "
              f"skin_area: '{skin_area_slot}' (typ: {type(skin_area_slot)})")

        # --- 3. Filtrování produktů ---
        recommended_products = []

        if not products:
            print("VAROVÁNÍ (ActionRecommendProduct): Seznam produktů je prázdný po načtení JSONu.")
            dispatcher.utter_message(text="Omlouvám se, momentálně nemáme v nabídce žádné produkty k doporučení.")
            return [SlotSet(s, None) for s in ["skin_type", "skin_concern", "product_category", "product_attribute", "brand", "skin_area"]]

        for product in products:
            product_name_for_debug = product.get('name', f"NEZNÁMÉ ID: {product.get('id', 'N/A')}")
            # print(f"DEBUG (ActionRecommendProduct): --- Zpracovávám produkt: {product_name_for_debug} ---") # Může být příliš upovídané

            product_skin_types = [st.lower() for st in product.get("skin_types", []) if isinstance(st, str)]
            product_skin_concerns = [sc.lower() for sc in product.get("skin_concerns", []) if isinstance(sc, str)]
            product_category_value = product.get("category", "").lower()
            product_attributes_list = [attr.lower() for attr in product.get("attributes", []) if isinstance(attr, str)]
            product_brand_value = product.get("brand", "").lower()
            product_skin_areas_list = [sa.lower() for sa in product.get("skin_areas", []) if isinstance(sa, str)]

            match_skin_type = True
            match_skin_concern = True
            match_product_category = True
            match_product_attributes = True
            match_brand = True
            match_skin_area = True

            # Normalizace a kontrola slotů před porovnáním
            # skin_type
            current_skin_type_slot_values = []
            if skin_type_slot and isinstance(skin_type_slot, list):
                current_skin_type_slot_values = [st.strip().lower() for st in skin_type_slot if isinstance(st, str) and st.strip()]
            
            if current_skin_type_slot_values: # Filtrujeme jen pokud je slot vyplněn validními hodnotami
                match_skin_type = False
                for st_slot_item_lower in current_skin_type_slot_values:
                    if st_slot_item_lower in product_skin_types:
                        match_skin_type = True
                        break
            
            # skin_concern
            current_skin_concern_slot_values = []
            if skin_concern_slot and isinstance(skin_concern_slot, list):
                current_skin_concern_slot_values = [sc.strip().lower() for sc in skin_concern_slot if isinstance(sc, str) and sc.strip()]

            if current_skin_concern_slot_values:
                match_skin_concern = False
                for sc_slot_item_lower in current_skin_concern_slot_values:
                    if any(p_concern_item in sc_slot_item_lower or sc_slot_item_lower in p_concern_item for p_concern_item in product_skin_concerns):
                        match_skin_concern = True
                        break
            
            # product_category
            current_product_category_slot_value = None
            if isinstance(product_category_slot, str) and product_category_slot.strip() and product_category_slot.lower() != 'none':
                current_product_category_slot_value = product_category_slot.strip().lower()
            if current_product_category_slot_value:
                match_product_category = (current_product_category_slot_value == product_category_value)

            # product_attribute
            current_product_attribute_slot_values = []
            if product_attribute_slot and isinstance(product_attribute_slot, list):
                 current_product_attribute_slot_values = [attr.strip().lower() for attr in product_attribute_slot if isinstance(attr, str) and attr.strip()]

            if current_product_attribute_slot_values:
                match_product_attributes = False # Předpokládáme neshodu, dokud nenajdeme všechny
                all_attributes_found = True
                for attr_slot_item_lower in current_product_attribute_slot_values:
                    if not (attr_slot_item_lower in product_attributes_list):
                        all_attributes_found = False
                        break
                if all_attributes_found:
                    match_product_attributes = True

            # brand
            current_brand_slot_value = None
            if isinstance(brand_slot, str) and brand_slot.strip() and brand_slot.lower() != 'none':
                current_brand_slot_value = brand_slot.strip().lower()
            if current_brand_slot_value:
                match_brand = (current_brand_slot_value == product_brand_value)

            # skin_area
            current_skin_area_slot_value = None
            if isinstance(skin_area_slot, str) and skin_area_slot.strip() and skin_area_slot.lower() != 'none':
                current_skin_area_slot_value = skin_area_slot.strip().lower()
            if current_skin_area_slot_value:
                match_skin_area = (current_skin_area_slot_value in product_skin_areas_list)

            if match_skin_type and match_skin_concern and match_product_category and match_product_attributes and match_brand and match_skin_area:
                print(f"INFO (ActionRecommendProduct): Produkt '{product_name_for_debug}' ODPOVÍDÁ kritériím.")
                recommended_products.append(product)
            # else:
                # print(f"DEBUG (ActionRecommendProduct): Produkt '{product_name_for_debug}' NEODPOVÍDÁ. Shody -> skin_type: {match_skin_type}, skin_concern: {match_skin_concern}, category: {match_product_category}, attributes: {match_product_attributes}, brand: {match_brand}, skin_area: {match_skin_area}")


        print(f"INFO (ActionRecommendProduct): Celkem nalezeno doporučených produktů: {len(recommended_products)}")

        # --- 4. Odeslání odpovědi uživateli ---
        if recommended_products:
            response_intro_parts = []
            # Používáme již normalizované a očištěné hodnoty slotů pro sestavení odpovědi
            if current_brand_slot_value:
                response_intro_parts.append(f"značky '{current_brand_slot_value}'")
            if current_product_category_slot_value:
                response_intro_parts.append(f"kategorie '{current_product_category_slot_value}'")
            if current_skin_type_slot_values: # Používáme seznam očištěných hodnot
                skin_types_text = ", ".join(current_skin_type_slot_values)
                response_intro_parts.append(f"pro typy pleti: {skin_types_text}")
            if current_skin_concern_slot_values:
                concerns_text = ", ".join(current_skin_concern_slot_values)
                response_intro_parts.append(f"řešící problémy: {concerns_text}")
            if current_product_attribute_slot_values:
                attrs_text = ", ".join(current_product_attribute_slot_values)
                response_intro_parts.append(f"s vlastnostmi: {attrs_text}")
            if current_skin_area_slot_value:
                response_intro_parts.append(f"pro oblast '{current_skin_area_slot_value}'")

            if response_intro_parts:
                response_intro = f"Pro Vaše požadavky ({'; '.join(response_intro_parts)}) bych Vám mohla doporučit:"
            else:
                response_intro = "Na základě Vašeho dotazu bych Vám mohla nabídnout tyto produkty:"
            
            dispatcher.utter_message(text=response_intro)

            for i, product_data in enumerate(recommended_products[:3]):
                product_name = product_data.get('name', 'Neznámý produkt')
                product_description = product_data.get('description', 'Popis není k dispozici.')
                product_link = product_data.get('link')
                
                message = f"{i+1}. **{product_name}**: {product_description}"
                if product_link:
                    message += f"\n   Více zde: {product_link}"
                dispatcher.utter_message(text=message)
                print(f"INFO (ActionRecommendProduct): Doporučen produkt: {product_name}")
            
            if len(recommended_products) > 3:
                dispatcher.utter_message(text=f"Našla jsem celkem {len(recommended_products)} produktů. Zobrazuji první tři. Pokud chcete vidět další, dejte mi vědět!")

        else:
            print("INFO (ActionRecommendProduct): Nebyly nalezeny žádné produkty odpovídající kritériím po filtrování.")
            dispatcher.utter_message(text="Omlouvám se, nenašla jsem žádný produkt, který by přesně odpovídal Vašemu požadavku. Můžete zkusit upřesnit, co hledáte, nebo se podívejte na naši kompletní nabídku na e-shopu.")
        
        print("---------------------------------------------------------------------------")
        print("!!! Akce ActionRecommendProduct DOKONČENA !!!")
        print("---------------------------------------------------------------------------")
        
        # --- 5. Resetování všech relevantních slotů ---
        # Toto je důležité, pokud tato akce běží jako submit akce formuláře.
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

    async def validate_skin_type(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        """Validuje hodnotu slotu `skin_type`."""
        print(f"VALIDATE_FORM: Validating skin_type: {slot_value} (typ: {type(slot_value)})")
        
        if slot_value is None:
            return {"skin_type": None}

        if not isinstance(slot_value, list):
            if isinstance(slot_value, str) and slot_value.strip():
                print(f"VALIDATE_FORM: skin_type byl string '{slot_value}', převádím na list.")
                slot_value = [slot_value.strip()]
            else:
                print(f"VALIDATE_FORM: skin_type není list ani validní string, resetuji na None.")
                # dispatcher.utter_message(text="Prosím, zadejte typ pleti jako seznam (např. 'suchá, citlivá') nebo jeden typ.")
                return {"skin_type": None}
        
        cleaned_list = [item.strip() for item in slot_value if isinstance(item, str) and item.strip()]
        
        if not cleaned_list:
            print(f"VALIDATE_FORM: skin_type po vyčištění prázdný, resetuji na None.")
            return {"skin_type": None}
            
        print(f"VALIDATE_FORM: skin_type validován na: {cleaned_list}")
        return {"skin_type": cleaned_list}


    async def validate_skin_concern(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        """Validuje hodnotu slotu `skin_concern`."""
        print(f"VALIDATE_FORM: Validating skin_concern: {slot_value} (typ: {type(slot_value)})")

        if slot_value is None:
            return {"skin_concern": None}

        if not isinstance(slot_value, list):
            if isinstance(slot_value, str) and slot_value.strip():
                print(f"VALIDATE_FORM: skin_concern byl string '{slot_value}', převádím na list.")
                slot_value = [slot_value.strip()]
            else:
                print(f"VALIDATE_FORM: skin_concern není list ani validní string, resetuji na None.")
                return {"skin_concern": None}

        cleaned_list = [item.strip() for item in slot_value if isinstance(item, str) and item.strip()]
        
        if not cleaned_list:
            print(f"VALIDATE_FORM: skin_concern po vyčištění prázdný, resetuji na None.")
            return {"skin_concern": None}

        print(f"VALIDATE_FORM: skin_concern validován na: {cleaned_list}")
        return {"skin_concern": cleaned_list}

    async def validate_product_category(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        """Validuje hodnotu slotu `product_category`."""
        print(f"VALIDATE_FORM: Validating product_category: '{slot_value}' (typ: {type(slot_value)})")
        if isinstance(slot_value, str) and slot_value.strip() and slot_value.lower() != 'none':
            validated_value = slot_value.strip()
            print(f"VALIDATE_FORM: product_category validován na: '{validated_value}'")
            return {"product_category": validated_value}
        
        print(f"VALIDATE_FORM: product_category je prázdný, 'none' nebo nevalidní, resetuji na None.")
        return {"product_category": None}

    async def validate_product_attribute(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        """Validuje hodnotu slotu `product_attribute`."""
        print(f"VALIDATE_FORM: Validating product_attribute: {slot_value} (typ: {type(slot_value)})")

        if slot_value is None:
            return {"product_attribute": None}

        if not isinstance(slot_value, list):
            if isinstance(slot_value, str) and slot_value.strip():
                print(f"VALIDATE_FORM: product_attribute byl string '{slot_value}', převádím na list.")
                slot_value = [slot_value.strip()]
            else:
                print(f"VALIDATE_FORM: product_attribute není list ani validní string, resetuji na None.")
                return {"product_attribute": None}
        
        cleaned_list = [item.strip() for item in slot_value if isinstance(item, str) and item.strip()]
        
        if not cleaned_list:
            print(f"VALIDATE_FORM: product_attribute po vyčištění prázdný, resetuji na None.")
            return {"product_attribute": None}
            
        print(f"VALIDATE_FORM: product_attribute validován na: {cleaned_list}")
        return {"product_attribute": cleaned_list}

    async def validate_brand(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        """Validuje hodnotu slotu `brand`."""
        print(f"VALIDATE_FORM: Validating brand: '{slot_value}' (typ: {type(slot_value)})")
        if isinstance(slot_value, str) and slot_value.strip() and slot_value.lower() != 'none':
            validated_value = slot_value.strip()
            print(f"VALIDATE_FORM: brand validován na: '{validated_value}'")
            return {"brand": validated_value}

        print(f"VALIDATE_FORM: brand je prázdný, 'none' nebo nevalidní, resetuji na None.")
        return {"brand": None}

    async def validate_skin_area(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        """Validuje hodnotu slotu `skin_area`."""
        print(f"VALIDATE_FORM: Validating skin_area: '{slot_value}' (typ: {type(slot_value)})")
        if isinstance(slot_value, str) and slot_value.strip() and slot_value.lower() != 'none':
            validated_value = slot_value.strip()
            print(f"VALIDATE_FORM: skin_area validován na: '{validated_value}'")
            return {"skin_area": validated_value}
        
        print(f"VALIDATE_FORM: skin_area je prázdný, 'none' nebo nevalidní, resetuji na None.")
        return {"skin_area": None}

    # --- Příklad dynamicky povinných slotů (odkomentuj a uprav podle potřeby) ---
    # @staticmethod
    # def required_slots(tracker: Tracker) -> List[Text]:
    #     """
    #     Dynamicky určuje, které sloty jsou povinné.
    #     Tato metoda se volá, aby se zjistilo, na který další slot se má formulář zeptat.
    #     """
    #     # Seznam všech slotů formuláře
    #     all_form_slots = ["skin_type", "skin_concern", "product_category", "product_attribute", "brand", "skin_area"]
    #     
    #     # Sloty, které chceme vždy vyplnit, pokud ještě nejsou
    #     core_slots_to_fill = ["skin_type", "skin_concern", "product_category"]
    #     
    #     required = []
    #     
    #     # Nejprve zkontrolujeme základní povinné sloty
    #     for slot_name in core_slots_to_fill:
    #         if tracker.get_slot(slot_name) is None:
    #             # Pokud chceme, aby se formulář ptal na jeden povinný slot po druhém:
    #             print(f"DEBUG (required_slots): Požaduji základní slot: {slot_name}")
    #             return [slot_name] 
    #             # Pokud chceme vrátit všechny chybějící základní sloty najednou:
    #             # required.append(slot_name) 
    #
    #     # Pokud jsou všechny základní sloty vyplněny, můžeme se ptát na další
    #     # (např. nepovinné nebo podmíněně povinné)
    #     # V tomto příkladu se po vyplnění základních zeptáme na zbývající, pokud nejsou vyplněny.
    #     # if not required: # Pokud jsou všechny core_slots vyplněny
    #     #    for slot_name in all_form_slots:
    #     #        if slot_name not in core_slots_to_fill and tracker.get_slot(slot_name) is None:
    #     #            print(f"DEBUG (required_slots): Požaduji doplňkový slot: {slot_name}")
    #     #            return [slot_name] # Ptáme se na jeden doplňkový po druhém

    #     # Alternativně, pokud chceme, aby se formulář vždy zeptal na VŠECHNY definované sloty (pokud nejsou vyplněny):
    #     # required = [s for s in all_form_slots if tracker.get_slot(s) is None]
    #     # if required:
    #     #    print(f"DEBUG (required_slots): Požaduji první z chybějících: {required[0]}")
    #     #    return [required[0]] # Vždy se zeptá na první chybějící z celého seznamu

    #     print(f"DEBUG (required_slots): Aktuálně požadované sloty (pokud by se vracel seznam všech chybějících): {required}")
    #     # Pokud se dostaneme sem a `required` je prázdný, znamená to, že všechny sloty,
    #     # které jsme chtěli vyplnit podle naší logiky, jsou vyplněny.
    #     # Formulář by se měl ukončit.
    #     return required
