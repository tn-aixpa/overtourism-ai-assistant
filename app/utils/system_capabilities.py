SYSTEM_DESCRIPTION = """
The system supports analysis and decision-making for tourism in Trentino.
The analysis of phenomenon is supported by two main things.

1. The analysis of territorial indexes that represent different touristic metrics in the whole Trentino region.
2. The analysis of what-if scenarios to solve critical problems in specific locations.

# For 1 typical workflows include

a. Checking on the map which area are more affected by a certain index
b. Show the trend of a certain index using graphs or maps

# For 2 typical workflows include

a. Explore existing proposals and scenarios to see how effective they are to solve a certain problem
b. Create a new proposal and associated scenarios to try to solve a problem in a specific location

"""

# User-facing description of the assistant's capability levels ("agents").
# Returned by get_system_capabilities(topic="agents") and relayed to the user,
# so it must describe what each level does in plain terms and must stay in sync
# with AgentTier (app/agent/state.py), ToolDefinition.agent_tier and the
# per-tier policies in app/prompts/answer_generation.py (_reasoning_policy).
# Italian names are the ones shown in the UI selector.
AGENTS_DESCRIPTION = """
The assistant works at different capability levels, called "agents". Each level
adds freedom to the one before it, but also moves further away from verified
platform data. The user can pick a level explicitly, or leave the selector on
"Automatico".

1. Esecutore (executor) - the strictest level. It only retrieves and shows
   what is stored on the platform, without interpreting it: lists and details of
   problems, proposals and scenarios, the available territories, glossary
   definitions, territorial indexes (list, maps, charts, values for given
   municipalities or thresholds), and the tunable simulation parameters. Users who
   can edit data can also create, modify or delete problems, proposals and
   scenarios, always after an explicit confirmation. It does not explain causes,
   draw conclusions or suggest strategies.

2. Operativo (operative) - everything the Esecutore does, plus it can analyse
   data that is already on the platform: for example it evaluates and
   interprets the results of a scenario (sustainability, constraints, trade-offs),
   compares scenarios and comments on trends. Every observation must be traceable
   to platform data. It still does not propose strategies or interventions of its
   own.

3. Metodologico (methodological) - explains HOW to work, based on the platform's
   reference workflow documents: how to model a destination, how the
   Problem -> Proposal -> Scenario chain works, how to design or validate a new
   territorial index. It can suggest the sequence of steps to follow and explain why
   each step matters, but it does not invent the content of a specific strategy or
   proposal. Available to users who can edit data.

4. Esplorativo (exploitative) - the most open level. It can reason freely, put
   forward its own ideas, strategies and solutions, and search the web for external
   information. Its answers are NOT checked against platform data, so they should be
   treated as suggestions to verify. It is limited to tourism management, needs the
   user's one-time consent (renewed after 24 hours), and is available to users who
   can edit data.

5. Automatico (automatic) - not a separate level but the default mode: the
   assistant chooses by itself. It starts from the strictest level and moves up
   only when the question needs it (for example from Esecutore to Operativo to
   analyse a scenario, to Metodologico for a "how do I..." question, to Esplorativo
   when nothing grounded on the platform can answer). The level used is always the
   highest one needed for that answer.

When a methodological question is asked, the Metodologico level is preferred; the
Esplorativo level is used only if the reference documents do not cover the
question.
"""
