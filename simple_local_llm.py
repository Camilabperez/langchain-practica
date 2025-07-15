from langchain_openai import ChatOpenAI

BASE_URL = "http://20.57.48.191:8084/v1"
MODEL_NAME = "granite-2b-custom-2cpu:latest"

try:
    # Inicializa el modelo ChatOpenAI
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