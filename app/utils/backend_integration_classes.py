from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class FieldSpec:
    description: str
    required: bool

@dataclass(frozen=True)
class ProblemInfoSchema:
    problem_title: FieldSpec
    objectives: FieldSpec
    problem_description: FieldSpec
    available_subsystems: FieldSpec
    additional_data: FieldSpec

    @staticmethod
    def default() -> "ProblemInfoSchema":
        return ProblemInfoSchema(
            problem_title = FieldSpec("The title of the problem", True),
            objectives = FieldSpec("The objectives of the problem", True),
            problem_description = FieldSpec("A detailed description of the problem", True),
            available_subsystems = FieldSpec("The available subsystems", False),
            additional_data = FieldSpec("Additional data", False),
        )
    
@dataclass(frozen=True)
class ScenarioInfoSchema:
    title: FieldSpec
    description: FieldSpec
    indexes_to_change: FieldSpec

    @staticmethod
    def default() -> "ScenarioInfoSchema":
        return ScenarioInfoSchema (
            title = FieldSpec("The title of the scenario", True),
            description = FieldSpec("Describes the proposal", True),
            indexes_to_change = FieldSpec("Indexes of simulation to change", True),
        )