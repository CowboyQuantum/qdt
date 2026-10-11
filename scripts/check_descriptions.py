"""Every pydantic field in qdt-schemas must carry a description (schema docs are generated from them)."""
import importlib
import pkgutil
import sys

from pydantic import BaseModel

import qdt_schemas

bad = []
for m in pkgutil.walk_packages(qdt_schemas.__path__, "qdt_schemas."):
    mod = importlib.import_module(m.name)
    for name, obj in vars(mod).items():
        if isinstance(obj, type) and issubclass(obj, BaseModel) and obj.__module__ == mod.__name__:
            for fname, f in obj.model_fields.items():
                if not f.description:
                    bad.append(f"{mod.__name__}.{name}.{fname}")
if bad:
    print("check_descriptions: FAIL — fields without description:\n  " + "\n  ".join(bad))
    sys.exit(1)
print("check_descriptions: OK")
