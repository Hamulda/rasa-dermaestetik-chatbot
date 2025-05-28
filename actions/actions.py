import json
from typing import Any, Text, Dict, List

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet

class ActionRecommendProduct(Action):

    def name(self) -> Text:
        return "action_recommend_product"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        print("---------------------------------------------------------------------------")
        print(f"!!! Akce ActionRecommendProduct byla ZAVOLÁNA (ID konverzace: {tracker.sender_id}) !!!")
        print("---------------------------------------------------------------------------")

        products_file_path = './data/products.json'
        try:
            with open(products_file_path, 'r', encoding='utf-8') as f:
                products = json.load(f)
            print(f"INFO: Soubor s produkty '{products_file_path}' úspěšně načten. Počet produktů: {len(products)}")
        except FileNotFoundError:
            print(f"CHYBA: Soubor s produkty nebyl nalezen na cestě: {products_file_path}")
            dispatcher.utter_message(text=f"Omlouvám se, momentálně nemohu načíst katalog produktů.")
            return [SlotSet(s, None) for s in ["skin_type", "skin_concern", "product_category", "product_attribute", "brand", "skin_area"]]
        except json.JSONDecodeError:
            print(f"CHYBA: V souboru s produkty ({products_file_path}) je chyba (není validní JSON) a nelze ho zpracovat.")
            dispatcher.utter_message(text=f"Omlouvám se, v katalogu produktů je technická chyba a nemohu Vám teď poradit.")
            return [SlotSet(s, None) for s in ["skin_type", "skin_concern", "product_category", "product_attribute", "brand", "skin_area"]]
        except Exception as e:
            print(f"CHYBA: Neočekávaná chyba při načítání souboru s produkty: {e}")
            dispatcher.utter_message(text=f"Omlouvám se, nastala neočekávaná chyba při hledání produktů.")
            return [SlotSet(s, None) for s in ["skin_type", "skin_concern", "product_category", "product_attribute", "brand", "skin_area"]]

        skin_type_slot = tracker.get_slot("skin_type")
        skin_concern_slot = tracker.get_slot("skin_concern")
        product_category_slot = tracker.get_slot("product_category")
        product_attribute_slot = tracker.get_slot("product_attribute")
        brand_slot = tracker.get_slot("brand")
        skin_area_slot = tracker.get_slot("skin_area") # <--- NOVÝ SLOT NAČTEN

        print(f"INFO: Přijaté sloty -> skin_type: {skin_type_slot} (typ: {type(skin_type_slot)}), skin_concern: {skin_concern_slot} (typ: {type(skin_concern_slot)}), product_category: '{product_category_slot}' (typ: {type(product_category_slot)}), product_attribute: {product_attribute_slot}, brand: '{brand_slot}', skin_area: '{skin_area_slot}' (typ: {type(skin_area_slot)})")

        recommended_products = []

        if not products:
            print("VAROVÁNÍ: Seznam produktů je prázdný po načtení JSONu.")
            dispatcher.utter_message(text="Omlouvám se, momentálně nemáme v nabídce žádné produkty k doporučení.")
            return [SlotSet(s, None) for s in ["skin_type", "skin_concern", "product_category", "product_attribute", "brand", "skin_area"]]

        for product in products:
            print(f"DEBUG: --- Začínám zpracovávat produkt: {product.get('name', 'NEZNÁMÉ ID/JMÉNO')} ---")

            product_skin_types = [st.lower() for st in product.get("skin_types", []) if isinstance(st, str)]
            product_skin_concerns = [sc.lower() for sc in product.get("skin_concerns", []) if isinstance(sc, str)]
            product_category_value = product.get("category", "").lower()
            product_attributes_list = [attr.lower() for attr in product.get("attributes", []) if isinstance(attr, str)]
            product_brand_value = product.get("brand", "").lower()
            product_skin_areas_list = [sa.lower() for sa in product.get("skin_areas", []) if isinstance(sa, str)] # <--- NOVÉ DATOVÉ POLE Z PRODUKTU

            match_skin_type = False
            match_skin_concern = False
            match_product_category = False
            match_product_attributes = False
            match_brand = False
            match_skin_area = False # <--- NOVÁ PROMĚNNÁ PRO SHODU

            # Shoda pro typ pleti
            if skin_type_slot and isinstance(skin_type_slot, list) and skin_type_slot:
                match_skin_type = False 
                for st_slot_item in skin_type_slot:
                    st_slot_item_lower = st_slot_item.lower()
                    if st_slot_item_lower in product_skin_types:
                        match_skin_type = True
                        break 
            else:
                match_skin_type = True 
            
            # Shoda pro problém pleti
            if skin_concern_slot and isinstance(skin_concern_slot, list) and skin_concern_slot:
                match_skin_concern = False 
                for sc_slot_item in skin_concern_slot:
                    slot_item_value_lower = sc_slot_item.lower()
                    temp_match_found_for_this_item = False
                    for p_concern_item in product_skin_concerns: 
                        cond1 = p_concern_item in slot_item_value_lower
                        cond2 = slot_item_value_lower in p_concern_item
                        is_match = cond1 or cond2
                        if is_match:
                            temp_match_found_for_this_item = True
                            break 
                    if temp_match_found_for_this_item:
                        match_skin_concern = True 
                        break 
            else:
                match_skin_concern = True
            
            # Shoda pro kategorii produktu
            current_product_category_slot = product_category_slot
            if isinstance(product_category_slot, str) and (product_category_slot.lower() == 'none' or not product_category_slot.strip()):
                current_product_category_slot = None

            if current_product_category_slot:
                if current_product_category_slot.lower() == product_category_value:
                    match_product_category = True
            else:
                match_product_category = True

            # Shoda pro atributy produktu
            if product_attribute_slot and isinstance(product_attribute_slot, list) and product_attribute_slot:
                all_attributes_match = True 
                for attr_slot_item in product_attribute_slot:
                    attr_slot_item_lower = attr_slot_item.lower()
                    if attr_slot_item_lower not in product_attributes_list:
                        all_attributes_match = False 
                        break 
                match_product_attributes = all_attributes_match
            else:
                match_product_attributes = True

            # Shoda pro značku produktu
            if brand_slot:
                if brand_slot.lower() == product_brand_value:
                    match_brand = True
            else:
                match_brand = True

            # Shoda pro oblast pokožky (skin_area_slot je text) <--- NOVÁ LOGIKA
            current_skin_area_slot = skin_area_slot
            if isinstance(skin_area_slot, str) and (skin_area_slot.lower() == 'none' or not skin_area_slot.strip()):
                current_skin_area_slot = None

            if current_skin_area_slot: # Pokud je slot skin_area naplněn
                if current_skin_area_slot.lower() in product_skin_areas_list:
                    match_skin_area = True
            else: # Pokud slot skin_area není naplněn, považujeme to za shodu
                match_skin_area = True

            # Finální podmínka nyní zahrnuje match_skin_area
            if match_skin_type and match_skin_concern and match_product_category and match_product_attributes and match_brand and match_skin_area:
                print(f"INFO: Produkt '{product.get('name')}' ODPOVÍDÁ kritériím (skin_type: {match_skin_type}, skin_concern: {match_skin_concern}, category: {match_product_category}, attributes: {match_product_attributes}, brand: {match_brand}, skin_area: {match_skin_area})")
                recommended_products.append(product)
            else:
                print(f"INFO: Produkt '{product.get('name')}' NEODPOVÍDÁ kritériím (skin_type: {match_skin_type}, skin_concern: {match_skin_concern}, category: {match_product_category}, attributes: {match_product_attributes}, brand: {match_brand}, skin_area: {match_skin_area})")

        print(f"INFO: Celkem nalezeno doporučených produktů: {len(recommended_products)}")

        if recommended_products:
            response_intro_parts = []
            if brand_slot:
                response_intro_parts.append(f"značky '{brand_slot}'")
            
            if current_product_category_slot:
                response_intro_parts.append(f"kategorie '{current_product_category_slot.lower()}'")
            
            if skin_type_slot and isinstance(skin_type_slot, list) and skin_type_slot:
                skin_types_text = ", ".join(skin_type_slot)
                response_intro_parts.append(f"pro typy pleti: {skin_types_text}")
            elif skin_type_slot and isinstance(skin_type_slot, str): 
                 response_intro_parts.append(f"pro {skin_type_slot} pleť")

            if skin_concern_slot and isinstance(skin_concern_slot, list) and skin_concern_slot:
                concerns_text = ", ".join(skin_concern_slot)
                response_intro_parts.append(f"řešící problémy: {concerns_text}")
            elif skin_concern_slot and isinstance(skin_concern_slot, str): 
                response_intro_parts.append(f"řešící '{skin_concern_slot}'")
            
            if product_attribute_slot and isinstance(product_attribute_slot, list) and product_attribute_slot:
                attrs_text = ", ".join(product_attribute_slot)
                response_intro_parts.append(f"s vlastnostmi: {attrs_text}")

            if current_skin_area_slot: # <--- PŘIDÁNO DO ODPOVĚDI
                response_intro_parts.append(f"pro oblast '{current_skin_area_slot.lower()}'")

            if response_intro_parts:
                response_intro = f"Pro Vaše požadavky ({'; '.join(response_intro_parts)}) bych Vám mohla doporučit:"
            else:
                response_intro = "Na základě Vašeho dotazu bych Vám mohla nabídnout:"
            
            dispatcher.utter_message(text=response_intro)

            for i, product_data in enumerate(recommended_products[:3]):
                product_name = product_data.get('name', 'Neznámý produkt')
                product_description = product_data.get('description', 'Popis není k dispozici.')
                product_link = product_data.get('link', '#')
                message = f"{i+1}. {product_name}: {product_description}\n   Více zde: {product_link}"
                dispatcher.utter_message(text=message)
                print(f"INFO: Doporučen produkt: {product_name}")
        else:
            print("INFO: Nebyly nalezeny žádné produkty odpovídající kritériím po filtrování.")
            dispatcher.utter_message(text="Omlouvám se, nenašla jsem žádný produkt, který by přesně odpovídal Vašemu požadavku. Můžete zkusit upřesnit, co hledáte, nebo se podívejte na naši kompletní nabídku na e-shopu.")
        
        print("---------------------------------------------------------------------------")
        print("!!! Akce ActionRecommendProduct DOKONČENA !!!")
        print("---------------------------------------------------------------------------")
        return [ # <--- UPRAVENO PRO NOVÝ SLOT
            SlotSet("skin_type", None), 
            SlotSet("skin_concern", None), 
            SlotSet("product_category", None),
            SlotSet("product_attribute", None),
            SlotSet("brand", None),
            SlotSet("skin_area", None) 
        ]