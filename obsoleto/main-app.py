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

import requests
import base64
import os
from dotenv import load_dotenv

#from utils.azure_devops_diagnostic import test_azure_devops_connection, ensure_wiki_exists
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

def test_azure_devops_connection():
    """Prueba la conexión directa a Azure DevOps API con diagnóstico detallado"""
    load_dotenv()
    
    org_url = os.getenv("AZDO_ORG_URL")
    pat = os.getenv("AZDO_PAT")
    project = os.getenv("AZDO_DEFAULT_PROJECT")
    
    if not all([org_url, pat, project]):
        return "❌ Variables de entorno faltantes"
    
    # Crear header de autenticación
    auth_string = f":{pat}"
    b64_auth = base64.b64encode(auth_string.encode()).decode()
    headers = {
        "Authorization": f"Basic {b64_auth}",
        "Content-Type": "application/json"
    }
    
    results = []
    results.append(f"🔍 DIAGNÓSTICO PARA PROYECTO: {project}")
    results.append(f"🌐 ORGANIZACIÓN: {org_url}")
    results.append("=" * 50)
    
    # Test 1: Verificar acceso a la organización
    project_found_in_list = False
    try:
        response = requests.get(f"{org_url}/_apis/projects", headers=headers)
        results.append(f"📡 Test 1 - Listar proyectos: Status {response.status_code}")
        
        if response.status_code == 200:
            projects = response.json()
            project_names = [p['name'] for p in projects['value']]
            results.append(f"✅ Acceso a organización: OK ({len(project_names)} proyectos)")
            results.append(f"📋 Proyectos disponibles: {', '.join(project_names)}")
            
            # Verificar si el proyecto específico existe
            if project in project_names:
                project_found_in_list = True
                results.append(f"✅ Proyecto '{project}' encontrado en la lista")
            else:
                results.append(f"❌ Proyecto '{project}' NO encontrado en la lista")
                
        elif response.status_code == 401:
            results.append(f"❌ Token PAT inválido o expirado")
            return "\n".join(results)
        elif response.status_code == 403:
            results.append(f"❌ Sin permisos para listar proyectos")
            return "\n".join(results)
        else:
            results.append(f"❌ Error acceso organización: {response.status_code} - {response.text}")
            return "\n".join(results)
    except Exception as e:
        results.append(f"❌ Error conexión organización: {e}")
        return "\n".join(results)
    
    # Test 2: Verificar acceso al proyecto específico
    results.append("\n" + "=" * 50)
    try:
        response = requests.get(f"{org_url}/{project}/_apis/project", headers=headers)
        results.append(f"📡 Test 2 - Acceso directo al proyecto: Status {response.status_code}")
        
        if response.status_code == 200:
            project_data = response.json()
            results.append(f"✅ Acceso al proyecto '{project}': OK")
            results.append(f"📋 ID del proyecto: {project_data.get('id', 'N/A')}")
            results.append(f"📋 Estado: {project_data.get('state', 'N/A')}")
        elif response.status_code == 404:
            results.append(f"❌ Proyecto '{project}' no encontrado en acceso directo")
            if project_found_in_list:
                results.append(f"🔧 PROBLEMA: El proyecto existe pero no puedes acceder directamente")
                results.append(f"🔧 CAUSA PROBABLE: Permisos insuficientes del token PAT")
        elif response.status_code == 401:
            results.append(f"❌ Token PAT inválido")
        elif response.status_code == 403:
            results.append(f"❌ Sin permisos para acceder al proyecto '{project}'")
            results.append(f"🔧 SOLUCIÓN: Revisar permisos del PAT y del usuario en el proyecto")
        else:
            results.append(f"❌ Error acceso proyecto: {response.status_code}")
            results.append(f"📝 Respuesta: {response.text[:200]}...")
    except Exception as e:
        results.append(f"❌ Error conexión proyecto: {e}")
    
    # Test 3: Verificar permisos del token
    results.append("\n" + "=" * 50)
    try:
        response = requests.get(f"{org_url}/_apis/connectionData", headers=headers)
        results.append(f"📡 Test 3 - Información del token: Status {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            user_info = data.get('authenticatedUser', {})
            results.append(f"✅ Token válido")
            results.append(f"👤 Usuario: {user_info.get('displayName', 'Desconocido')}")
            results.append(f"📧 Email: {user_info.get('uniqueName', 'No disponible')}")
            results.append(f"🆔 ID: {user_info.get('id', 'No disponible')}")
        else:
            results.append(f"❌ Error validación token: {response.status_code}")
    except Exception as e:
        results.append(f"❌ Error validación token: {e}")
    
    # Test 4: Verificar acceso al Wiki
    results.append("\n" + "=" * 50)
    try:
        response = requests.get(f"{org_url}/{project}/_apis/wiki/wikis", headers=headers, params={"api-version": "7.0"})
        results.append(f"📡 Test 4 - Acceso al Wiki: Status {response.status_code}")
        
        if response.status_code == 200:
            wikis = response.json()
            if wikis['count'] > 0:
                wiki_names = [w['name'] for w in wikis['value']]
                results.append(f"✅ Acceso a Wiki: OK ({wikis['count']} wikis)")
                results.append(f"📋 Wikis disponibles: {', '.join(wiki_names)}")
                
                # Obtener detalles del primer wiki
                first_wiki = wikis['value'][0]
                results.append(f"📋 Wiki principal: {first_wiki['name']}")
                results.append(f"📋 ID: {first_wiki['id']}")
                results.append(f"📋 Tipo: {first_wiki.get('type', 'N/A')}")
            else:
                results.append(f"⚠️  No hay wikis en el proyecto '{project}'")
        elif response.status_code == 404:
            results.append(f"❌ Wiki API no encontrada")
        elif response.status_code == 403:
            results.append(f"❌ Sin permisos para acceder al Wiki")
            results.append(f"🔧 SOLUCIÓN: Agregar permisos de Wiki al token PAT")
        else:
            results.append(f"❌ Error acceso Wiki: {response.status_code}")
            results.append(f"📝 Respuesta: {response.text[:200]}...")
    except Exception as e:
        results.append(f"❌ Error conexión Wiki: {e}")
    
    # Resumen y recomendaciones
    results.append("\n" + "=" * 50)
    results.append("🔧 RECOMENDACIONES:")
    
    if project_found_in_list and response.status_code == 404:
        results.append("1. ⚠️  PROBLEMA PRINCIPAL: Permisos insuficientes del token PAT")
        results.append("2. 🔧 Ve a Azure DevOps → User Settings → Personal Access Tokens")
        results.append("3. 🔧 Edita tu token y asegúrate de tener estos permisos:")
        results.append("   - Project and Team (Read)")
        results.append("   - Wiki (Read & Write)")
        results.append("   - Code (Read) - si el wiki está en repo")
        results.append("4. 🔧 Verifica permisos del usuario en Project Settings → Security")
    
    return "\n".join(results)

# Función para agregar al sidebar de Streamlit
def add_diagnostic_to_sidebar():
    """Agregar botón de diagnóstico al sidebar"""
    if st.sidebar.button("🔍 Diagnóstico Completo"):
        with st.sidebar:
            with st.spinner("Ejecutando diagnóstico..."):
                diagnostic_result = test_azure_devops_connection()
                st.text_area("Resultados del diagnóstico:", diagnostic_result, height=400)

# Función para verificar si el wiki existe y crearlo si es necesario
def ensure_wiki_exists():
    """Verifica si el wiki existe y da instrucciones para crearlo"""
    load_dotenv()
    
    org_url = os.getenv("AZDO_ORG_URL")
    pat = os.getenv("AZDO_PAT")
    project = os.getenv("AZDO_DEFAULT_PROJECT")
    
    auth_string = f":{pat}"
    b64_auth = base64.b64encode(auth_string.encode()).decode()
    headers = {
        "Authorization": f"Basic {b64_auth}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(f"{org_url}/{project}/_apis/wiki/wikis", headers=headers, params={"api-version": "7.0"})
        if response.status_code == 200:
            wikis = response.json()
            if wikis['count'] == 0:
                return f"""
❌ NO HAY WIKIS EN EL PROYECTO '{project}'

🔧 PASOS PARA CREAR UN WIKI:
1. Ve a https://dev.azure.com/camilabperez/{project}
2. Haz clic en "Wiki" en el menú lateral
3. Haz clic en "Create project wiki"
4. Crea al menos una página con contenido sobre LLMs
5. Vuelve a probar tu aplicación

📋 ESTRUCTURA SUGERIDA:
- Página principal: "Home"
- Páginas de contenido: "LLM-GPT", "LLM-Claude", "LLM-Gemini", etc.
"""
            else:
                wiki_info = wikis['value'][0]
                return f"✅ Wiki encontrado: {wiki_info['name']} (ID: {wiki_info['id']})"
        else:
            return f"❌ Error verificando wiki: {response.status_code} - {response.text}"
    except Exception as e:
        return f"❌ Error: {e}"

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

    st.sidebar.markdown("### Diagnóstico")
if st.sidebar.button("🔍 Diagnóstico Completo"):
    with st.sidebar:
        with st.spinner("Ejecutando diagnóstico..."):
            diagnostic_result = test_azure_devops_connection()
            st.text_area("Resultados:", diagnostic_result, height=400)

if st.sidebar.button("📝 Verificar Wiki"):
    wiki_status = ensure_wiki_exists()
    st.sidebar.info(wiki_status)

    