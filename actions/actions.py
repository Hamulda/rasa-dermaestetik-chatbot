# hamulda/rasa-dermaestetik-chatbot/Hamulda-rasa-dermaestetik-chatbot-79a84f686ca329ca215d1171b8e32c27131672fb/actions/actions.py
import json
from typing import Any, Text, Dict, List, Optional
import dateparser
from datetime import datetime

from rasa_sdk import Action, Tracker, FormValidationAction
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.types import DomainDict
from rasa_sdk.events import SlotSet, FollowupAction

# --- Constants ---
KNOWLEDGE_BASE_FILE_PATH = "data/knowledge_base.json"
PRODUCTS_FILE_PATH = "data/products.json"
USER_DATA_FILE = "data/user_data.json" 
BASE_ESHOP_URL = "https://www.dermaestetik.cz/"
PRODUCTS_PER_PAGE = 3

# --- Helper Functions ---

def load_json_file(file_path: Text) -> Optional[Dict]:
    """Loads a JSON file and returns its content."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: The file {file_path} was not found.")
        return None
    except json.JSONDecodeError:
        print(f"Error: The file {file_path} is not a valid JSON.")
        return None

def save_json_file(file_path: Text, data: Dict):
    """Saves a dictionary to a JSON file."""
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Error saving data to {file_path}: {e}")

def load_user_data() -> Dict:
    """Loads user data, returns empty dict if file doesn't exist."""
    data = load_json_file(USER_DATA_FILE)
    return data if data is not None else {}

def save_user_data(user_data: Dict):
    """Saves the user data dictionary."""
    save_json_file(USER_DATA_FILE, user_data)


def display_products(dispatcher: CollectingDispatcher, products: List[Dict[Text, Any]]):
    """Formats and displays a list of products to the user."""
    if not products:
        dispatcher.utter_message(response="utter_no_products_found")
        return

    elements = []
    for product in products:
        elements.append({
            "title": f"{product['brand']} - {product['name']}",
            "subtitle": f"Kategorie: {product['category']}\nCena: {product['price']} Kč",
            "image_url": product['image_url'],
            "buttons": [
                {
                    "title": "Zobrazit na e-shopu",
                    "url": f"{BASE_ESHOP_URL}{product['url']}",
                    "type": "web_url"
                },
                {
                    "title": "Více informací",
                    "payload": f'/select_product{{"product_name": "{product["name"]}"}}',
                    "type": "postback"
                }
            ]
        })
    
    dispatcher.utter_message(attachment={"type": "template", "payload": {"template_type": "generic", "elements": elements}})

# --- Product Recommendation Actions ---

