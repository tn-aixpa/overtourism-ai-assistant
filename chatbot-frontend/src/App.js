import React, { useState, useRef, useEffect, useCallback } from "react";
import "./App.css";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import Plot from "react-plotly.js";

const API_URL = "http://localhost:9000/agent";

// ─── Helpers ────────────────────────────────────────────────────────────────

function generateSessionId() {
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  return Array.from({ length: 8 }, () =>
    chars.charAt(Math.floor(Math.random() * chars.length))
  ).join("");
}

function fmtVal(v) {
  return parseFloat(v.toFixed(4)).toString();
}

function getInitialValue(widget) {
  if (widget.index_type === "uniform") return widget.loc ?? 0;
  if (widget.v !== undefined) return widget.v;
  return widget.loc ?? 0;
}

function initSlidersState(slidersData) {
  const state = {};
  for (const group of Object.keys(slidersData.widgets)) {
    state[group] = slidersData.widgets[group].map((w) => {
      const initial = getInitialValue(w);
      return {
        ...w,
        _val: initial,
        _initial: initial,
      };
    });
  }
  return state;
}
// ─── ChartPanel ─────────────────────────────────────────────────────────────

function ChartPanel({ figure }) {
  const [revision, setRevision] = useState(0);

  const layout = {
    ...figure.layout,
    autosize: true,
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: {
      ...figure.layout?.font,
      color:
        getComputedStyle(document.documentElement)
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

// ─── SliderWidget ────────────────────────────────────────────────────────────

function SliderWidget({ widget, onChange }) {
  const val = widget._val;
  const suffix = widget.index_category === "%" ? "%" : "";
  const isUniform =
    widget.index_type === "uniform" && widget.index_category !== "%";

  const step = useCallback(
    (dir) => {
      const s = widget.step || 1;
      const next = Math.round((val + dir * s) * 1e6) / 1e6;
      onChange(Math.min(Math.max(next, widget.min), widget.max));
    },
    [val, widget, onChange]
  );

  return (
    <div className="slider-card">
      <div className="slider-label">{widget.index_name}</div>

      <div className="slider-row">
        <input
          type="range"
          min={widget.min}
          max={widget.max}
          step={widget.step || 1}
          value={val}
          onChange={(e) => onChange(parseFloat(e.target.value))}
        />
        <span className="slider-value">
          {fmtVal(val)}
          {suffix}
        </span>
      </div>

      <div className="stepper-row">
        <button className="step-btn" onClick={() => step(-1)} aria-label="Decrease">
          −
        </button>
        <button className="step-btn" onClick={() => step(1)} aria-label="Increase">
          +
        </button>
        {isUniform && (
          <span className="slider-badge">distribuzione uniforme</span>
        )}
      </div>
    </div>
  );
}

// ─── SlidersPanel ────────────────────────────────────────────────────────────

function SlidersPanel({ slidersData, sessionId  }) {
  const groups = Object.keys(slidersData.widgets);
  const [activeTab, setActiveTab] = useState(groups[0]);
  const [state, setState] = useState(() => initSlidersState(slidersData));
  const [submitting, setSubmitting] = useState(false);

  const handleSubmitSliders = async () => {
    if (submitting) return; // prevent double click

    setSubmitting(true);

    // Flatten all widgets across groups
    const allWidgets = Object.values(state).flat();

    const changed = allWidgets.filter(
      (w) => w._val !== w._initial
    );

    const payload = {};

    changed.forEach((w) => {
      const hasScale = w.scale !== undefined && w.scale !== null;

      payload[w.index_id] = hasScale
        ? [w._val, w._val + w.scale]
        : w._val;
    });

    if (Object.keys(payload).length === 0) {
      setSubmitting(false); // re-enable
      return;
    }

    try {
      const res = await fetch(`${API_URL}/inject_sliders`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          session_id: sessionId,
          values: payload,
        }),
      });

      const data = await res.json();
      console.log("Inject response:", data);
    } catch (err) {
      console.error("Error sending sliders:", err);
    }
  };

  const handleChange = useCallback((group, index_id, newVal) => {
    setState((prev) => ({
      ...prev,
      [group]: prev[group].map((w) =>
        w.index_id === index_id ? { ...w, _val: newVal } : w
      ),
    }));
  }, []);

  return (
    <div className="sliders-panel">
      <div className="sliders-layout">
        <div className="tab-list" role="tablist">
          {groups.map((g) => (
            <button
              key={g}
              role="tab"
              aria-selected={activeTab === g}
              className={`tab-btn${activeTab === g ? " active" : ""}`}
              onClick={() => setActiveTab(g)}
            >
              {g}
            </button>
          ))}
        </div>

        <div className="sliders-grid" role="tabpanel">
          {state[activeTab]
            .filter((w) => w.editable)
            .map((w) => (
              <SliderWidget
                key={w.index_id}
                widget={w}
                onChange={(val) => handleChange(activeTab, w.index_id, val)}
              />
            ))}
        </div>

      </div>
        <div className="sliders-footer">
          <button
            className="submit-sliders-btn"
            onClick={handleSubmitSliders}
            disabled={submitting}
          >
            {submitting ? "Indici modificati" : "Conferma modifica"}
          </button>
        </div>
    </div>
  );
}

// ─── Message ─────────────────────────────────────────────────────────────────

