from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage
from typing import List
from store.SessionStore import ChatMessage


def to_lc_messages(msgs: List[ChatMessage]) -> List[BaseMessage]:
    out: List[BaseMessage] = []
    for m in msgs:
        if m.role == "system":
            out.append(SystemMessage(content=m.content))
        elif m.role == "user":
            out.append(HumanMessage(content=m.content))
        else:
            out.append(AIMessage(content=m.content))
    return out