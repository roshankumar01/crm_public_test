from dataclasses import dataclass
from functools import lru_cache
from importlib import import_module
from pathlib import Path
from pkgutil import iter_modules
from typing import Callable

import pandas as pd


@dataclass(frozen=True)
class ImporterDefinition:
    import_type: str
    display_name: str
    description: str
    columns: tuple[dict, ...]
    validate_columns: Callable[[pd.DataFrame], None]
    parse_row: Callable


EXCLUDED_MODULES = {"__init__", "common", "registry", "service"}


@lru_cache(maxsize=1)
def discover_importers():
    importer_directory = Path(__file__).parent
    discovered = {}

    for module_info in iter_modules([str(importer_directory)]):
        module_name = module_info.name
        if module_name in EXCLUDED_MODULES or module_name.startswith("_"):
            continue

        module = import_module("app.services.importers." + module_name)
        if not hasattr(module, "IMPORT_TYPE"):
            continue

        required = ["DISPLAY_NAME", "DESCRIPTION", "validate_columns", "parse_row"]
        missing = [name for name in required if not hasattr(module, name)]
        if missing:
            raise RuntimeError(f"Importer '{module_name}' is missing: {', '.join(missing)}")

        import_type = module.IMPORT_TYPE.strip().upper()
        if import_type in discovered:
            raise RuntimeError(f"Duplicate importer type: {import_type}")

        discovered[import_type] = ImporterDefinition(
            import_type=import_type,
            display_name=module.DISPLAY_NAME,
            description=module.DESCRIPTION,
            columns=tuple(getattr(module, "COLUMNS", ())),
            validate_columns=module.validate_columns,
            parse_row=module.parse_row,
        )

    return discovered


def get_importer(import_type: str):
    normalized = import_type.strip().upper()
    importers = discover_importers()
    importer = importers.get(normalized)
    if not importer:
        raise ValueError(
            f"Unknown import type '{normalized}'. Available types: {', '.join(sorted(importers))}"
        )
    return importer


def list_importers():
    return sorted(discover_importers().values(), key=lambda item: item.display_name.lower())
