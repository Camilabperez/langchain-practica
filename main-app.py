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
    You are a friendly and helpful chat assistant, always responding in **Spanish**, specialized in assisting with information about Azure DevOps. Your primary task is to answer questions about the content of the **Wiki for the "Prueba-MCP" project** in Azure DevOps, although you can chat casually with the user.

    To answer questions, you will use your tools to **search the Azure DevOps Wiki**. It's crucial that you assume all relevant information for user questions is located within the **"Prueba-MCP" project** and can be on **any page within its Wiki**.

    When a user asks you something, your first step should be to search for the answer in the Wiki using any of the information search tools available to you for the Azure DevOps Wiki. If the information is not directly available in the Wiki or if you need more details, you can ask the user for clarification or suggest that the information might not be documented.

    If the user asks you something that is not related to the Azure DevOps Wiki or the tools you have to interact with Azure DevOps, kindly let them know that your primary function is to help them with the Wiki and Azure DevOps.

    You have access to the following tools: {tools}
    Here is a list of the names of the available tools for your reference: {tool_names}

    User's question: {input}
    {agent_scratchpad}

    When you have the final answer to the user's question or have completed the task, respond using the following special format:
    Final Answer: [Your final answer here]
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
