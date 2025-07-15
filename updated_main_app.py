from dotenv import load_dotenv
import streamlit as st
from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from tools.time import get_current_time
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder 
from langchain.memory import ConversationBufferMemory
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langchain_together import ChatTogether

# Importar la integración de Edge Wiki
from utils.edge_wiki_integration import create_edge_wiki_tools, test_edge_wiki_connection, add_edge_wiki_to_sidebar

import os

# Load environment variables from .env file
load_dotenv()

# Configurar la página de Streamlit
st.set_page_config(page_title="ChatBot Azure DevOps", layout="wide")
st.title("ChatBot Azure DevOps")
st.markdown("""
Bienvenido! Este chatbot fue desarrollado para realizar consultas sobre la wiki de Azure DevOps.
**Tecnologías:** Langchain + Azure DevOps Python SDK + Gemini
""")

# Verificar variables de entorno
required_vars = ['AZDO_PAT', 'GOOGLE_API_KEY']
missing_vars = [var for var in required_vars if not os.getenv(var)]

if missing_vars:
    st.error(f"❌ Variables de entorno faltantes: {', '.join(missing_vars)}")
    st.info("Por favor configura las variables en tu archivo .env")
    st.stop()

# Inicializar herramientas
@st.cache_resource
def initialize_tools():
    """Inicializa las herramientas del agente"""
    try:
        # Herramientas locales SIN WIKIPEDIA
        home_tools = [get_current_time]
        
        # Herramientas de Edge Wiki
        edge_wiki_tools = create_edge_wiki_tools()
        
        # Combinar todas las herramientas
        all_tools = home_tools + edge_wiki_tools
        
        # Crear lista de nombres
        tool_names = [tool.name for tool in all_tools]
        
        return all_tools, tool_names
        
    except Exception as e:
        st.error(f"❌ Error inicializando herramientas: {e}")
        return [], []

tools, tool_names = initialize_tools()

if not tools:
    st.error("❌ No se pudieron inicializar las herramientas. Verifica tu configuración.")
    st.stop()

# Prompt optimizado para el agente
prompt = ChatPromptTemplate.from_messages([
    ("system", """
Eres un asistente de chat amable y servicial que responde en **español**. Tu especialidad es ayudar con información sobre una wiki en Azure DevOps.

Tienes acceso a las siguientes herramientas: {tools}

Para usar una herramienta, sigue EXACTAMENTE este formato:

Thought: Necesito buscar información para responder esta pregunta.
Action: [nombre_de_la_herramienta]
Action Input: {{"parametro": "valor"}}
Observation: [resultado de la herramienta]

Después de recibir la observación, puedes hacer otro pensamiento y usar otra herramienta, o dar tu respuesta final:

Thought: Ahora tengo la información necesaria para responder.
Final Answer: [tu respuesta en español]

IMPORTANTE - HERRAMIENTAS DISPONIBLES:

1. **edge_wiki_search**: Busca contenido en el wiki
   - Uso: {{"query": "término de búsqueda", "wiki_id": "id_del_wiki" (opcional)}}
   - Ejemplo:{{"query": "LLM"}}
- OTRO EJEMPLO
    -Action Input: {{"query": "Installation Manager", "wiki_id": "035d6f62-1bf0-45fc-afca-3faea5500748"}}

2. **edge_wiki_get_page**: Obtiene contenido completo de una página
   - Uso: {{"path": "path/de/página", "wiki_id": "id_del_wiki"}}
   - Usa path y wiki_id obtenidos de edge_wiki_search

3. **edge_wiki_list_wikis**: Lista todos los wikis disponibles
   - Uso: {{}}

4. **search_wikipedia**: Busca en Wikipedia
   - Uso: {{"query": "término de búsqueda"}}

5. **get_current_time**: Obtiene la hora actual
   - Uso: {{}}

FLUJO RECOMENDADO:
1. Para preguntas sobre el wiki, SIEMPRE empieza con edge_wiki_search.
2. Si encuentras páginas relevantes, usa edge_wiki_get_page para obtener el contenido completo.
3. Cuando encuentres información en el wiki, incluye siempre el contenido y el enlace a la página original.

Herramientas disponibles: {tool_names}

Cuando encuentres información en el wiki, incluye siempre el enlace a la página original para que el usuario pueda acceder a más detalles.
"""),
    MessagesPlaceholder(variable_name="chat_history"),
    ("user", "{input}"),
    ("assistant", "{agent_scratchpad}")
])

# Inicializar el modelo LLM
BASE_URL = "http://20.57.48.191:8084/v1"
MODEL_NAME = "granite-2b-custom-2cpu:latest"
@st.cache_resource
def initialize_llm_local():
    """Inicializa el modelo de lenguaje"""
    return ChatOpenAI(
        openai_api_base=BASE_URL,
        model_name=MODEL_NAME,
        openai_api_key="sk-not-required"
    )


@st.cache_resource
def initialize_llm_gemini():
    """Inicializa el modelo de lenguaje"""
    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=0.1,
        max_output_tokens=2048
   )

@st.cache_resource
def initialize_llm2():
    return ChatAnthropic(
        model="claude-3-5-sonnet-20240620", 
        temperature=0.1,
        max_tokens=2048, 
        anthropic_api_key=""
    )

