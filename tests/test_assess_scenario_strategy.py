import pytest
from dataclasses import replace

from app.agent.nodes.problem import decide_scenario_strategy
from app.agent.state import ConversationMessage

@pytest.mark.parametrize(
    "messages, expected_answer",
    [
        # GENERATE_SCENARIOS
        ([{"role": "user", "content": "In Molveno there is a problem related to the fact that there are not enough parking spaces, which leads to people parking off-spot and long queues."},
          {"role": "assistant", "content": "Would you like me to generate scenarios to address this problem or do you have any specific scenario in mind that you want to generate?"},
          {"role": "user", "content": "Yes, please, I would like to see how adding 200 parking spaces would impact the problem."}],
 "GENERATE_SCENARIOS"),
        ([{"role": "user", "content": "In Molveno there is a problem related to the fact that there are not enough parking spaces, which leads to people parking off-spot and long queues. I would like also to see the result when increasing parking slots of 200 units and of to indocue a politics that favors larger groups."}],
 "GENERATE_SCENARIOS"),

        # GENERATE_AGENTIC_SCENARIOS
        ([{"role": "user", "content": "In Molveno there is a problem related to the fact that there are not enough parking spaces, which leads to people parking off-spot and long queues."},
          {"role": "assistant", "content": "Would you like me to generate scenarios to address this problem or do you have any specific scenario in mind that you want to generate?"},
          {"role": "user", "content": "Yes, please, suggest some valid solutions to this problem."}],
 "GENERATE_AGENTIC_SCENARIOS"),
        ([{"role": "user", "content": "In Molveno there is a problem related to the fact that there are not enough parking spaces, which leads to people parking off-spot and long queues. Please, also suggest some valid solutions to this problem."}],
 "GENERATE_AGENTIC_SCENARIOS"),

        # ASK_USER_PREFERENCE
        ([{"role": "user", "content": "In Molveno there is a problem related to the fact that there are not enough parking spaces, which leads to people parking off-spot and long queues."}],
 "ASK_USER_PREFERENCE"),

        # NO_SCENARIOS
        ([{"role": "user", "content": "In Molveno there is a problem related to the fact that there are not enough parking spaces, which leads to people parking off-spot and long queues."},
          {"role": "assistant", "content": "Would you like me to generate scenarios to address this problem or do you have any specific scenario in mind that you want to generate?"},
          {"role": "user", "content": "No, thanks."}],
 "NO_SCENARIOS")
    ],
)
def test_single_roles(empty_state, messages, expected_answer):
    state = replace(empty_state)
    for msg in messages:
       state.conversation.append(
              ConversationMessage(
                  role=msg["role"],
                  content=msg["content"],
       ))
       if msg["role"] == "user":
           state.last_user_en = msg["content"]
    res_state = decide_scenario_strategy(state)
    assert res_state.cognitive.next_action == expected_answer