function Message({ msg, sessionId }) {
  if (msg.role === "user") {
    return <div className="message user">{msg.content}</div>;
  }

  return (
    <div className="message assistant">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
      {msg.chartData && <ChartPanel figure={msg.chartData} />}
      {msg.slidersData && <SlidersPanel slidersData={msg.slidersData} sessionId={sessionId} />}
    </div>
  );
}

// ─── LoadingBubble ────────────────────────────────────────────────────────────

function LoadingBubble({ statusMessage }) {
  return (
    <div className="message assistant">
      <div className="dots">
        <span />
        <span />
        <span />
      </div>
      {statusMessage && <span className="status">{statusMessage}</span>}
    </div>
  );
}

// ─── App ─────────────────────────────────────────────────────────────────────

function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [attachments, setAttachments] = useState([]);
  const [activeContext, setActiveContext] = useState("");
  const [language, setLanguage] = useState("Italiano");
  const [statusMessage, setStatusMessage] = useState(null);
  const [sessionId] = useState(() => generateSessionId());

  const textareaRef = useRef(null);
  const chatRef = useRef(null);
  const fileInputRef = useRef(null);

  // Auto-scroll on new messages
  useEffect(() => {
    if (chatRef.current) {
      chatRef.current.scrollTop = chatRef.current.scrollHeight;
    }
  }, [messages, loading]);

  // Auto-expand textarea
  const handleInputChange = (e) => {
    const el = e.target;
    setInput(el.value);
    el.style.height = "auto";
    el.style.height = `${Math.max(el.scrollHeight, 24)}px`;
  };

  // File handling
  const handleFileChange = (e) => {
    const newFiles = Array.from(e.target.files);
    setAttachments((prev) => {
      const existing = new Set(prev.map((f) => f.name));
      return [...prev, ...newFiles.filter((f) => !existing.has(f.name))];
    });
    e.target.value = null;
  };

  const removeAttachment = (idx) =>
    setAttachments((prev) => prev.filter((_, i) => i !== idx));

  // Send message
  const sendMessage = async () => {
    if (!input.trim() && attachments.length === 0) return;

    const currentInput = input;
    const newMessages = [
      ...messages,
      { role: "user", content: currentInput || "[Attachment]" },
    ];
    setMessages(newMessages);
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    setLoading(true);
    setStatusMessage("");

    const eventSource = new EventSource(`${API_URL}/stream/${sessionId}`);

    eventSource.addEventListener("status", (e) => {
      setStatusMessage(e.data);
    });

    eventSource.addEventListener("done", async () => {
      eventSource.close();
      try {
        const res = await fetch(`${API_URL}/result/${sessionId}`);
        const data = await res.json();
        setActiveContext(data.active_context || "-");
        setMessages([
          ...newMessages,
          {
            role: "assistant",
            content: data.response,
            chartData: data.chart_data ?? null,
            slidersData: data.sliders_data ?? null,
          },
        ]);
      } catch {
        setMessages([
          ...newMessages,
          { role: "assistant", content: "Error fetching result." },
        ]);
      }
      setLoading(false);
      setStatusMessage(null);
    });

    eventSource.onerror = () => {
      eventSource.close();
      setLoading(false);
      setStatusMessage(null);
    };

    const formData = new FormData();
    formData.append("message", currentInput);
    formData.append("session_id", sessionId);
    formData.append("user_lang", language);
    attachments.forEach((file) => formData.append("files", file));
    setAttachments([]);
    if (fileInputRef.current) fileInputRef.current.value = "";

    try {
      await fetch(API_URL, { method: "POST", body: formData });
    } catch {
      eventSource.close();
      setMessages([
        ...newMessages,
        { role: "assistant", content: "Error contacting server." },
      ]);
      setLoading(false);
      setStatusMessage(null);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  // Save conversation
  const saveConversation = async () => {
    if (!sessionId) return;
    try {
      const res = await fetch(`${API_URL}/save`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId }),
      });
      const data = await res.json();
      alert(data.message || "Conversation saved!");
    } catch {
      alert("Failed to save conversation.");
    }
  };

  return (
    <div className="app">
      {/* Header */}
      <header className="header">
        <h2>Digital Twin Agent</h2>
        <div className="header-right">
          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            className="language-select"
          >
            <option value="Italiano">Italiano</option>
            <option value="English">English</option>
          </select>
          <span className="session">Session: {sessionId}</span>
        </div>
      </header>

      {/* Context bar */}
      <div className="context-header">
        <span className="context">Active context: {activeContext || "-"}</span>
        <button
          className="save-btn"
          onClick={saveConversation}
          disabled={!sessionId}
        >
          💾 Save conversation
        </button>
      </div>

      {/* Chat */}
      <div className="chat-wrapper" ref={chatRef}>
        <div className="chat-container">
          {messages.map((msg, i) => (
            <Message key={i} msg={msg} sessionId={sessionId} />
          ))}
          {loading && <LoadingBubble statusMessage={statusMessage} />}
        </div>
      </div>

      {/* Input */}
      <div className="input-container">
        <div className="input-wrapper">
          <div className="input-inner">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              placeholder="Ask something..."
              rows={1}
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
            <button onClick={sendMessage} disabled={loading}>
              Send
            </button>
          </div>

          {attachments.map((file, idx) => (
            <div key={idx} className="attachment-name">
              {file.name}
              <span
                className="remove-attachment"
                onClick={() => removeAttachment(idx)}
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
