"""A tiny state-graph engine with human-in-the-loop interrupts.

Same ideas as LangGraph — nodes that read/update shared state and return the name of the next node, plus an
INTERRUPT that pauses the run until a human answers — in ~30 lines you can read and test. `langgraph_app.py`
shows the identical graph built with the real LangGraph library.
"""
from .. import observability

END = "__end__"
INTERRUPT = "__interrupt__"


class Graph:
    def __init__(self):
        self.nodes: dict = {}

    def node(self, fn):
        self.nodes[fn.__name__] = fn
        return fn

    def run(self, entry: str, ctx, state: dict, max_steps: int = 20) -> str:
        cur, steps = entry, 0
        while cur not in (END, INTERRUPT):
            steps += 1
            if steps > max_steps:
                raise RuntimeError("agent graph did not terminate")
            with observability.span(f"node:{cur}"):
                cur = self.nodes[cur](ctx, state)
        return cur
