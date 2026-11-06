from langgraph.graph import END, START, StateGraph

from services.graph.nodes.agent import agent, tools
from services.graph.nodes.suggest import suggest
from services.graph.state import AgentState


def _after_agent(state: AgentState) -> str:
    return "tools" if state["pending"] else "suggest"


def graph_builder():
    """
    agent ⇄ tools until the model answers (the agent caps the rounds), then suggest
    offers follow-up questions.
    """
    g = StateGraph(AgentState)
    g.add_node("agent", agent)
    g.add_node("tools", tools)
    g.add_node("suggest", suggest)

    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", _after_agent, {"tools": "tools", "suggest": "suggest"})
    g.add_edge("tools", "agent")
    g.add_edge("suggest", END)
    return g.compile()
