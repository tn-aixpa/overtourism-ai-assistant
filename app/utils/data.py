translation = {
    'parcheggi': 'parking',
    'spiaggia': 'beach',
    'alberghi': 'hotels',
    'ristoranti': 'restaurants',
}

def translate_string(s):
    for old, new in translation.items():
        s = s.replace(old, new)
    return s

def translate_obj(obj):
    if isinstance(obj, dict):
        return {translate_string(k): translate_obj(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [translate_obj(item) for item in obj]
    elif isinstance(obj, str):
        return translate_string(obj)
    else:
        return obj

def parse_data(data: dict, type: str):
    if type == "problem":
        extras = data.pop("extras", {})
        if "groups" in extras:
            data["groups"] = [
                translation.get(group.lower(), group) for group in extras["groups"]
            ]
        # editable_indexes lives in extras now, just drop it (fetched separately via widgets)

    elif type == "proposal":
        data.pop("related_scenario_ids", None)

    elif type == "scenario":
        extras = data.pop("extras", {})
        cleaned_data = data.get("index_values", [])
        data["data"] = translate_obj(cleaned_data)
        data.pop("index_values", None)

    return data

def parse_editable_indexes(input_json):
    """
    Parses the input JSON and returns editable_indexes with their limits.
    """
    editable_indexes_with_limits = {}

    for group, indexes in input_json.get("widgets", {}).items():
        for index in indexes:
            if index.get("editable", False):
                editable_indexes_with_limits[index["index_id"]] = {
                    "loc": index.get("loc", index.get("v", 0.0)),
                    "scale": index.get("scale", 0.0),
                    "min": index.get("min", 0.0),
                    "max": index.get("max", 1000.0),
                    "step": index.get("step", 1.0)
                }

    return editable_indexes_with_limits