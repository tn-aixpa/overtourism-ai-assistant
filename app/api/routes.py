# SPDX-License-Identifier: Apache-2.0

from fastapi import APIRouter, HTTPException
import logging

from app.schemas import AgentRequest, AgentResponse
from app.agent.state import AgentState
from app.agent.graph import app as agent_app
from app.agent.memory import generate_key, load_state, save_state
from app.utils.common import translate_from_eng
from app.utils.error_codes import get_error_message, ErrorCode

logger = logging.getLogger(__name__)

router = APIRouter()

def load_demo_data(state: AgentState) -> AgentState:
    import json
    from app.utils.data import parse_data
    state.cognitive.problem_info_to_extract = {
        "problem_title": {"description": "The title of the problem", "required": True},
        "objectives": {"description": "The objectives of the problem", "required": True},
        "problem_description": {"description": "A detailed description of the problem the that the user wants to address, that will provide context for the analysis", "required": True},
        "available_subsystems": {"description": "The available subsystems related to the problem", "required": False},
        "additional_data": {"description": "Any additional data relevant to the problem", "required": False},
    }

    state.cognitive.problem_id = "parcheggi_200"

    state.cognitive.scenario_info_to_extract = {
        "title": {"description": "The title of the scenario", "required": True},
        "description": {"description": "Describes the proposal", "required": False},
        "additional_data": {"description": "Any additional data relevant to the problem, links or attachments", "required": False},
        "context_conditions": {"description": "Elements/factors that can impact the proposed solution", "required": False},
        "potential_impact": {"description": "Potential impact of the proposal", "required": False},
        "indexes_to_change": {"description": "Indexes of simulation to change", "required": True}
    }

    with open(f"tests/data/test_base.json", "r") as f:
        state = parse_data(state, json.loads(f.read()), True)

    state.cognitive.scenario_ids = ["model_0", "model_3"]
    state.cognitive.data = {}

    with open(f"tests/data/test_base.json", "r") as f:
        state = parse_data(state, json.loads(f.read()))
    with open(f"tests/data/test_1.json", "r") as f:
        state = parse_data(state, json.loads(f.read()))
    return state

@router.post("/agent", response_model=AgentResponse)
async def run_agent_endpoint(request: AgentRequest) -> AgentResponse:
    """
    Main entrypoint for the AI agent.

    Responsibilities:
    - Resolve memory scope using (session_id, problem_id, scenario_ids)
    - Load existing AgentState or create a new one
    - Inject the new user message and data
    - Run LangGraph
    - Persist updated state
    - Return structured response
    """

    try:
        # resolve memory key for session
        key = request.session_id or generate_key()
        
        # load existing state or create a new one
        state = load_state(key)
        if not state:
            user_lang = getattr(request, 'user_lang', "English")
            state = AgentState(session_id=key, user_lang=user_lang)

            #TODO: remove this part later
            demo = getattr(request, 'demo', False)
            if demo:
                state = load_demo_data(state)

        # inject user messages
        assert request.message, "No message provided in the request"
        
        translated = translate_from_eng(request.message, state.user_lang)
        state.add_user_message(localized=request.message, translated_en=translated)

        # 5Run LangGraph agent
        updated_state_dict = agent_app.invoke(state)
        final_state = AgentState(**updated_state_dict)

        # persist updated state
        save_state(key, final_state)

        # return the last assistant message as response
        last_msg = final_state.get_last_message()
        response_text = ""
        if last_msg and last_msg.role == "assistant":
            response_text = last_msg.content_localized  # return in user language
        else:
            logger.warning("No assistant message generated in the response")
            response_text = get_error_message(ErrorCode.REQUEST_ERROR, final_state=state.user_lang)

        return AgentResponse(response=response_text)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Agent execution failed")
        raise HTTPException(
            status_code=500,
            detail=f"Agent execution failed: {str(e)}",
        )