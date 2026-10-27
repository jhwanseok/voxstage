"""YAML reading and writing for the studio. Writing uses one fixed style (ADR 0013: parsed equality, not bytes)."""

from __future__ import annotations

import yaml


class _Loader(yaml.SafeLoader):
    """Like safe_load, except that timestamps stay strings: JSON columns cannot hold date objects."""


_Loader.yaml_implicit_resolvers = {
    k: [(tag, rx) for tag, rx in v if tag != "tag:yaml.org,2002:timestamp"]
    for k, v in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def load(text: str):
    return yaml.load(text, Loader=_Loader)


def dump(data) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=None, width=120)
