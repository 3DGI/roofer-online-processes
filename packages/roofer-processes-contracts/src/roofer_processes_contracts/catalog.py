"""Public production catalog and transport-independent validation."""

from copy import deepcopy
from typing import Any

from ogc_processes.interfaces import ContractViolation
from ogc_processes.models import (
    InputDescription,
    JobControlOption,
    OutputDescription,
    ProcessDescription,
    ProcessSummary,
    Results,
    TransmissionMode,
)
from pydantic import ValidationError

from roofer_processes_contracts.models import PROCESS_ID, BuildingModel, ReconstructionInputs


class RooferCatalog:
    def __init__(self) -> None:
        schema = ReconstructionInputs.model_json_schema(by_alias=True)
        self._description = ProcessDescription(
            id=PROCESS_ID,
            title="Reconstruct buildings",
            description="Prepare remote LAS/LAZ files, reconstruct selected BAG buildings, and export models.",
            version="2.0.0",
            keywords=["BAG", "point cloud", "reconstruction"],
            inputsSchema=schema,
            inputs={
                name: InputDescription(
                    title=name,
                    schema={**field, "$defs": deepcopy(schema.get("$defs", {}))},
                    minOccurs=1 if name in schema.get("required", []) else 0,
                    maxOccurs=1,
                )
                for name, field in schema["properties"].items()
            },
            outputs={
                "building_model": OutputDescription(title="Building model", schema=BuildingModel.model_json_schema())
            },
            jobControlOptions=[JobControlOption.execute_async],
            outputTransmission=[TransmissionMode.value],
        )

    def list_processes(self) -> list[ProcessSummary]:
        return [ProcessSummary.model_validate(self._description.model_dump())]

    def get_process(self, process_id: str) -> ProcessDescription | None:
        return self._description.model_copy(deep=True) if process_id == PROCESS_ID else None


class RooferContractValidator:
    def validate_inputs(self, process_id: str, inputs: dict[str, Any]) -> dict[str, Any]:
        if process_id != PROCESS_ID:
            raise ContractViolation("Unknown process")
        try:
            return ReconstructionInputs.model_validate(inputs).model_dump(mode="json", by_alias=True, exclude_none=True)
        except (ValidationError, ValueError, TypeError) as exc:
            raise ContractViolation("Invalid reconstruction inputs") from exc

    def validate_results(self, process_id: str, results: Results) -> Results:
        if process_id != PROCESS_ID or set(results.outputs) != {"building_model"}:
            raise ContractViolation("Invalid reconstruction results")
        try:
            model = BuildingModel.model_validate(results.outputs["building_model"])
        except (ValidationError, ValueError, TypeError) as exc:
            raise ContractViolation("Invalid reconstruction results") from exc
        return Results(outputs={"building_model": model.model_dump(mode="json", exclude_none=True)})
