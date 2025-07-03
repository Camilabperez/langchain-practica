from dotenv import load_dotenv
import streamlit as st
from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from tools.time import get_current_time
from tools.wikipedia import search_wikipedia
from utils.mcp import AzureDevOpsMCPClient, MCP_COMMAND
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder 
from langchain.memory import ConversationBufferMemory

# Load environment variables from .env file
load_dotenv()

# 1. Inicialización del Cliente MCP y las Herramientas
mcp_client = AzureDevOpsMCPClient(command=MCP_COMMAND)

# 2. Define tus herramientas para el agente
mcp_tools_names, mcp_tools = mcp_client.list_mcp_tools_structuredtool()

home_tools = [get_current_time, search_wikipedia]
home_tools_names = ["get_current_time", "search_wikipedia"]

tools = mcp_tools + home_tools
tool_names = mcp_tools_names + home_tools_names

# Prompt corregido para ReAct Agent
prompt = ChatPromptTemplate.from_messages([
    ("system", """
Eres un asistente de chat amable y servicial que responde en **español**. Estás especializado en asistir con información sobre Azure DevOps, específicamente del Wiki del proyecto "Prueba-MCP".

Tienes acceso a las siguientes herramientas: {tools}

Para usar una herramienta, sigue EXACTAMENTE este formato:

Thought: Necesito buscar información para responder esta pregunta.
Action: [nombre_de_la_herramienta]
Action Input: {{"parametro": "valor"}}
Observation: [resultado de la herramienta]

Después de recibir la observación, puedes hacer otro pensamiento y usar otra herramienta, o dar tu respuesta final:

Thought: Ahora tengo la información necesaria para responder.
Final Answer: [tu respuesta en español]

IMPORTANTE - FORMATO DE Action Input:
- SIEMPRE usa JSON válido
- Para herramientas que requieren solo "query": {{"query": "texto de búsqueda"}}
- Para herramientas de wiki que solo necesitan project: {{}}  (objeto vacío, se usarán valores por defecto)
- Para herramientas que necesitan project y path: {{"path": "/ruta/pagina"}}

EJEMPLOS CORRECTOS:
1. Para listar páginas del wiki:
   Action: wiki_list_pages
   Action Input: {{}}

2. Para buscar en el wiki:
   Action: wiki_search_pages  
   Action Input: {{"query": "LLM"}}

3. Para obtener contenido de una página:
   Action: wiki_get_page
   Action Input: {{"path": "/nombre-de-la-pagina"}}

4. Para buscar en Wikipedia:
   Action: search_wikipedia
   Action Input: {{"query": "Azure DevOps"}}

Herramientas disponibles: {tool_names}

Cuando el usuario pregunte sobre contenido del wiki, SIEMPRE empieza listando las páginas disponibles o buscando directamente si tienes términos específicos.
"""),
    MessagesPlaceholder(variable_name="chat_history"),
    ("user", "{input}"),
    ("assistant", "{agent_scratchpad}")
])

# Initialize a model with higher temperature for better reasoning
llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash",
    temperature=0.1,
    max_output_tokens=2048
)

# Inicializa la memoria de conversación
if "memory" not in st.session_state:
    st.session_state.memory = ConversationBufferMemory(
        memory_key="chat_history",
        return_messages=True,
        input_key="input"
    )
    st.session_state.memory.chat_memory.add_ai_message("¡Hola! Soy tu asistente de Azure DevOps. ¿En qué puedo ayudarte hoy?")

# Construct the ReAct agent
agent = create_react_agent(
    tools=tools,
    llm=llm,
    prompt=prompt
)

# Create an agent executor
agent_executor = AgentExecutor(
    agent=agent, 
    tools=tools, 
    verbose=True, 
    memory=st.session_state.memory,
    handle_parsing_errors=True,
    max_iterations=10,
    return_intermediate_steps=True,
    early_stopping_method="generate"
)

