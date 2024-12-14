from key_vaults import SecretManager

from typing import Annotated
from typing import Literal
from typing_extensions import TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

from langchain_openai import AzureChatOpenAI

from langchain_core.messages import ToolMessage

import json
import os
from dotenv import load_dotenv

# Cargar las variables del archivo .env en el entorno
load_dotenv()

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

class BasicToolNode:
    """A node that runs the tools requested in the last AIMessage."""

    def __init__(self, tools: list) -> None:
        self.tools_by_name = {tool.name: tool for tool in tools}

    def __call__(self, inputs: dict):
        if messages := inputs.get("messages", []):
            message = messages[-1]
        else:
            raise ValueError("No message found in input")
        outputs = []
        for tool_call in message.tool_calls:
            tool_result = self.tools_by_name[tool_call["name"]].invoke(
                tool_call["args"]
            )
            outputs.append(
                ToolMessage(
                    content=json.dumps(tool_result),
                    name=tool_call["name"],
                    tool_call_id=tool_call["id"],
                )
            )
        return {"messages": outputs}

class State(TypedDict):
    # Messages have the type "list". The `add_messages` function
    # in the annotation defines how this state key should be updated
    # (in this case, it appends messages to the list, rather than overwriting them)
    messages: Annotated[list, add_messages]

def route_tools(state: State):
    """
    Esta función se utiliza en una arista condicional (conditional_edge) del grafo.
    Su objetivo es decidir a qué nodo dirigirse a continuación basándose en el
    último mensaje del estado. Si el mensaje tiene llamadas a herramientas (tool calls),
    se redirige al nodo "tools". Si no, se dirige a END.
    """

    # Primero verifica si 'state' es una lista. Si lo es, significa que el último
    # mensaje está al final de la lista.
    if isinstance(state, list):
        ai_message = state[-1]
    # Si 'state' no es una lista, entonces intenta obtener la lista de mensajes
    # del diccionario 'state'. Usa la sintaxis ':=' (operador walrus) para asignar
    # la lista a 'messages'. Si 'messages' existe, toma el último mensaje.
    elif messages := state.get("messages", []):
        ai_message = messages[-1]
    else:
        # Si no se cumple ninguna de las condiciones anteriores, significa que
        # no hay mensajes disponibles, así que se lanza un error.
        raise ValueError(f"No messages found in input state to tool_edge: {state}")

    # Ahora que tenemos el último mensaje, verificamos si el mensaje tiene el
    # atributo 'tool_calls' y si esta lista no está vacía.
    # hasattr(ai_message, "tool_calls") verifica si el atributo existe.
    # len(ai_message.tool_calls) > 0 verifica que haya al menos una llamada a herramienta.
    if hasattr(ai_message, "tool_calls") and len(ai_message.tool_calls) > 0:
        # Si el mensaje tiene tool_calls, retornamos el nombre del nodo "tools"
        # indicando que el flujo debe ir a ese nodo.
        return "tools"

    # Si no hay tool_calls, el flujo se dirige al nodo END, finalizando el proceso.
    return END

#Add Chatbot
def chatbot(state: State):
    # return {"messages": [llm.invoke(state["messages"])]}
    return {"messages": [llm_with_tools.invoke(state["messages"])]}

tool = TavilySearchResults(max_results=2, tavily_api_key=tavily_api_key)
tools = [tool]
# tool.invoke("What's a 'node' in LangGraph?")

tool_node = BasicToolNode(tools=[tool])

# Modification: tell the LLM which tools it can call
llm_with_tools = llm.bind_tools(tools)

graph_builder = StateGraph(State)

graph_builder.add_node("chatbot", chatbot)

# The `tools_condition` function returns "tools" if the chatbot asks to use a tool, and "END" if
# it is fine directly responding. This conditional routing defines the main agent loop.
graph_builder.add_conditional_edges(
    "chatbot",
    route_tools,
    # The following dictionary lets you tell the graph to interpret the condition's outputs as a specific node
    # It defaults to the identity function, but if you
    # want to use a node named something else apart from "tools",
    # You can update the value of the dictionary to something else
    # e.g., "tools": "my_tools"
    {"tools": "tools", END: END},
)

# Registrar el nodo "tools" en el grafo
graph_builder.add_node("tools", tool_node)

# Any time a tool is called, we return to the chatbot to decide the next step
graph_builder.add_edge("tools", "chatbot")
graph_builder.add_edge(START, "chatbot")

#to be able to run our graph
graph = graph_builder.compile()


#to run the chatbot:

def stream_graph_updates(user_input: str):
    for event in graph.stream(
        {"messages": [("user", user_input)]}):
        for value in event.values():
            print("Assistant:", value["messages"][-1].content)


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