import streamlit as st
import requests

API_URL = "http://localhost:9000/agent"

st.title("Digital Twin Agent Demo")

if "messages" not in st.session_state:
    st.session_state.messages = []

# Initialize session_id
if "session_id" not in st.session_state:
    st.session_state.session_id = None

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# User input
if prompt := st.chat_input("Ask something..."):
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

    payload = {
        "message": prompt,
        "demo": True,
    }

    # send session_id if it exists
    if st.session_state.session_id:
        payload["session_id"] = st.session_state.session_id

    response = requests.post(API_URL, json=payload)
    data = response.json()
    
    # Save session_id returned from API
    st.session_state.session_id = data.get("session_id")

    answer = data["response"]
    st.session_state.messages.append({"role": "assistant", "content": answer})

    with st.chat_message("assistant"):
        st.markdown(answer)