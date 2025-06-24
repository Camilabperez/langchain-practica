from dotenv import load_dotenv
import streamlit as st
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain.agents import AgentExecutor, create_sql_agent

# Para el agente unificado (ReAct Agent)
from langchain.agents import AgentExecutor
from langchain.agents import create_react_agent 
from langchain_core.tools import tool
from langchain_core.prompts import PromptTemplate

import requests # Para las peticiones HTTP a WebMethods


# Carga las variables de entorno
load_dotenv()

# --- Configuración del LLM de Gemini ---
llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0)

# --- Configuración de la Base de Datos PostgreSQL ---
db_uri = "postgresql+psycopg2://wm_user:wm_password@51.8.239.179:5432/messages"

# Descripción de las columnas de la tabla 'ventas' para que el LLM entienda el contexto
custom_table_info = {
    "ventas": """
    Tabla 'ventas' contiene información detallada sobre cada transacción de venta.
    Columnas:
    - id_transaccion (INTEGER PRIMARY KEY): Identificador único de cada transacción.
    - id_sucursal (INTEGER): Identificador único de cada sucursal.
    - nombre_sucursal (TEXT): Nombre de la sucursal.
    - id_venta (INTEGER): Identificador único de cada venta.
    - fecha (DATE): La fecha en que se realizó la venta.
    - rut_cliente (INTEGER): El RUT del cliente que realizó la compra.
    - total_venta (NUMERIC): El valor total de la venta en moneda local.
    - id_producto (INTEGER): El identificador del producto vendido.
    - precio_producto (NUMERIC): El precio unitario del producto vendido.
    - cantidad (INTEGER): La cantidad de unidades del producto vendidas en esta transacción.
    - medio_pago (TEXT): El método de pago utilizado (e.g., 'tarjeta', 'efectivo', 'transferencia').
    """
}

# --- Configuración de IBM WebMethods ---
WEBMETHODS_HOST = "http://172.171.88.128:5555/" # Cambia esto a tu host real (ej. "http://192.168.1.100:5555")
WEBMETHODS_USER = "Administrator"         # Cambia esto a tu usuario real
WEBMETHODS_PASSWORD = "manage" # Cambia esto a tu contraseña real


# --- Herramientas para el Agente ---

# 1. Herramienta para monitorear IBM MQ (simulada)
@tool
def get_ibm_mq_status(queue_manager: str, queue_name: str) -> str:
    """
    Obtiene métricas de estado de una cola específica en un gestor de colas de IBM MQ.
    Esta herramienta es útil para monitorear el rendimiento y la salud de las colas de mensajes.
    Parámetros:
    - queue_manager (str): El nombre del gestor de colas de IBM MQ (e.g., 'QM_PRODUCCION').
    - queue_name (str): El nombre de la cola específica dentro del gestor de colas (e.g., 'COLA.PEDIDOS.ENTRADA').
    """
    # *** ESTO ES UNA SIMULACIÓN PARA DEMOSTRACIÓN ***
    if queue_manager.lower() == "qm_produccion":
        if queue_name.lower() == "cola.pedidos.entrada":
            return (f"La cola 'COLA.PEDIDOS.ENTRADA' en 'QM_PRODUCCION' tiene 75 mensajes pendientes, "
                    f"con una antigüedad del mensaje más antiguo de 5 minutos. "
                    f"El último mensaje fue recibido hace 30 segundos. "
                    f"No hay errores en la cola.")
        elif queue_name.lower() == "cola.pedidos.procesados":
            return (f"La cola 'COLA.PEDIDOS.PROCESADOS' en 'QM_PRODUCCION' está vacía (0 mensajes). "
                    f"Se procesaron 1250 mensajes en la última hora.")
        elif queue_name.lower() == "cola.errores":
            return (f"¡ALERTA! La cola 'COLA.ERRORES' en 'QM_PRODUCCION' tiene 15 mensajes críticos. "
                    f"El último error ocurrió hace 2 minutos: 'Formato JSON inválido'.")
        else:
            return f"No se encontró información simulada para la cola '{queue_name}' en '{queue_manager}'."
    else:
        return f"No se encontró información simulada para el gestor de colas '{queue_manager}'."

# 2. Herramienta para monitorear IBM WebMethods (simulada o real)
@tool
def get_webmethods_service_status(service_name: str) -> str:
    """
    Consulta el estado de un servicio específico en IBM WebMethods Integration Server o API Gateway
    a través de su API REST.
    Útil para verificar si un servicio está activo, su última ejecución exitosa, o si tiene errores.
    Parámetros:
    - service_name (str): El nombre completo del servicio o API a consultar (ej. 'com.example.flow:processOrder').
    """
    # URL de ejemplo para una API de monitoreo de WebMethods. ¡ADAPTA ESTO A TU API REAL!
    # Necesitas consultar la documentación de tu versión específica de WebMethods.
    api_endpoint = f"{WEBMETHODS_HOST}/monitor/flow-executions"

    try:
        # Si quieres usar la conexión real, descomenta y ajusta estas líneas:
        response = requests.get(api_endpoint, auth=(WEBMETHODS_USER, WEBMETHODS_PASSWORD), verify=False) # 'verify=False' para desarrollo con certificados auto-firmados
        response.raise_for_status() # Lanza una excepción para errores HTTP (4xx o 5xx)
        real_status_data = response.json()
        return f"Estado real del servicio '{service_name}': {real_status_data}"

        

    except requests.exceptions.RequestException as e:
        return f"Error al conectar con la API de WebMethods para el servicio '{service_name}': {e}. Verifica el WEBMETHODS_HOST y tus credenciales."
    except Exception as e:
        return f"Ocurrió un error inesperado al procesar la respuesta de WebMethods para '{service_name}': {e}"