class ActionRecommendProduct(Action):
    def name(self) -> Text:
        return "action_recommend_product"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        products = load_json_file(PRODUCTS_FILE_PATH)
        if not products:
            dispatcher.utter_message(text="Omlouvám se, momentálně nemám přístup k databázi produktů.")
            return []

        # Get filters from slots
        brand_filter = tracker.get_slot('brand')
        category_filter = tracker.get_slot('category')
        skin_type_filter = tracker.get_slot('skin_type')
        skin_concern_filter = tracker.get_slot('skin_concern')
        
        # Get excluded filters from custom slots
        excluded_filters = tracker.get_slot('excluded_filters') or {}
        excluded_brands = excluded_filters.get('brand', [])
        excluded_categories = excluded_filters.get('category', [])
        excluded_skin_types = excluded_filters.get('skin_type', [])
        excluded_skin_concerns = excluded_filters.get('skin_concern', [])

        filtered_products = products

        # Apply positive filters
        if brand_filter:
            filtered_products = [p for p in filtered_products if any(b.lower() in p['brand'].lower() for b in brand_filter)]
        if category_filter:
            filtered_products = [p for p in filtered_products if any(c.lower() in p['category'].lower() for c in category_filter)]
        if skin_type_filter:
            filtered_products = [p for p in filtered_products if p.get('skin_type') and any(st.lower() in [s.lower() for s in p['skin_type']] for st in skin_type_filter)]
        if skin_concern_filter:
            filtered_products = [p for p in filtered_products if p.get('skin_concern') and any(sc.lower() in [s.lower() for s in p['skin_concern']] for sc in skin_concern_filter)]

        # Apply negative/excluded filters
        if excluded_brands:
            filtered_products = [p for p in filtered_products if not any(b.lower() in p['brand'].lower() for b in excluded_brands)]
        if excluded_categories:
            filtered_products = [p for p in filtered_products if not any(c.lower() in p['category'].lower() for c in excluded_categories)]
        if excluded_skin_types:
            filtered_products = [p for p in filtered_products if not (p.get('skin_type') and any(st.lower() in [s.lower() for s in p['skin_type']] for st in excluded_skin_types))]
        if excluded_skin_concerns:
            filtered_products = [p for p in filtered_products if not (p.get('skin_concern') and any(sc.lower() in [s.lower() for s in p['skin_concern']] for sc in excluded_skin_concerns))]

        current_page = 1
        total_pages = -(-len(filtered_products) // PRODUCTS_PER_PAGE) # Ceiling division

        display_products(dispatcher, filtered_products[:PRODUCTS_PER_PAGE])

        if not filtered_products:
             # Follow up action to reset form if no products found
            return [SlotSet("products_shown", []), FollowupAction("action_listen")]
        
        # Save state for pagination
        return [
            SlotSet("products_shown", filtered_products),
            SlotSet("current_page", current_page),
            SlotSet("total_pages", total_pages),
            # Set a checkpoint
            SlotSet("active_filters", {
                "brand": brand_filter,
                "category": category_filter,
                "skin_type": skin_type_filter,
                "skin_concern": skin_concern_filter
            })
        ]

class ActionShowNextProducts(Action):
    def name(self) -> Text:
        return "action_show_next_products"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        products_shown = tracker.get_slot("products_shown")
        current_page = tracker.get_slot("current_page")
        total_pages = tracker.get_slot("total_pages")

        if not products_shown or current_page is None or total_pages is None:
            dispatcher.utter_message(text="Omlouvám se, zdá se, že nemám co zobrazit. Zkusme prosím nové vyhledávání.")
            return []

        if current_page >= total_pages:
            dispatcher.utter_message(text="Už jsem vám ukázala všechny produkty, které odpovídají vašemu výběru.")
            return [SlotSet("current_page", current_page)]

        next_page = current_page + 1
        start_index = int(current_page * PRODUCTS_PER_PAGE)
        end_index = int(start_index + PRODUCTS_PER_PAGE)

        display_products(dispatcher, products_shown[start_index:end_index])

        return [SlotSet("current_page", next_page)]

class ActionGetProductDetails(Action):
    def name(self) -> Text:
        return "action_get_product_details"

    def _get_product_from_tracker(self, tracker: Tracker) -> Optional[Dict]:
        """Helper to get a product based on product_name or product_order slot."""
        product_name = tracker.get_slot("product_name")
        product_order_str = tracker.get_slot("product_order") # "první", "druhý", etc.
        products_on_display = tracker.get_slot("products_shown")
        current_page = tracker.get_slot("current_page") or 1

        if product_name:
            all_products = load_json_file(PRODUCTS_FILE_PATH)
            for product in all_products:
                if product['name'].lower() == product_name.lower():
                    return product

        if product_order_str and products_on_display:
            order_map = {"první": 0, "druhý": 1, "třetí": 2, "prvni": 0, "druhy": 1, "treti": 2, "1":0, "2":1, "3":2}
            order_index = order_map.get(product_order_str.lower())
            
            if order_index is not None:
                start_index = int((current_page - 1) * PRODUCTS_PER_PAGE)
                actual_index = start_index + order_index
                if actual_index < len(products_on_display):
                    return products_on_display[actual_index]
        return None

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        product = self._get_product_from_tracker(tracker)
        
        if not product:
            dispatcher.utter_message(text="Omlouvám se, nemohu najít informace o tomto produktu. Zkuste to prosím znovu.")
            return [SlotSet("product_name", None), SlotSet("product_order", None)]
        
        knowledge_base = load_json_file(KNOWLEDGE_BASE_FILE_PATH)
        product_info = knowledge_base.get(product["name"], "Pro tento produkt bohužel nemám podrobné informace.")

        message = f"**{product['brand']} - {product['name']}**\n\n{product_info}"
        
        dispatcher.utter_message(text=message)
        return [SlotSet("product_name", None), SlotSet("product_order", None)]


class ActionCompareProducts(Action):
    def name(self) -> Text:
        return "action_compare_products"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        entities = tracker.latest_message.get('entities', [])
        product_orders = [e['value'] for e in entities if e['entity'] == 'product_order']
        
        if len(product_orders) < 2:
            dispatcher.utter_message(text="Prosím, specifikujte alespoň dva produkty k porovnání (např. 'porovnej první a druhý').")
            return []

        products_to_compare = []
        for order in product_orders:
            # Temporarily set slot to use the helper function
            temp_tracker = tracker.copy()
            temp_tracker.slots['product_order'] = SlotSet('product_order', order)
            temp_tracker.slots['product_name'] = SlotSet('product_name', None)
            
            action_details = ActionGetProductDetails()
            product = action_details._get_product_from_tracker(temp_tracker)
            if product:
                products_to_compare.append(product)

        if len(products_to_compare) < 2:
            dispatcher.utter_message(text="Omlouvám se, podařilo se mi najít méně než dva z požadovaných produktů.")
            return []

        # Create a comparison table in markdown
        headers = ["Vlastnost"] + [p['name'] for p in products_to_compare]
        rows = [
            ["Značka"] + [p['brand'] for p in products_to_compare],
            ["Kategorie"] + [p['category'] for p in products_to_compare],
            ["Cena"] + [f"{p['price']} Kč" for p in products_to_compare],
            ["Pro pleť"] + [", ".join(p.get('skin_type', ['N/A'])) for p in products_to_compare],
            ["Řeší"] + [", ".join(p.get('skin_concern', ['N/A'])) for p in products_to_compare]
        ]

        # Formatting as markdown table
        header_line = "| " + " | ".join(headers) + " |"
        separator_line = "| " + " | ".join(["---"] * len(headers)) + " |"
        row_lines = ["| " + " | ".join(row) + " |" for row in rows]
        
        table = "\n".join([header_line, separator_line] + row_lines)
        
        dispatcher.utter_message(text=f"Zde je porovnání vybraných produktů:\n\n{table}")

        return []


# --- Form Validation ---

class ValidateProductRecommendationForm(FormValidationAction):
    def name(self) -> Text:
        return "validate_product_recommendation_form"

    def _extract_negations(self, text: Text, entities: List[Dict]) -> Dict[Text, List[Text]]:
        """Extracts negated entities from user text."""
        negated_entities = {}
        negation_words = ["nechci", "bez", "ne", "kromě"]
        
        for entity in entities:
            entity_text = entity["value"]
            # Search for negation words in a window around the entity
            window_start = max(0, entity["start"] - 10)
            window_end = entity["end"] + 10
            text_window = text[window_start:window_end]

            if any(neg_word in text_window.lower() for neg_word in negation_words):
                entity_type = entity["entity"]
                if entity_type not in negated_entities:
                    negated_entities[entity_type] = []
                negated_entities[entity_type].append(entity_text)
        return negated_entities

    async def run(
        self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict
    ) -> List[Dict[Text, Any]]:
        events = await super().run(dispatcher, tracker, domain)
        
        last_message = tracker.latest_message
        text = last_message.get("text", "")
        entities = last_message.get("entities", [])
        
        negated = self._extract_negations(text, entities)
        if negated:
            current_excluded = tracker.get_slot("excluded_filters") or {}
            for entity_type, values in negated.items():
                if entity_type not in current_excluded:
                    current_excluded[entity_type] = []
                current_excluded[entity_type].extend(v for v in values if v not in current_excluded[entity_type])
            
            events.append(SlotSet("excluded_filters", current_excluded))

            # Remove negated values from the actual slots if they were picked up
            for slot_name, values in negated.items():
                current_slot_value = tracker.get_slot(slot_name)
                if isinstance(current_slot_value, list):
                    new_value = [v for v in current_slot_value if v not in values]
                    events.append(SlotSet(slot_name, new_value if new_value else None))

        return events

    def _validate_list_slot(
        self,
        slot_value: Any,
        slot_name: Text,
        known_values: List[Text]
    ) -> Dict[Text, Any]:
        if not slot_value:
            return {slot_name: None}
        
        validated_values = []
        for value in slot_value:
            # Simple normalization, can be improved with fuzzy matching
            normalized_value = value.lower()
            if any(normalized_value in known_val.lower() for known_val in known_values):
                 validated_values.append(value)
        
        return {slot_name: validated_values if validated_values else None}

    def validate_brand(self, slot_value: Any, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> Dict[Text, Any]:
        # This can be improved with a lookup table from a file
        known_brands = ["Medik8", "Rejudicare", "Gernetic", "Mesoestetic"]
        return self._validate_list_slot(slot_value, "brand", known_brands)
    
class ValidateAppointmentForm(FormValidationAction):
    def name(self) -> Text:
        return "validate_appointment_form"

    def validate_date(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        """Validate date value."""
        if not slot_value:
            return {"date": None}

        # Use dateparser to parse human-readable dates
        # Settings ensure we prefer dates in the future
        parsed_date = dateparser.parse(slot_value, languages=['cs'], settings={'PREFER_DATES_FROM': 'future'})

        if not parsed_date:
            dispatcher.utter_message(response="utter_ask_rephrase_date")
            return {"date": None}

        # Check if the parsed date is in the past (considering today as valid)
        if parsed_date.date() < datetime.now().date():
            dispatcher.utter_message(response="utter_date_in_past")
            return {"date": None}

        # Format the date nicely for confirmation
        # Example: "středa 18. června 2025"
        formatted_date = parsed_date.strftime("%A %d. %B %Y").lower()
        # Simple Czech day/month name replacement
        day_map = {'monday': 'pondělí', 'tuesday': 'úterý', 'wednesday': 'středa', 'thursday': 'čtvrtek', 'friday': 'pátek', 'saturday': 'sobota', 'sunday': 'neděle'}
        month_map = {'january': 'ledna', 'february': 'února', 'march': 'března', 'april': 'dubna', 'may': 'května', 'june': 'června', 'july': 'července', 'august': 'srpna', 'september': 'září', 'october': 'října', 'november': 'listopadu', 'december': 'prosince'}
        for en, cs in day_map.items():
            formatted_date = formatted_date.replace(en, cs)
        for en, cs in month_map.items():
            formatted_date = formatted_date.replace(en, cs)

        return {"date": formatted_date}


    def validate_time(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        """Validate time value."""
        if not slot_value:
            return {"time": None}
        
        # We can also use dateparser for time
        parsed_time = dateparser.parse(slot_value, languages=['cs'])
        
        if not parsed_time:
            dispatcher.utter_message(text="Omlouvám se, tento čas se mi nepodařilo rozpoznat. Zkuste to prosím znovu, například '14:30' nebo 'v deset dopoledne'.")
            return {"time": None}
            
        # Format to HH:MM
        formatted_time = parsed_time.strftime("%H:%M")
        return {"time": formatted_time}


# --- GDPR Actions ---

class ActionManageGDPR(Action):
    def name(self) -> Text:
        return "action_manage_gdpr"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        dispatcher.utter_message(response="utter_gdpr_manage")
        return []

class ActionGDPRConsentGrant(Action):
    def name(self) -> Text:
        return "action_gdpr_consent_grant"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        sender_id = tracker.sender_id
        user_data = load_user_data()
        
        # Uložíme souhlas pro daného uživatele
        user_data[sender_id] = {"consent_given": True}
        save_user_data(user_data)
        
        dispatcher.utter_message(response="utter_gdpr_consent_granted")
        return [SlotSet("gdpr_consent", True)]

class ActionGDPRConsentRevoke(Action):
    def name(self) -> Text:
        return "action_gdpr_consent_revoke"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        sender_id = tracker.sender_id
        user_data = load_user_data()

        if sender_id in user_data:
            user_data[sender_id]["consent_given"] = False
            save_user_data(user_data)
            
        dispatcher.utter_message(response="utter_gdpr_consent_revoked")
        return [SlotSet("gdpr_consent", False)]

class ActionGDPRDeleteData(Action):
    def name(self) -> Text:
        return "action_gdpr_delete_data"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        sender_id = tracker.sender_id
        user_data = load_user_data()

        if sender_id in user_data:
            del user_data[sender_id]
            save_user_data(user_data)
        
        dispatcher.utter_message(response="utter_gdpr_data_deleted")
        # Smažeme i všechny sloty pro jistotu
        return [SlotSet(slot, None) for slot in tracker.slots.keys()]