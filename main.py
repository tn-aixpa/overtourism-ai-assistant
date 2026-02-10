from app.agent.graph import app,intent_subgraph, interaction_subgraph, problem_subgraph, scenario_runner_subgraph

def test():
    state = {
        "message": [{"role": "user"/"assistant", "content": "Please, summarize the scenario results."}],
        "scenario_ids": ["sim1"],
        "data": None,
        "data_loaded_at": None,
        "next_action": None,
        "response": "",
    }

    result = app.invoke(state)
    print("\n=== AGENT RESPONSE ===")
    print(result["response"])

def draw():
    # Draw main graph
    print("=== Main Graph ===")
    print(app.get_graph().draw_mermaid())

    # Draw subgraphs
    print("=== Intent Subgraph ===")
    print(intent_subgraph.get_graph().draw_mermaid())

    print("=== Interaction Subgraph ===")
    print(interaction_subgraph.get_graph().draw_mermaid())

    print("=== Problem Subgraph ===")
    print(problem_subgraph.get_graph().draw_mermaid())

    print("=== Scenario Runner Subgraph ===")
    print(scenario_runner_subgraph.get_graph().draw_mermaid())

draw()
# use https://mermaid.live/ to visualize the output