# --- Configuración del Agente Unificado ---
db_connected = False # Inicializa en False para manejar errores de conexión
try:
    # Inicializa SQLDatabase con la descripción de la tabla
    db = SQLDatabase.from_uri(db_uri,
                              include_tables=["ventas"],
                              custom_table_info=custom_table_info
                              )
    # Crea el SQLDatabaseToolkit que proporciona herramientas para interactuar con la DB
    db_toolkit = SQLDatabaseToolkit(db=db, llm=llm)
    db_connected = True
except Exception as e:
    st.error(f"Error al conectar a la base de datos PostgreSQL: {e}. Por favor, verifica la URI y las credenciales.")
    # No detengas la ejecución completamente, para que Streamlit pueda mostrar el error.


# Lista de todas las herramientas disponibles para el agente
# Incluimos las herramientas del toolkit de SQLDatabase y nuestras nuevas herramientas.
if db_connected:
    tools = db_toolkit.get_tools() + [get_ibm_mq_status, get_webmethods_service_status]
else:
    # Si la DB no conecta, solo ofrecemos las herramientas no relacionadas con la DB.
    tools = [get_ibm_mq_status, get_webmethods_service_status]

tool_names = ["ibm mq", "postgreSQL", "webmethods"]  # Nombres de las herramientas para el prompt
# Define el prompt para nuestro agente.
prompt = PromptTemplate.from_template(
    """
    Eres un asistente de monitoreo de sistemas inteligente y experto en bases de datos, colas de IBM MQ, y servicios de IBM WebMethods.
    Tu objetivo es responder preguntas sobre el estado de la base de datos de ventas, el estado de las colas de IBM MQ, y el estado de los servicios de WebMethods.
    Tienes acceso a las siguientes herramientas:
    Aquí tienes una lista de los nombres de las herramientas disponibles para tu referencia: {tool_names}
    {tools}

    **Reglas para usar las herramientas:**
    1.  Usa las herramientas que comienzan con `sql_db_` (como `sql_db_query` y `sql_db_schema`) para consultar la base de datos de ventas.
    2.  Usa la herramienta `get_ibm_mq_status` si la pregunta es sobre el estado o métricas de una cola de IBM MQ. Esta herramienta requiere el nombre del gestor de colas y el nombre de la cola.
    3.  Usa la herramienta `get_webmethods_service_status` si la pregunta es sobre el estado o métricas de un servicio específico de IBM WebMethods. Esta herramienta requiere el nombre del servicio.
    4.  Sé lo más específico posible en tus respuestas y proporciona los datos relevantes.
    5.  Si no puedes encontrar la respuesta con las herramientas disponibles, indica que no tienes la información.

    **Ejemplos de preguntas que puedes responder:**
    - "¿Cuántas ventas totales hay en la base de datos?" (Usará SQL)
    - "Dime el estado de la cola de entrada de pedidos en el gestor QM_PRODUCCION." (Usará get_ibm_mq_status)
    - "¿Cómo está el servicio 'processOrder' en WebMethods?" (Usará get_webmethods_service_status)
    - "¿Está funcionando 'validateInputJSON' en WebMethods?" (Usará get_webmethods_service_status)

    Pregunta del usuario: {input}
    {agent_scratchpad}
    """
)


# Crea el agente ReAct
agent = create_react_agent(llm=llm, tools=tools, prompt=prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True, handle_parsing_errors=True)


# --- Interfaz de Usuario con Streamlit ---
st.set_page_config(page_title="Monitor de Sistema con LangChain", layout="wide")
st.title("🚀 Monitor Inteligente de Sistema (Ventas, IBM MQ y WebMethods)")

st.markdown("""
Esta aplicación te permite hacer preguntas en lenguaje natural sobre el estado de tus **ventas (PostgreSQL)**,
el **estado de tus colas de IBM MQ**, y el **estado de los servicios de IBM WebMethods**. LangChain usará Gemini
para decidir qué información necesita y qué herramientas usar para responderte.
""")

# Solo muestra el campo de entrada y el botón si al menos una herramienta está disponible
if not tools:
    st.warning("No hay herramientas disponibles para consultar. Por favor, revisa la configuración de la base de datos y WebMethods.")
else:
    user_question = st.text_input(
        "Haz una pregunta sobre el sistema (ej. '¿Cuántas ventas hubo ayer?', '¿Cuántos mensajes hay en la cola COLA.PEDIDOS.ENTRADA en QM_PRODUCCION?' o '¿Cómo está el servicio processOrder en WebMethods?'):",
        "¿Cómo está el servicio processOrder en WebMethods?" # Pregunta predeterminada para probar WebMethods
    )

    if st.button("Consultar Sistema"):
        if user_question:
            with st.spinner("Consultando el sistema..."):
                try:
                    response = agent_executor.invoke({"input": user_question})
                    st.success("Consulta completada:")
                    st.write(response["output"])
                except Exception as e:
                    st.error(f"Ocurrió un error al procesar tu consulta: {e}")
                    st.info("Asegúrate de que tus preguntas coincidan con los datos y el esquema de la base de datos, las colas MQ o los servicios de WebMethods.")
        else:
            st.warning("Por favor, escribe una pregunta.")

st.sidebar.header("Configuración")
st.sidebar.markdown(f"**Base de Datos Conectada:** `{'Sí' if db_connected else 'No (Error)'}`")
st.sidebar.markdown(f"**LLM Usado:** `{llm.model_name if hasattr(llm, 'model_name') else 'N/A'}`")
st.sidebar.info("Para cambiar la configuración, edita el archivo `app_monitor.py`.")