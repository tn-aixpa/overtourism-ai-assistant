from dataclasses import dataclass, fields
from typing import Any, Dict, Optional


# -------------------------
# FIELD SPEC (schema layer)
# -------------------------

@dataclass(frozen=True)
class FieldSpec:
    description: str
    required: bool = False


# -------------------------
# BASE SCHEMA (generic)
# -------------------------

@dataclass(frozen=True)
class BaseSchema:
    def validate(self, data: Dict[str, Any]) -> None:
        missing = []
        for f in fields(self):
            spec: FieldSpec = getattr(self, f.name)
            if spec.required and (f.name not in data or data[f.name] in [None, "", []]):
                missing.append(f.name)
        if missing:
            raise ValueError(f"Missing required fields: {missing}")

    def format_structure(self) -> str:
        lines = []
        for f in fields(self):
            spec: FieldSpec = getattr(self, f.name)
            tag = "[REQUIRED]" if spec.required else "[OPTIONAL]"
            lines.append(f"- **{f.name}** {tag}: {spec.description}")
        return "\n".join(lines)

class PrettyFormatMixin:
    def format_fields(self) -> str:
        lines = []
        for f in fields(self):
            value = getattr(self, f.name)

            # Skip empty values
            if value in [None, "", [], {}]:
                continue

            # Format lists nicely
            if isinstance(value, list):
                formatted_value = ", ".join(map(str, value))
            # Format dicts nicely
            elif isinstance(value, dict):
                formatted_value = ", ".join(f"{k}: {v}" for k, v in value.items())
            else:
                formatted_value = str(value)

            lines.append(f"- **{f.name}**: {formatted_value}")

        return "\n".join(lines)

# -------------------------
# DATA MODELS (data layer)
# -------------------------

@dataclass
class ProblemInfo(PrettyFormatMixin):
    problem_title: str
    objectives: str
    problem_description: str
    available_subsystems: Optional[list[str]] = None
    additional_data: Optional[str] = None


@dataclass
class ProposalInfo(PrettyFormatMixin):
    title: str
    description: str
    related_data: Optional[str] = None
    context_conditions: Optional[str] = None
    potential_impact: Optional[str] = None
    connected_scenarios: Optional[list[str]] = None


@dataclass
class ScenarioInfo(PrettyFormatMixin):
    title: str
    description: str
    indexes_to_change: Dict[str, str]


# -------------------------
# SCHEMA DEFINITIONS
# -------------------------

@dataclass(frozen=True)
class ProblemInfoSchema(BaseSchema):
    problem_title: FieldSpec
    objectives: FieldSpec
    problem_description: FieldSpec
    available_subsystems: FieldSpec
    additional_data: FieldSpec

    @staticmethod
    def default() -> "ProblemInfoSchema":
        return ProblemInfoSchema(
            problem_title=FieldSpec("The title of the problem", True),
            objectives=FieldSpec("The main objectives we want to achieve", True),
            problem_description=FieldSpec(
                "Detailed problem description, useful for generating solutions", True
            ),
            available_subsystems=FieldSpec(
                "Available subsystems [parking, beach, restaurants, hotels]", False
            ),
            additional_data=FieldSpec(
                "Links or references to supporting material", False
            ),
        )


@dataclass(frozen=True)
class ProposalInfoSchema(BaseSchema):
    title: FieldSpec
    description: FieldSpec
    related_data: FieldSpec
    context_conditions: FieldSpec
    potential_impact: FieldSpec
    connected_scenarios: FieldSpec

    @staticmethod
    def default() -> "ProposalInfoSchema":
        return ProposalInfoSchema(
            title=FieldSpec("The title of the proposal", True),
            description=FieldSpec(
                "Description highlighting key elements to define scenarios", True
            ),
            related_data=FieldSpec(
                "Links or references supporting the proposal", False
            ),
            context_conditions=FieldSpec(
                "External factors (seasonality, weather, events, etc.)", False
            ),
            potential_impact=FieldSpec(
                "Impact description with metrics (e.g. reduce pollution by 20%)",
                False,
            ),
            connected_scenarios=FieldSpec(
                "List of connected scenarios", False
            ),
        )


@dataclass(frozen=True)
class ScenarioInfoSchema(BaseSchema):
    title: FieldSpec
    description: FieldSpec
    indexes_to_change: FieldSpec

    @staticmethod
    def default() -> "ScenarioInfoSchema":
        return ScenarioInfoSchema(
            title=FieldSpec("The title of the scenario", True),
            description=FieldSpec("Scenario description", True),
            indexes_to_change=FieldSpec(
                "Simulation indexes to modify", True
            ),
        )

# -------------------------
# GENERIC BUILDER
# -------------------------

def build_schema_data(schema: BaseSchema, data: Dict[str, Any], cls):
    schema.validate(data)
    return cls(**data)