import re
def extract_session_id(session_str: str):
    match = re.search(r"/sessions/(.*?)/contexts/", session_str)
    if match:
        extracted_string = match.group(1)
        return extracted_string
    return ""

def get_str_from_food_dict(food_dict: dict):
    return ", ".join([f"{int(value)} {key}" for key, value in food_dict.items()])

if __name__ == "__main__":
    # print(get_str_from_food_dict({"momo":2, "sekuwa": 3 }))
    print(extract_session_id("projects/nlp-chatbot-yfbp/agent/sessions/eee02238-1528-3662-a9fb-8a75618b5494/contexts/ongoing-order"))
    # session_str = "projects/nlp-chatbot-yfbp/agent/sessions/eee02238-1528-3662-a9fb-8a75618b5494/contexts/ongoing-order"
    # print(extract_session_id(session_str))