"""The codebase model: plain data the town is built from."""

import json
from dataclasses import asdict, dataclass, field


@dataclass
class Module:
    id: str
    district: str
    kind: str
    loc: int = 0
    complexity: int = 0
    exports: list = field(default_factory=list)
    notes: int = 0
    is_entry: bool = False
    parse_error: str | None = None
    churn: int = 0
    mentioned: bool = False
    tested_by: list = field(default_factory=list)
    lang: str = "python"
    depth: str = "full"
    is_package: bool = False
    public: bool = False
    inline_tests: bool = False
    burns: bool = True
    members: list = field(default_factory=list)
    functions: list = field(default_factory=list)


@dataclass
class Model:
    repo: str
    modules: dict = field(default_factory=dict)
    edges: dict = field(default_factory=dict)
    externals: dict = field(default_factory=dict)
    renames: dict = field(default_factory=dict)

    def of_kind(self, kind):
        return [m for _, m in sorted(self.modules.items()) if m.kind == kind]

    def importers(self):
        found = {}
        for src, dst in sorted(self.edges):
            found.setdefault(dst, []).append(src)
        return found

    def to_dict(self):
        return {
            "repo": self.repo,
            "modules": [asdict(m) for _, m in sorted(self.modules.items())],
            "edges": [[s, d, n] for (s, d), n in sorted(self.edges.items())],
            "externals": {k: sorted(v) for k, v in sorted(self.externals.items())},
            "renames": dict(sorted(self.renames.items())),
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            repo=data["repo"],
            modules={m["id"]: Module(**{**m, "functions": [tuple(f) for f in m.get("functions", [])]})
                     for m in data["modules"]},
            edges={(s, d): n for s, d, n in data["edges"]},
            externals={k: list(v) for k, v in data["externals"].items()},
            renames=dict(data.get("renames", {})),
        )

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=1, sort_keys=True)

    @classmethod
    def load(cls, path):
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))
