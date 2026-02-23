# from app.agent.state import AgentState

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
        return {
            translate_string(k): translate_obj(v)
            for k, v in obj.items()
        }

    elif isinstance(obj, list):
        return [translate_obj(item) for item in obj]

    elif isinstance(obj, str):
        return translate_string(obj)

    else:
        return obj

def parse_data(state, data: dict, partial=False):
    assert state.cognitive.problem_id == data["problem_id"]
    if not partial:
        assert data["scenario_id"] in state.cognitive.scenario_ids

        cleaned_data = data["data"]
        if "points" in cleaned_data:
            cleaned_data.pop("points")
        if "index_diffs" in data and data["index_diffs"]:
            cleaned_data["index_diffs"] = data["index_diffs"]
        cleaned_data = translate_obj(cleaned_data)
        if not state.cognitive.data:
            state.cognitive.data = {data["scenario_id"]: cleaned_data}
        else:
            state.cognitive.data[data["scenario_id"]] = cleaned_data


    # use later to run scenarios
    editable_indexes =  data["editable_indexes"]
    editable_indexes_with_limits = {}
    for group, indexes in data["widgets"].items():
        for index in indexes:
            if index["index_id"] in editable_indexes:
                editable_indexes_with_limits[index["index_id"]] = {
                "loc": 350.0,
                "scale": 100.0,
                "min": 0.0,
                "max": 1000.0,
                "step": 10.0
            }
                
    state.cognitive.editable_indexes = editable_indexes_with_limits
                
    return state