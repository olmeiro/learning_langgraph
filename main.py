from key_vaults import SecretManager

from typing import Annotated
from typing_extensions import TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.memory import MemorySaver


from langchain_openai import AzureChatOpenAI

import os
from dotenv import load_dotenv

# Cargar las variables del archivo .env en el entorno
load_dotenv()

# Add memory
memory = MemorySaver()

# Ahora puedes obtener la clave desde el entorno
tavily_api_key = os.getenv("TAVILY_API_KEY")

secrets = SecretManager()

endpoint = secrets.get_secret("smart-openai-endpoint")
api_key = secrets.get_secret("smart-openai-key")

# define the tool:
from langchain_community.tools.tavily_search import TavilySearchResults

llm: AzureChatOpenAI = AzureChatOpenAI(
    openai_api_version = secrets.get_secret("smart-openai-api-version"),
    azure_deployment="gpt-4o",
    temperature=0,
    api_key=secrets.get_secret("smart-openai-key"),
    azure_endpoint=secrets.get_secret("smart-openai-endpoint"),
    max_tokens=1500
)


class State(TypedDict):
    # Messages have the type "list". The `add_messages` function
    # in the annotation defines how this state key should be updated
    # (in this case, it appends messages to the list, rather than overwriting them)
    messages: Annotated[list, add_messages]

graph_builder = StateGraph(State)

tool = TavilySearchResults(max_results=2, tavily_api_key=tavily_api_key)
tools = [tool]

# Modification: tell the LLM which tools it can call
llm_with_tools = llm.bind_tools(tools)


#Add Chatbot
def chatbot(state: State):
    return {"messages": [llm_with_tools.invoke(state["messages"])]}


graph_builder.add_node("chatbot", chatbot)

tool_node = ToolNode(tools=[tool])
# Registrar el nodo "tools" en el grafo
graph_builder.add_node("tools", tool_node)


# The `tools_condition` function returns "tools" if the chatbot asks to use a tool, and "END" if
# it is fine directly responding. This conditional routing defines the main agent loop.
graph_builder.add_conditional_edges(
    "chatbot",
    tools_condition,
)

# Any time a tool is called, we return to the chatbot to decide the next step
graph_builder.add_edge("tools", "chatbot")
graph_builder.add_edge(START, "chatbot")

#to be able to run our graph with checkpointer memory:
graph = graph_builder.compile(checkpointer=memory)

#Pick a thread to use as the key for this conversation.
config = {"configurable": {"thread_id": "1"}}

#to run the chatbot:
def stream_graph_updates(user_input: str):
    for event in graph.stream(
            {
                "messages": [("user", user_input)]
            },
            config,
            stream_mode="values"
        ):

        for value in event.values():
            # print("DEBUG - Value:", value)  # Inspeccionar el contenido completo de `value`

            # Verificar si `value` es una lista
            if isinstance(value, list):
                # Iterar sobre cada mensaje en la lista
                for message in value:
                    # Verificar si el mensaje tiene el atributo `content`
                    if hasattr(message, "content"):
                        print("Assistant:", message.content)
                    else:
                        print("Assistant: Mensaje no tiene contenido")
            else:
                print("Assistant: Value no es una lista")


while True:
    try:
        user_input = input("User: ")
        if user_input.lower() in ["quit", "exit", "q"]:
            print("Goodbye!")
            break

        stream_graph_updates(user_input)

    except:
        # fallback if input() is not available
        user_input = "What do you know about LangGraph?"
        print("User: " + user_input)
        stream_graph_updates(user_input)
        break