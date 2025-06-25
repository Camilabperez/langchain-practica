from dotenv import load_dotenv
import streamlit as st
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain.agents import AgentExecutor, create_sql_agent

# Carga las variables de entorno
load_dotenv()

# --- Configuración del LLM de Gemini ---
llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0)
# --- Configuración de la Base de Datos PostgreSQL ---
db_uri = "postgresql+psycopg2://wm_user:wm_password@51.8.239.179:5432/messages"

try:
    # Descripcion de las columnas de la tabla para que el LLM entienda el contexto
    custom_table_info = {
        "ventas": """
        Tabla 'ventas' contiene información detallada sobre cada transacción de venta.
        Columnas:
        - id_transaccion (INTEGER PRIMARY KEY): Identificador único de cada transacción.
        - id_sucursal (INTEGER): Identificador único de cada sucursal.
        - nombre_sucursal (TEXT): Nombre de la sucursal.
        - id_venta (INTEGER PRIMARY KEY): Identificador único de cada venta.
        - fecha (DATE): La fecha en que se realizó la venta.
        - rut_cliente (INTEGER): El RUT del cliente que realizó la compra.
        - total_venta (NUMERIC): El valor total de la venta en moneda local.
        - id_producto (INTEGER): El identificador del producto vendido.
        - precio_producto (NUMERIC): El precio unitario del producto vendido.
        - cantidad (INTEGER): La cantidad de unidades del producto vendidas en esta transacción.
        - medio_pago (TEXT): El método de pago utilizado (e.g., 'tarjeta', 'efectivo', 'transferencia').
        """
    }

    # Inicializa SQLDatabase
    db = SQLDatabase.from_uri(db_uri,
                              include_tables=["ventas"], 
                              custom_table_info=custom_table_info # ¡Aquí pasamos las descripciones!
                              )

    # Crea el SQLDatabaseToolkit
    toolkit = SQLDatabaseToolkit(db=db, llm=llm)

    # Crea el agente SQL
    agent_executor = create_sql_agent(
        llm=llm,
        toolkit=toolkit,
        verbose=True,
        agent_type="zero-shot-react-description"
    )
    db_connected = True
except Exception as e:
    st.error(f"Error al conectar a la base de datos PostgreSQL: {e}. Por favor, verifica la URI y las credenciales.")
    st.stop() # Detiene la ejecución si hay un error de conexión 

# --- Interfaz de Usuario con Streamlit ---
st.set_page_config(page_title="Monitor Inteligente de Ventas (PostgreSQL)", layout="wide")
st.title("📊 Monitor Inteligente de Ventas")
st.markdown("""
Esta aplicación te permite hacer preguntas en lenguaje natural sobre tus **ventas** en la base de datos PostgreSQL.
""")

if not db_connected:
    st.warning("La aplicación no pudo conectar a la base de datos. Por favor, revisa la configuración en el código.")
else:
    user_question = st.text_input("Haz una pregunta sobre tu tabla de ventas:", "Cuántas ventas totales hay?")

    if st.button("Consultar Ventas"):
        if user_question:
            with st.spinner("Consultando base de datos..."):
                try:
                    response = agent_executor.invoke({"input": user_question})
                    st.success("Consulta completada:")
                    st.write(response["output"])
                except Exception as e:
                    st.error(f"Ocurrió un error al procesar tu consulta: {e}")
                    st.info("Asegúrate de que tus preguntas coincidan con los datos y el esquema de la base de datos.")
        else:
            st.warning("Por favor, escribe una pregunta.")

    st.sidebar.header("Configuración")
    st.sidebar.markdown(f"**Base de Datos Conectada:** `PostgreSQL`")
    st.sidebar.markdown(f"**LLM Usado:** `{llm.model_name if hasattr(llm, 'model_name') else 'N/A'}`")
    st.sidebar.info("Para cambiar la base de datos o el LLM, edita el archivo `app_db_monitor.py`.")
