from dotenv import load_dotenv
import streamlit as st
from langchain import hub
from langchain.agents import AgentExecutor, create_structured_chat_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import Tool
from langchain_google_genai import ChatGoogleGenerativeAI
from tools.time import get_current_time
from tools.wikipedia import search_wikipedia
from utils.mcp import AzureDevOpsMCPClient, MCP_COMMAND
from langchain.memory import ConversationSummaryBufferMemory
from langchain.schema import SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder # Import MessagesPlaceholder
from langchain_core.prompts import PromptTemplate
from langchain.agents import create_react_agent 

# Load environment variables from .env file
load_dotenv()

# 1. Inicialización del Cliente MCP y las Herramientas
mcp_client = AzureDevOpsMCPClient(command=MCP_COMMAND)

# 2. Define tus herramientas para el agente
mcp_tools = mcp_client.list_mcp_tools_structuredtool()

home_tools = [ get_current_time,search_wikipedia,]
home_tools_names = ["get_current_time", "search_wikipedia"]

tools = mcp_tools + home_tools
tools_names = home_tools_names


prompt = PromptTemplate.from_template("""
    Eres un asistente de chat amigable y servicial, especializado en ayudar con información sobre Azure DevOps. 
    Tu principal tarea es responder preguntas sobre el contenido de la **Wiki del proyecto "Prueba-MCP"** de Azure DevOps.

    Por favor, responde siempre en **español** y mantén un tono **simpático y conversacional*
                                      
    Tienes acceso a las siguientes herramientas:
    {tools}
    Aquí tienes una lista de los nombres de las herramientas disponibles para tu referencia: {tool_names}

                                      
    Para responder a las preguntas, utilizarás tus herramientas para **buscar en la Wiki de Azure DevOps**. Es fundamental que asumas que toda la información relevante para las preguntas de los usuarios se encuentra dentro del **proyecto "Prueba-MCP"** y puede estar en **cualquier página de su Wiki**.

    Cuando un usuario te pregunte algo, tu primer paso debe ser buscar la respuesta en la Wiki utilizando alguna de las herramientas de búsqueda de información que tengas disponible para la Wiki de Azure DevOps. Si la información no está directamente disponible en la Wiki o si necesitas más detalles, puedes solicitar aclaraciones al usuario o sugerirle que la información podría no estar documentada.

    Si el usuario te pide algo que no está relacionado con la Wiki de Azure DevOps o las herramientas que tienes para interactuar con Azure DevOps, hazle saber amablemente que tu función principal es ayudarte con la Wiki y Azure DevOps.

    Pregunta del usuario: {input}
    {agent_scratchpad}
    """
)



# Initialize a model
llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash")

# Inicializa la memoria de conversación
if "memory" not in st.session_state:
    st.session_state.memory = ConversationSummaryBufferMemory(
        llm=llm,
        memory_key="chat_history",
        return_messages=True,
        max_token_limit=1000
    )
    st.session_state.memory.chat_memory.add_ai_message("¡Hola! Soy tu asistente de Azure DevOps. ¿En qué puedo ayudarte hoy?")



# Crea el agente y el AgentExecutor 
agent = create_react_agent(llm=llm, tools=tools, prompt=prompt)
agent_executor = AgentExecutor(
    agent=agent, 
    tools=tools, 
    memory=st.session_state.memory,
    verbose=True, 
    handle_parsing_errors=True
    )

# --- Interfaz de Usuario con Streamlit ---
st.set_page_config(page_title="ChatBot", layout="wide")
st.title("ChatBot Azure DevOps")
st.markdown("""
Bienvenido! Este chatbot fue desarrollado para realizar consultas sobre la wiki de AzureDevOps
            Langchain + MCP + Azure DevOps
""")

placeholder = st.empty()

with placeholder.container():
    # Muestra el historial de conversación en la interfaz
    # Aquí debes iterar sobre st.session_state.memory.chat_history (que es una lista de mensajes)
    for message in st.session_state.memory.chat_memory.messages:
        if isinstance(message, HumanMessage):
            with st.chat_message("user"):
                st.markdown(message.content)
        elif isinstance(message, AIMessage):
            with st.chat_message("assistant"):
                st.markdown(message.content)


# Usa st.chat_input para la entrada de usuario
user_query = st.chat_input("¿En qué puedo ayudarte con Azure DevOps?")

if user_query: # Este bloque se ejecuta cuando el usuario presiona Enter
    # Agrega la pregunta del usuario al historial usando .chat_memory
    st.session_state.memory.chat_memory.add_user_message(user_query)

    # Muestra la pregunta del usuario inmediatamente
    with st.chat_message("user"):
        st.markdown(user_query)

    with st.chat_message("assistant"):
        with st.spinner("Pensando..."):
            try:
                # Crea una instancia del callback handler para la visualización de herramientas
                #tool_handler = StreamlitToolCallbackHandler(st.empty())

                # Invoca el agente
                response = agent_executor.invoke(
                    {"input": user_query}, 
                    {"agent_scratchpad": ['']}
                )

                # Muestra la respuesta del agente
                st.markdown(response["output"])
                # Agrega la respuesta del agente al historial usando .chat_memory
                st.session_state.memory.chat_memory.add_ai_message(response["output"])

            except Exception as e:
                st.error(f"Ocurrió un error al procesar tu consulta: {e}")
                # Agrega el mensaje de error al historial usando .chat_memory
                st.session_state.memory.chat_memory.add_ai_message(f"Lo siento, ocurrió un error: {e}")
                st.info("Asegúrate de que tus preguntas coincidan con los datos y el esquema de la base de datos.")

st.sidebar.markdown("")
if st.sidebar.button("🧹 Borrar Historial"):
    st.session_state.memory.chat_memory.clear()
    placeholder.empty()
