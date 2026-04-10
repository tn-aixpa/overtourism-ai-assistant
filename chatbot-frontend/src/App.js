import React, { useState, useRef, useEffect } from "react";
import "./App.css";
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import Plot from "react-plotly.js";

const API_URL = "http://localhost:9000/agent";

function ChartPanel({ figure }) {
  const [revision, setRevision] = useState(0);

  const layout = {
    ...figure.layout,
    autosize: true,
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: {
      ...figure.layout?.font,
      color: getComputedStyle(document.documentElement)
        .getPropertyValue("--color-text-primary")
        .trim() || "#111",
    },
    margin: { l: 48, r: 24, t: figure.layout?.title ? 40 : 12, b: 40 },
  };

  const config = {
    responsive: true,
    displaylogo: false,
    modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d"],
    toImageButtonOptions: { format: "svg", filename: "chart" },
  };

  return (
    <div className="chart-panel">
      <Plot
        data={figure.data}
        layout={layout}
        config={config}
        revision={revision}
        useResizeHandler
        style={{ width: "100%", minHeight: 320 }}
        onInitialized={() => setRevision((r) => r + 1)}
      />
    </div>
  );
}

function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const textareaRef = useRef(null);
  const chatRef = useRef(null);
  const [attachments, setAttachments] = useState([]);
  const fileInputRef = useRef(null);
  const [activeContext, setActiveContext] = useState("");
  const [language, setLanguage] = useState("Italiano");

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

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    if (chatRef.current) {
      chatRef.current.scrollTop = chatRef.current.scrollHeight;
    }
  }, [messages]);

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
    const textarea = e.target;
    setInput(textarea.value);
    textarea.style.height = "auto";
    textarea.style.height = `${Math.max(textarea.scrollHeight, 24)}px`;
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
    formData.append("user_lang", language);

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
      setActiveContext(data.active_context || "-");

      setMessages([
        ...newMessages,
        { role: "assistant", content: data.response, chartData: data.chart_data ?? null },
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

  // Save conversation
  const saveConversation = async () => {
    if (!sessionId) return;

    try {
      const res = await fetch(`http://localhost:9000/agent/save`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ session_id: sessionId }),
      });

      const data = await res.json();
      alert(data.message || "Conversation saved!");
    } catch (err) {
      console.error(err);
      alert("Failed to save conversation.");
    }
  };

  return (
    <div className="app">
      {/* HEADER */}
      <header className="header">
        <h2>Digital Twin Agent</h2>

        <div className="header-right">
          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            className="language-select"
          >
            <option value="Italian">Italiano</option>
            <option value="English">English</option>
          </select>

          <span className="session">Session: {sessionId}</span>
        </div>
      </header>

      {/* CONTEXT */}
      <header className="context-header">
        <span className="context">Active context: {activeContext || "-"}</span>
        <button 
          className="save-btn" 
          onClick={saveConversation} 
          disabled={!sessionId}
        >
          💾 Save conversation
        </button>
      </header>


      {/* CHAT AREA */}
      <div className="chat-wrapper" ref={chatRef}>
        <div className="chat-container">
          {messages.map((msg, i) => (
            <div key={i} className={`message ${msg.role}`}>
              {msg.role === 'assistant' ? (
                <>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                  {msg.chartData && <ChartPanel figure={msg.chartData} />}
                </>
              ) : (
                msg.content
              )}
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