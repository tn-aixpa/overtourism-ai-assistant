import React, { useState, useRef, useEffect, useCallback } from "react";
import Plot from "react-plotly.js";
import "./App.css";

const API_URL = "http://localhost:9000/agent";

// ---------------------------------------------------------------------------
// Message renderer — handles plain text and chart payloads
// ---------------------------------------------------------------------------

function MessageBubble({ msg }) {
  const isUser = msg.role === "user";

  return (
    <div className={`message ${msg.role}`}>
      {/* Text content */}
      {msg.content && <span className="message-text">{msg.content}</span>}

      {/* Chart — rendered only for assistant messages that carry chart_data */}
      {!isUser && msg.chartData && (
        <ChartPanel figure={msg.chartData} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Interactive chart panel (Plotly)
// ---------------------------------------------------------------------------

function ChartPanel({ figure }) {
  const [revision, setRevision] = useState(0);

  // Merge dark-mode-aware layout overrides on top of the backend layout
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

// ---------------------------------------------------------------------------
// Main App
// ---------------------------------------------------------------------------

function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const textareaRef = useRef(null);
  const [attachments, setAttachments] = useState([]);
  const fileInputRef = useRef(null);
  const [activeContext, setActiveContext] = useState("");
  const [language, setLanguage] = useState("English");
  const messagesEndRef = useRef(null);

  const generateSessionId = () => {
    const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
    return Array.from({ length: 8 }, () =>
      chars.charAt(Math.floor(Math.random() * chars.length))
    ).join("");
  };

  const [sessionId, setSessionId] = useState(() => generateSessionId());

  // Auto-scroll to latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Handle file attachments
  const handleFileChange = (e) => {
    const newFiles = Array.from(e.target.files);
    setAttachments((prev) => {
      const existingNames = new Set(prev.map((f) => f.name));
      return [...prev, ...newFiles.filter((f) => !existingNames.has(f.name))];
    });
    e.target.value = null;
  };

  // Auto-expand textarea
  const handleInputChange = (e) => {
    setInput(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = e.target.scrollHeight + "px";
  };

  // Send message
  const sendMessage = useCallback(async () => {
    if (!input.trim() && attachments.length === 0) return;

    const userMessage = { role: "user", content: input || "[Attachment]" };
    const newMessages = [...messages, userMessage];
    setMessages(newMessages);

    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";

    const formData = new FormData();
    formData.append("message", input);
    formData.append("session_id", sessionId);
    formData.append("user_lang", language);
    attachments.forEach((file) => formData.append("files", file));

    setLoading(true);
    setAttachments([]);
    if (fileInputRef.current) fileInputRef.current.value = "";

    try {
      const res = await fetch(API_URL, { method: "POST", body: formData });
      const data = await res.json();

      if (data.session_id) setSessionId(data.session_id);
      setActiveContext(data.active_context || "-");

      // Build assistant message — attach chart_data if present
      const assistantMessage = {
        role: "assistant",
        content: data.response,
        chartData: data.chart_data ?? null,   // <-- Plotly figure JSON or null
      };

      setMessages([...newMessages, assistantMessage]);
    } catch (err) {
      console.error(err);
      setMessages([
        ...newMessages,
        { role: "assistant", content: "Error contacting server." },
      ]);
    }

    setLoading(false);
  }, [input, attachments, messages, sessionId, language]);

  // Save conversation
  const saveConversation = async () => {
    if (!sessionId) return;
    try {
      const res = await fetch("http://localhost:9000/agent/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
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
            <option value="English">English</option>
            <option value="Italian">Italian</option>
          </select>
          <span className="session">Session: {sessionId}</span>
        </div>
      </header>

      {/* CONTEXT BAR */}
      <header className="context-header">
        <span className="context">Active context: {activeContext || "-"}</span>
        <button className="save-btn" onClick={saveConversation} disabled={!sessionId}>
          💾 Save conversation
        </button>
      </header>

      {/* CHAT AREA */}
      <div className="chat-wrapper">
        <div className="chat-container">
          {messages.map((msg, i) => (
            <MessageBubble key={i} msg={msg} />
          ))}

          {loading && (
            <div className="message assistant">
              <div className="dots">
                <span></span><span></span><span></span>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* INPUT AREA */}
      <div className="input-container">
        <div className="input-wrapper">
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
              onClick={() => fileInputRef.current?.click()}
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

          {attachments.map((file, idx) => (
            <div key={idx} className="attachment-name">
              {file.name}
              <span
                className="remove-attachment"
                onClick={() => setAttachments((prev) => prev.filter((_, i) => i !== idx))}
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
