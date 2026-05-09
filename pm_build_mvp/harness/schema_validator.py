# NOTE: Hard schema validation (raises on failure, triggers patch loop).
# Soft structural validation (warn-only) lives in
# workflows/planning_workflow.py (_validate_backlog). Keep enum values and
# required field rules in sync between these two locations when modifying either.
import json
from pydantic import BaseModel, ValidationError, Field
from typing import List, Literal

class TechStack(BaseModel):
    status: Literal["proposed", "pending", "locked"] = Field(..., description="Current status of the tech stack choice")
    frontend: List[str] = Field(..., description="List of frontend technologies")
    backend: List[str] = Field(..., description="List of backend technologies")
    database: List[str] = Field(..., description="Primary database systems")
    infra: List[str] = Field(..., description="Deployment and infrastructure tools")
    notes: str = Field(..., description="Reasoning behind the tech stack selection")

class TaskItem(BaseModel):
    id: str = Field(..., description="Unique task identifier, e.g., TASK-01")
    title: str = Field(..., description="Clear, actionable task title")
    owner: Literal["frontend", "backend", "fullstack", "qa"] = Field(..., description="Responsible role")
    priority: Literal["high", "medium", "low"] = Field(..., description="Execution priority")
    dependencies: List[str] = Field(..., description="IDs of tasks that must be completed first")
    acceptance_criteria: List[str] = Field(..., description="Strict checklist to verify task completion")
    files_to_create: List[str] = Field(..., description="Expected new files to be created")
    files_to_modify: List[str] = Field(..., description="Existing files to be modified")
    notes: str = Field(..., description="Additional context or edge cases")

class HandoffSchema(BaseModel):
    project_name: str = Field(..., description="Name of the MVP project")
    objective: str = Field(..., description="Core goal of this MVP")
    target_platform: Literal["web", "mobile", "api", "desktop"]
    tech_stack: TechStack
    tasks: List[TaskItem] = Field(..., description="List of broken-down development tasks")

def validate_handoff(json_content: str):
    """Validates handoff JSON and returns exact coordinates of failures."""
    try:
        data = json.loads(json_content)
        HandoffSchema(**data)
        return True, []
    except ValidationError as e:
        errors =[]
        for err in e.errors():
            path = ".".join([str(loc) for loc in err["loc"]])
            errors.append(f"{path}: {err['msg']}")
        return False, errors
    except Exception as e:
        return False, [str(e)]