# --- Interfaz de Usuario con Streamlit ---
st.set_page_config(page_title="ChatBot Azure DevOps", layout="wide")
st.title("ChatBot Azure DevOps")
st.markdown("""
Bienvenido! Este chatbot fue desarrollado para realizar consultas sobre la wiki de Azure DevOps.
**Tecnologías:** Langchain + MCP + Azure DevOps + Gemini
""")

placeholder = st.empty()

# Botón para probar conexión con MCP
if st.sidebar.button("🔧 Probar Conexión MCP"):
    try:
        with st.sidebar:
            with st.spinner("Probando conexión..."):
                tools_list = mcp_client.list_mcp_tools()
                st.success(f"✅ Conexión exitosa! {len(tools_list)} herramientas disponibles")
                with st.expander("Ver herramientas disponibles"):
                    for tool in tools_list:
                        st.write(f"- **{tool['name']}**: {tool.get('description', 'Sin descripción')}")
    except Exception as e:
        st.sidebar.error(f"❌ Error de conexión: {e}")

# Usa st.chat_input para la entrada de usuario
user_query = st.chat_input("¿En qué puedo ayudarte con Azure DevOps?")

# Renderiza el historial solo al inicio
if user_query is None:
    with placeholder.container():
        for message in st.session_state.memory.chat_memory.messages:
            if isinstance(message, HumanMessage):
                with st.chat_message("user"):
                    st.markdown(message.content)
            elif isinstance(message, AIMessage):
                with st.chat_message("assistant"):
                    st.markdown(message.content)

if user_query:
    # Agrega la pregunta del usuario al historial
    st.session_state.memory.chat_memory.add_user_message(user_query)

    # Muestra la pregunta del usuario inmediatamente
    with st.chat_message("user"):
        st.markdown(user_query)

    with st.chat_message("assistant"):
        with st.spinner("Buscando en Azure DevOps..."):
            try:
                # Invoca el agente
                response = agent_executor.invoke(
                    {"input": user_query},
                    config={"verbose": True}
                )

                # Muestra la respuesta del agente
                if "output" in response:
                    st.markdown(response["output"])
                    st.session_state.memory.chat_memory.add_ai_message(response["output"])
                else:
                    error_msg = "No se pudo obtener una respuesta válida del agente."
                    st.error(error_msg)
                    st.session_state.memory.chat_memory.add_ai_message(error_msg)

                # Mostrar pasos intermedios en modo debug
                if st.sidebar.checkbox("🐛 Modo Debug"):
                    if "intermediate_steps" in response:
                        with st.expander("Ver pasos de ejecución"):
                            for i, (action, observation) in enumerate(response["intermediate_steps"]):
                                st.write(f"**Paso {i+1}:**")
                                st.write(f"- Acción: {action.tool}")
                                st.write(f"- Entrada: {action.tool_input}")
                                st.write(f"- Resultado: {observation}")
                                st.divider()

            except Exception as e:
                error_msg = f"Ocurrió un error al procesar tu consulta: {str(e)}"
                st.error(error_msg)
                st.session_state.memory.chat_memory.add_ai_message(f"Lo siento, {error_msg}")
                
                # Mostrar stack trace en modo debug
                if st.sidebar.checkbox("🐛 Modo Debug", key="debug_error"):
                    st.exception(e)

# Sidebar con controles
st.sidebar.markdown("### Controles")
if st.sidebar.button("🧹 Borrar Historial"):
    st.session_state.memory.chat_memory.clear()
    st.session_state.memory.chat_memory.add_ai_message("¡Hola! Soy tu asistente de Azure DevOps. ¿En qué puedo ayudarte hoy?")
    placeholder.empty()
    st.rerun()

# Mostrar información del sistema
with st.sidebar.expander("ℹ️ Información del Sistema"):
    st.write(f"**Herramientas MCP:** {len(mcp_tools)}")
    st.write(f"**Herramientas locales:** {len(home_tools)}")
    st.write(f"**Total herramientas:** {len(tools)}")