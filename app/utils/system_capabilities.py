SYSTEM_DESCRIPTION = """
The system supports analysis and decision-making for tourism in Trentino.
The analysis of phenomenon is supported by two main things.

1. The analysis of touristic phenomenon in the whole Trentino region.
2. The analysis of what-if scenarios to solve critical problems in specific locations.

# For 1 typical workflows include

a. Checking on the map which area are more affected by a certain indicator
b. Show the trend of a certain indicator using graphs or maps

# For 2 typical workflows include

1. **Explore**: call list_available_scenarios → get_context_details → analyze_scenario_results
2. **Create a proposal**: set a problem context → gather the proposal details → confirm → create_new_proposal
3. **Create a scenario**: get_configuration_parameters (to resolve/compute the desired parameter
   values) → create_new_temp_scenario (previews the simulated result, no confirmation needed) →
   once the user is happy with the preview → confirm → create_new_scenario (saves it permanently)

"""
