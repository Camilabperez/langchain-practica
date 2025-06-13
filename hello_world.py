from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import ChatPromptTemplate

load_dotenv()

llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash")

prompt = ChatPromptTemplate.from_messages([
    ("system", "Eres un asistente amable y útil."),
    ("user", "{input}")
])

chain = prompt | llm

response = chain.invoke({"input": "¿Cuál es la capital de Francia?"})
print(response.content)

response_joke = chain.invoke({"input": "Cuéntame un chiste corto."})
print("\n" + response_joke.content)

