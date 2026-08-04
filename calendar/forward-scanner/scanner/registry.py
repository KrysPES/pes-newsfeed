"""The source registry.

registry.json rather than registry.yaml. The brief allows an equivalent, and a
YAML reader is not in the standard library, so JSON keeps the scanner to
standard library plus requests.

Every source in section 2 has an entry. resolved sources have a parser and
produce rows. unresolved sources produce nothing and are re-probed each weekly
run so the verdict stays current rather than inherited.
"""

import json

from . import config


def load(path=None):
    path = path or config.REGISTRY_PATH
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def save(registry, path=None):
    path = path or config.REGISTRY_PATH
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(registry, handle, indent=2, ensure_ascii=False, sort_keys=False)
        handle.write("\n")


def resolved(registry):
    return [entry for entry in registry["sources"] if entry["verdict"] == "resolved"]


def unresolved(registry):
    return [entry for entry in registry["sources"] if entry["verdict"] != "resolved"]


def by_id(registry, source_id):
    for entry in registry["sources"]:
        if entry["id"] == source_id:
            return entry
    return None
