from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import SystemMessage

from LLM.make_llm import make_llm
from tools.llm_tools import TOOLS
from prompts.chat import CHAT_SYSTEM_PROMPT
from API.config import settings


LLM = make_llm(
    model=settings.DEFAULT_LLM_MODEL,
    temperature=settings.DEFAULT_TEMPERATURE,
)

PROMPT = ChatPromptTemplate.from_messages(
    [
        SystemMessage(content=CHAT_SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ]
)

AGENT = create_tool_calling_agent(
    llm=LLM,
    tools=TOOLS,
    prompt=PROMPT,
)

AGENT_EXECUTOR = AgentExecutor(
    agent=AGENT,
    tools=TOOLS,
    verbose=False,
    max_iterations=8,
    handle_parsing_errors=True,
)
