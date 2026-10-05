"""Dependency layers: foundations at the back (row 0), what builds on them in front."""

import json
import os


def strongly_connected(nodes, succ):
    """Tarjan's algorithm without recursion. Components come out sinks first."""
    index, low, on_stack, stack, components = {}, {}, set(), [], []

    def visit(node):
        index[node] = low[node] = len(index)
        stack.append(node)
        on_stack.add(node)
        return node, iter(sorted(succ.get(node, ())))

    for start in sorted(nodes):
        if start in index:
            continue
        work = [visit(start)]
        while work:
            node, children = work[-1]
            for child in children:
                if child not in index:
                    work.append(visit(child))
                    break
                if child in on_stack:
                    low[node] = min(low[node], index[child])
            else:
                work.pop()
                if work:
                    parent = work[-1][0]
                    low[parent] = min(low[parent], low[node])
                if low[node] == index[node]:
                    component = []
                    while True:
                        member = stack.pop()
                        on_stack.discard(member)
                        component.append(member)
                        if member == node:
                            break
                    components.append(sorted(component))
    return components


def layer_of(nodes, succ):
    """Layer = longest import path down to a module that imports nothing here."""
    keep = set(nodes)
    succ = {n: {c for c in succ.get(n, ()) if c in keep} for n in keep}
    components = strongly_connected(keep, succ)
    component_of = {n: i for i, comp in enumerate(components) for n in comp}
    component_layer = []
    for i, comp in enumerate(components):
        below = [component_layer[component_of[c]]
                 for n in comp for c in succ[n] if component_of[c] != i]
        component_layer.append(1 + max(below) if below else 0)
    found = {n: component_layer[component_of[n]] for n in keep}
    return found, sorted(c for c in components if len(c) > 1)


def module_graph(model, district=None):
    nodes = [m.id for m in model.of_kind("source") if district in (None, m.district)]
    keep = set(nodes)
    succ = {}
    for src, dst in model.edges:
        if src in keep and dst in keep:
            succ.setdefault(src, set()).add(dst)
    return nodes, succ


def district_graph(model):
    sources = model.of_kind("source")
    nodes = sorted({m.district for m in sources})
    succ = {}
    for src, dst in model.edges:
        a, b = model.modules[src].district, model.modules[dst].district
        if a != b:
            succ.setdefault(a, set()).add(b)
    return nodes, succ


def cycles(model):
    return layer_of(*module_graph(model))[1]


class Rows:
    def __init__(self, districts=None, modules=None):
        self.districts = dict(districts or {})
        self.modules = dict(modules or {})

    def update(self, model):
        for old, new in sorted(model.renames.items()):
            if old in self.modules and new not in self.modules:
                self.modules[new] = self.modules.pop(old)
        for name, row in sorted(layer_of(*district_graph(model))[0].items()):
            self.districts.setdefault(name, row)
        for district in sorted({m.district for m in model.of_kind("source")}):
            for name, row in sorted(layer_of(*module_graph(model, district))[0].items()):
                self.modules.setdefault(name, row)
        return self

    def is_backwards(self, model, src, dst):
        """True when an import reaches forward, from a foundation to what sits in front."""
        a, b = model.modules[src], model.modules[dst]
        if a.district != b.district:
            here, there = self.districts.get(a.district), self.districts.get(b.district)
        else:
            here, there = self.modules.get(src), self.modules.get(dst)
        return here is not None and there is not None and there > here

    def save(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"districts": self.districts, "modules": self.modules}, f,
                      indent=1, sort_keys=True)

    @classmethod
    def load(cls, path):
        if not os.path.exists(path):
            return cls()
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls(data.get("districts"), data.get("modules"))
