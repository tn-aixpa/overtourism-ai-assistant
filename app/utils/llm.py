from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage
from time import time
import re

DEBUG = False

# Initialize local Ollama model
# https://ollama.com/search
# mistral, tinyllama, phi3:mini, gemma2:2b, llama3:8b, qwen3.5:2b, llama3.2:1b, gpt-oss:20b
MODEL = "gpt-oss:20b"
llm = ChatOllama(
    model=MODEL,
    base_url="http://localhost:11434",
    temperature=0,
    keep_alive=-1
)

def format_messages(messages):
    return "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in messages
    )

def llm_interaction(prompt: str) -> str:
    try:
        t1 = time()
        response = llm.invoke([HumanMessage(content=prompt)])
        el = time() - t1
        with open("logs/times_"+re.sub(r'\W+', '', MODEL)+"_.txt", "a+") as f:
            f.write(f"{el:.2f}\n")

        return response.content.strip()
    except Exception as e:
        return f"Error connecting to chatbot: {e}"