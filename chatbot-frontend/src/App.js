import React, { useState, useRef, useEffect } from "react";
import "./App.css";

const API_URL = "http://localhost:9000/agent";

function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const textareaRef = useRef(null);
  const [attachments, setAttachments] = useState([]);
  const fileInputRef = useRef(null);

  // TEMPORARY: session id generation
  const generateSessionId = () => {
    const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
    let result = "";
    for (let i = 0; i < 8; i++) {
      result += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return result;
  };
  const [sessionId, setSessionId] = useState(null);

  useEffect(() => {
    const id = generateSessionId();
    setSessionId(id);
  }, []);

  // Handle file attachments
  const handleFileChange = (e) => {
    const newFiles = Array.from(e.target.files);

    setAttachments((prev) => {
      const existingNames = new Set(prev.map(f => f.name));
      const filtered = newFiles.filter(f => !existingNames.has(f.name));
      return [...prev, ...filtered];
    });

    // Reset input so same file can be selected again
    e.target.value = null;
  };

  // Auto-expand textarea
  const handleInputChange = (e) => {
    setInput(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = e.target.scrollHeight + "px";
  };

  //Send message
  const sendMessage = async () => {
    if (!input.trim() && attachments.length === 0) return;

    const newMessages = [...messages, { role: "user", content: input || "[Attachment]" }];
    setMessages(newMessages);

    // Reset input and shrink textarea
    setInput("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }

    const formData = new FormData();
    formData.append("message", input);
    formData.append("session_id", sessionId);
    formData.append("demo", true);

    attachments.forEach((file) => formData.append("files", file));

    setLoading(true);
    // Clear attachments after sending
    setAttachments([]);
    if (fileInputRef.current) fileInputRef.current.value = "";

    try {
      const res = await fetch(API_URL, {
        method: "POST",
        body: formData,
      });
      const data = await res.json();

      if (data.session_id) setSessionId(data.session_id);

      setMessages([
        ...newMessages,
        { role: "assistant", content: data.response },
      ]);
    } catch (err) {
      console.error(err);
      setMessages([
        ...newMessages,
        { role: "assistant", content: "Error contacting server." },
      ]);
    }

    setLoading(false);
  };

  return (
    <div className="app">
      {/* HEADER */}
      <header className="header">
        <h2>Digital Twin Agent</h2>
        <span className="session">Session: {sessionId}</span>
      </header>

      {/* CONTEXT */}
      <header className="context-header">
        <span className="context">Active context: </span>
      </header>


      {/* CHAT AREA */}
      <div className="chat-wrapper">
        <div className="chat-container">
          {messages.map((msg, i) => (
            <div key={i} className={`message ${msg.role}`}>
              {msg.content}
            </div>
          ))}
          {loading && (
            <div className="message assistant">
              <div className="dots">
                <span></span>
                <span></span>
                <span></span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* INPUT AREA */}
      <div className="input-container">
        <div className="input-wrapper">
          
          {/* Row: input + controls */}
          <div className="input-inner">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={handleInputChange}
              placeholder="Ask something..."
              rows={1}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  sendMessage();
                }
              }}
              disabled={loading}
            />

            <span
              className="attachment-icon"
              onClick={() => fileInputRef.current && fileInputRef.current.click()}
            >
              📎
            </span>

            <input
              type="file"
              multiple
              onChange={handleFileChange}
              ref={fileInputRef}
              style={{ display: "none" }}
            />

            <button onClick={sendMessage} disabled={loading}>Send</button>
          </div>

          {/* Row: attachments */}
          {attachments.map((file, idx) => (
            <div key={idx} className="attachment-name">
              {file.name}
              <span
                className="remove-attachment"
                onClick={() =>
                  setAttachments(prev => prev.filter((_, i) => i !== idx))
                }
              >
                🗙
              </span>
            </div>
          ))}

        </div>
      </div>
    </div>
  );
}

export default App;