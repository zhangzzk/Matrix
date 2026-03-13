from __future__ import annotations

import json
from typing import Type, TypeVar

from pydantic import BaseModel, ValidationError

TModel = TypeVar("TModel", bound=BaseModel)


class ExtractionValidationError(ValueError):
    pass


class ExtractionValidator:
    def validate_json_text(self, payload: str, schema: Type[TModel]) -> TModel:
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ExtractionValidationError("Invalid JSON extraction payload") from exc

        try:
            return schema.model_validate(parsed)
        except ValidationError as exc:
            raise ExtractionValidationError("Extraction payload failed schema validation") from exc

    def validate_payload(self, payload: object, schema: Type[TModel]) -> TModel:
        try:
            return schema.model_validate(payload)
        except ValidationError as exc:
            raise ExtractionValidationError("Extraction payload failed schema validation") from exc