@st.cache_resource
def initialize_llm_TogetherAI():
    """Inicializa el modelo de lenguaje"""
    return ChatTogether(
        together_api_key=os.getenv("TOGETHER_API_KEY"),
       model="meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo", 
       temperature=0.1,
       max_tokens=2048
    )


llm = initialize_llm_local()

# Inicializar la memoria de conversación
if "memory" not in st.session_state:
    st.session_state.memory = ConversationBufferMemory(
        memory_key="chat_history",
        return_messages=True,
        input_key="input"
    )
    st.session_state.memory.chat_memory.add_ai_message("¡Hola! Soy tu asistente de Azure DevOps. ¿En qué puedo ayudarte hoy?")

# Crear el agente
@st.cache_resource
def create_agent():
    """Crea el agente ReAct"""
    agent = create_react_agent(
        tools=tools,
        llm=llm,
        prompt=prompt
    )
    
    return AgentExecutor(
        agent=agent, 
        tools=tools, 
        verbose=True, 
        memory=st.session_state.memory,
        handle_parsing_errors=True,
        max_iterations=10,
        return_intermediate_steps=True,
        early_stopping_method="generate"
    )

agent_executor = create_agent()

# Contenedor principal para el chat
placeholder = st.empty()

# Sidebar con controles
st.sidebar.markdown("### Controles")

# Botón para limpiar historial
if st.sidebar.button("🧹 Borrar Historial"):
    st.session_state.memory.chat_memory.clear()
    st.session_state.memory.chat_memory.add_ai_message("¡Hola! Soy tu asistente de Azure DevOps. ¿En qué puedo ayudarte hoy?")
    placeholder.empty()
    st.rerun()

# Botón para probar conexión
if st.sidebar.button("🔧 Probar Conexión"):
    with st.sidebar:
        with st.spinner("Probando conexión..."):
            result = test_edge_wiki_connection()
            st.text_area("Resultado:", result, height=300)

# Agregar controles de Edge Wiki
add_edge_wiki_to_sidebar()

# Información del sistema
with st.sidebar.expander("ℹ️ Información del Sistema"):
    st.write(f"**Herramientas disponibles:** {len(tools)}")
    st.write("**Herramientas activas:**")
    for tool in tools:
        st.write(f"- {tool.name}")

# Checkbox para modo debug
debug_mode = st.sidebar.checkbox("🐛 Modo Debug")

# Entrada de chat
user_query = st.chat_input("¿En qué puedo ayudarte con Azure DevOps?")

# Renderizar historial al inicio
if user_query is None:
    with placeholder.container():
        for message in st.session_state.memory.chat_memory.messages:
            if isinstance(message, HumanMessage):
                with st.chat_message("user"):
                    st.markdown(message.content)
            elif isinstance(message, AIMessage):
                with st.chat_message("assistant"):
                    st.markdown(message.content)

# Mostrar ejemplos de uso
with st.expander("💡 Ejemplos de preguntas"):
    st.markdown("""
    **Ejemplos de preguntas que puedes hacer:**
    
    - "Busca páginas relacionadas con Flush"
    - "¿Qué wikis tengo disponibles?"
    - "Muéstrame el contenido de la página principal"
    - "¿Qué hora es?"
    - "Busca en Wikipedia información sobre Azure DevOps"
    """)
# Procesar nueva consulta
if user_query:
    # Agregar al historial
    st.session_state.memory.chat_memory.add_user_message(user_query)

    # Mostrar pregunta del usuario
    with st.chat_message("user"):
        st.markdown(user_query)

    # Procesar con el agente
    with st.chat_message("assistant"):
        with st.spinner("Buscando en Azure DevOps..."):
            try:
                # Invocar el agente
                response = agent_executor.invoke(
                    {"input": user_query},
                    config={"verbose": debug_mode}
                )

                # Mostrar respuesta
                if "output" in response:
                    st.markdown(response["output"])
                    st.session_state.memory.chat_memory.add_ai_message(response["output"])
                else:
                    error_msg = "No se pudo obtener una respuesta válida del agente."
                    st.error(error_msg)
                    st.session_state.memory.chat_memory.add_ai_message(error_msg)

                # Mostrar pasos intermedios en modo debug
                if debug_mode and "intermediate_steps" in response:
                    with st.expander("Ver pasos de ejecución"):
                        for i, (action, observation) in enumerate(response["intermediate_steps"]):
                            st.write(f"**Paso {i+1}:**")
                            st.write(f"- **Acción:** {action.tool}")
                            st.write(f"- **Entrada:** {action.tool_input}")
                            st.write(f"- **Resultado:** {observation}")
                            st.divider()

            except Exception as e:
                error_msg = f"Ocurrió un error al procesar tu consulta: {str(e)}"
                st.error(error_msg)
                st.session_state.memory.chat_memory.add_ai_message(f"Lo siento, {error_msg}")
                
                # Mostrar stack trace en modo debug
                if debug_mode:
                    st.exception(e)

# Footer
st.markdown("---")
st.markdown("**Desarrollado con:** LangChain + Azure DevOps Python SDK + Gemini")
