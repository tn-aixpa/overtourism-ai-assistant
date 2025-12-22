from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage

# Initialize local Ollama model
llm = ChatOllama(
    model="mistral",
    base_url="http://localhost:11434",
    temperature=0,
)

def classify_intent(prompt: str) -> str:
    """
    Returns a single action string.
    """
    response = llm.invoke([HumanMessage(content=prompt)])
    return response.content.strip()

def simple_llm(prompt: str) -> str:
    """
    Generic LLM helper.
    """
    response = llm.invoke([HumanMessage(content=prompt)])
    return response.content
