from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

# Usa la IP de tu VM Linux y el puerto 8084
# Si ejecutas el script en la misma VM, puedes usar "http://localhost:8084/v1"
# Si ejecutas el script desde otra máquina, usa la IP real de la VM.
BASE_URL = "http://20.57.48.191:8084/v1"
MODEL_NAME = "granite-2b-custom-2cpu:latest"

try:
    # Inicializa el modelo ChatOpenAI
    # openai_api_key es requerido por la librería, pero puede ser cualquier string para Ollama
    model = ChatOpenAI(
        openai_api_base=BASE_URL,
        model_name=MODEL_NAME,
        openai_api_key="ollama-key"
    )

    # Realiza la inferencia
    answer = model.invoke("Give me a fact about whales.")

    # Imprime la respuesta
    print(answer.content)

except Exception as e:
    print(f"Ocurrió un error: {e}")
    print("Asegúrate de que Ollama esté corriendo y escuchando en:")
    print(f"  {BASE_URL}")
    print(f"y que el modelo '{MODEL_NAME}' esté descargado en Ollama.")