import { useState, useRef, useEffect } from "react";
import styles from "../styles/Wizard.module.css";

const STEP_LABELS = [
  "Genre",
  "Ton",
  "Echelle",
  "Factions",
  "Ressources",
  "Regions",
  "Technologie",
  "Relations",
  "Conflits",
  "Resume",
  "Validation",
];

function renderMarkdown(text) {
  if (!text) return "";
  let html = text
    // Code blocks
    .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>')
    // Inline code
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    // Bold
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    // Italic
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    // Unordered lists
    .replace(/^[-*] (.+)$/gm, '<li>$1</li>')
    // Ordered lists
    .replace(/^\d+\. (.+)$/gm, '<li>$1</li>')
    // Paragraphs
    .replace(/\n\n/g, '</p><p>')
    // Line breaks
    .replace(/\n/g, '<br/>');

  // Wrap consecutive <li> in <ul>
  html = html.replace(/((?:<li>.*?<\/li>\s*(?:<br\/>)?)+)/g, '<ul>$1</ul>');
  html = html.replace(/<br\/>\s*<\/ul>/g, '</ul>');
  html = html.replace(/<ul>\s*<br\/>/g, '<ul>');

  return `<p>${html}</p>`;
}

export default function WizardChat({ messages, onSend, isLoading, step }) {
  const [input, setInput] = useState("");
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  const handleSubmit = (e) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;
    onSend(trimmed);
    setInput("");
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <>
      {/* Step progress bar */}
      <div className={styles.stepBar}>
        {STEP_LABELS.map((label, i) => {
          const stepNum = i + 1;
          let cls = styles.stepDot;
          if (stepNum < step) cls += ` ${styles.completed}`;
          else if (stepNum === step) cls += ` ${styles.active}`;
          return (
            <div key={stepNum} className={cls}>
              <span className={styles.stepNumber}>{stepNum}</span>
              {label}
            </div>
          );
        })}
      </div>

      {/* Messages */}
      <div className={styles.messages}>
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`${styles.message} ${
              msg.role === "assistant" ? styles.assistant : styles.user
            }`}
          >
            <div
              className={styles.messageContent}
              dangerouslySetInnerHTML={{
                __html:
                  msg.role === "assistant"
                    ? renderMarkdown(msg.content)
                    : msg.content.replace(/</g, "&lt;").replace(/>/g, "&gt;"),
              }}
            />
          </div>
        ))}
        {isLoading && (
          <div className={styles.loadingDots}>
            <span />
            <span />
            <span />
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <form className={styles.inputArea} onSubmit={handleSubmit}>
        <textarea
          ref={inputRef}
          className={styles.inputField}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Decrivez votre monde..."
          disabled={isLoading}
          rows={1}
        />
        <button
          type="submit"
          className={styles.sendBtn}
          disabled={isLoading || !input.trim()}
        >
          Envoyer
        </button>
      </form>
    </>
  );
}
