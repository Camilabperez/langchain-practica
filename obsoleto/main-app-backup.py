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

home_tools = [ get_current_time,search_wikipedia,]
home_tools_names = ["get_current_time", "search_wikipedia"]

tools = mcp_tools + home_tools
tool_names = mcp_tools_names + home_tools_names


prompt = ChatPromptTemplate.from_messages([
    ("system",  """
Eres un asistente de chat amable y servicial, siempre respondiendo en **español**, especializado en asistir con información sobre Azure DevOps. Tu tarea principal es contestar preguntas acerca del contenido del **Wiki del proyecto "Prueba-MCP"** en Azure DevOps, aunque puedes conversar de forma casual con el usuario.

Para responder preguntas, utilizarás tus herramientas para **buscar en el Wiki de Azure DevOps**. Debes asumir que toda la información relevante para las consultas del usuario se encuentra dentro del **proyecto "Prueba-MCP"** y puede estar en **cualquier página de su Wiki**.

Cuando un usuario te haga una pregunta, tu primer paso debe ser buscar la respuesta en el Wiki utilizando cualquiera de las herramientas de búsqueda que tengas disponibles para el Wiki de Azure DevOps. Si la información no está disponible directamente o necesitas más detalles, puedes pedir aclaraciones al usuario o indicar que la información podría no estar documentada.

Si el usuario te pregunta algo que no esté relacionado con el Wiki de Azure DevOps o con las herramientas que tienes para interactuar con Azure DevOps, debes indicarle amablemente que tu función principal es ayudarle con el Wiki y con Azure DevOps.

Tienes acceso a las siguientes herramientas: {tools}
Aquí tienes una lista de los nombres de las herramientas disponibles como referencia: {tool_names}
     
⚠️ Cuando respondas con un `Action Input`, **debes enviarlo SIEMPRE como un objeto JSON con clave-valor**, nunca como un texto plano.

✅ Ejemplo correcto:
Action Input: {{ "{{\"query\": \"texto a buscar\"}}" }}

❌ Ejemplo prohibido:
Action Input: "texto a buscar"

Si la consulta no requiere herramientas, puedes responder directamente con:
Final Answer: [respuesta en español]

En cada paso debes elegir **solo uno** de estos dos formatos:
- Thought + Action + Action Input (con JSON)
- Final Answer

**Jamás combines ambos en el mismo paso.**

---

Ejemplos de uso:

**Ejemplo 1 (con herramienta):**
Thought: Necesito buscar la definición de pipelines en la wiki.
Action: search_wiki
Action Input: {{ "{{\"query\": \"pipelines en Azure DevOps\"}}" }}

**Ejemplo 2 (sin herramienta):**
Thought: El usuario pregunta algo que no requiere búsqueda.
Final Answer: Claro, te puedo explicar los conceptos generales de Azure DevOps.

---

IMPORTANTE:
- `Action Input` **debe ser un objeto JSON** como {{ "{{\"query\": \"texto a buscar\"}}" }}
- Si tu respuesta no requiere herramienta, incluidas interacciones sociales (como saludos), debes usar SIEMPRE el formato Final Answer: [texto].
- Nunca devuelvas texto plano suelto fuera de estos formatos.
❌ Nunca pongas Action Input como texto plano.
❌ Nunca pongas Action Input sin la clave "query".
❌ Nunca devuelvas texto directo sin Final Answer.
---

Pregunta del usuario: {input}
{agent_scratchpad}
"""),
    MessagesPlaceholder(variable_name="chat_history"),
    ("human", "{input}"),
])





# Initialize a model
llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash")

# Inicializa la memoria de conversación
if "memory" not in st.session_state:
    st.session_state.memory = ConversationBufferMemory(
        memory_key="chat_history",
        return_messages=True,
        input_key="input"  # importante para funcionar con AgentExecutor
    )
    st.session_state.memory.chat_memory.add_ai_message("¡Hola! Soy tu asistente de Azure DevOps. ¿En qué puedo ayudarte hoy?")

# Construct the JSON agent
agent = create_react_agent(
    tools=tools,
    llm=llm,
    prompt= prompt
)

# Create an agent executor by passing in the agent and tools
agent_executor = AgentExecutor(
        agent=agent, 
        tools=tools, 
        verbose=True, 
        memory=st.session_state.memory,
        handle_parsing_errors=True,
        max_iterations=5,
        return_intermediate_steps=True,
)

# --- Interfaz de Usuario con Streamlit ---
st.set_page_config(page_title="ChatBot", layout="wide")
st.title("ChatBot Azure DevOps")
st.markdown("""
Bienvenido! Este chatbot fue desarrollado para realizar consultas sobre la wiki de AzureDevOps
            Langchain + MCP + Azure DevOps
""")

placeholder = st.empty()

# Usa st.chat_input para la entrada de usuario
user_query = st.chat_input("¿En qué puedo ayudarte con Azure DevOps?")

#Rednderiza el historial solo al inicio
if user_query is None:
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



if user_query: # Este bloque se ejecuta cuando el usuario presiona Enter
    # Agrega la pregunta del usuario al historial usando .chat_memory
    st.session_state.memory.chat_memory.add_user_message(user_query)

    # Muestra la pregunta del usuario inmediatamente
    with st.chat_message("user"):
        st.markdown(user_query)

    with st.chat_message("assistant"):
        with st.spinner("Pensando..."):
            try:

                # Invoca el agente
                response = agent_executor.invoke(
                    {"input": user_query}
                )

                # Muestra la respuesta del agente
                st.markdown(response["output"])
                # Agrega la respuesta del agente al historial usando .chat_memory
                st.session_state.memory.chat_memory.add_ai_message(response["output"])

            except Exception as e:
                st.error(f"Ocurrió un error al procesar tu consulta: {e}")
                # Agrega el mensaje de error al historial usando .chat_memory
                st.session_state.memory.chat_memory.add_ai_message(f"Lo siento, ocurrió un error: {e}")
                st.info("Problemas.")

st.sidebar.markdown("")
if st.sidebar.button("🧹 Borrar Historial"):
    st.session_state.memory.chat_memory.clear()
    placeholder.empty()
