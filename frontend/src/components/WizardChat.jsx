import { useState, useRef, useEffect } from "react";
import styles from "../styles/Wizard.module.css";

const STEP_LABELS = [
  "Genre",
  "Ambiance",
  "Géographie",
  "Factions",
  "Ressources",
  "Pouvoirs",
  "Événements",
  "Personnages",
  "Départ",
  "Durée",
  "Récap",
];

function renderMarkdown(text) {
  if (!text) return "";

  // Split into blocks to handle tables and code blocks separately
  const blocks = [];
  let remaining = text;

  // Extract code blocks first
  remaining = remaining.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
    const id = `__CODE_${blocks.length}__`;
    blocks.push(`<pre><code>${code.replace(/</g, "&lt;").replace(/>/g, "&gt;")}</code></pre>`);
    return id;
  });

  // Extract markdown tables
  remaining = remaining.replace(
    /(?:^|\n)((?:\|[^\n]+\|\n)+)/g,
    (match) => {
      const lines = match.trim().split("\n").filter(l => l.trim());
      // Skip separator rows (|---|---|)
      const dataLines = lines.filter(l => !/^\|[\s\-:|]+\|$/.test(l));
      if (dataLines.length === 0) return match;

      const headerCells = dataLines[0].split("|").filter(c => c.trim());
      let tableHtml = "<table><thead><tr>";
      headerCells.forEach(c => { tableHtml += `<th>${renderInline(c.trim())}</th>`; });
      tableHtml += "</tr></thead><tbody>";
      for (let i = 1; i < dataLines.length; i++) {
        const cells = dataLines[i].split("|").filter(c => c.trim());
        tableHtml += "<tr>";
        cells.forEach(c => { tableHtml += `<td>${renderInline(c.trim())}</td>`; });
        tableHtml += "</tr>";
      }
      tableHtml += "</tbody></table>";

      const id = `__TABLE_${blocks.length}__`;
      blocks.push(tableHtml);
      return `\n${id}\n`;
    }
  );

  // Process inline markdown
  let html = renderInline(remaining);

  // Headers (h2, h3)
  html = html.replace(/^### (.+)$/gm, '<h4>$1</h4>');
  html = html.replace(/^## (.+)$/gm, '<h3>$1</h3>');
  // Horizontal rules
  html = html.replace(/^---+$/gm, '<hr/>');
  // Unordered lists
  html = html.replace(/^[-*] (.+)$/gm, '<li>$1</li>');
  // Ordered lists
  html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');
  // Paragraphs
  html = html.replace(/\n\n/g, '</p><p>');
  // Line breaks
  html = html.replace(/\n/g, '<br/>');

  // Wrap consecutive <li> in <ul>
  html = html.replace(/((?:<li>.*?<\/li>\s*(?:<br\/>)?)+)/g, '<ul>$1</ul>');
  html = html.replace(/<br\/>\s*<\/ul>/g, '</ul>');
  html = html.replace(/<ul>\s*<br\/>/g, '<ul>');

  // Restore extracted blocks
  blocks.forEach((block, i) => {
    html = html.replace(new RegExp(`__(?:CODE|TABLE)_${i}__`), block);
  });

  // Strip the step indicator line (Étape N/11) — it's shown in the progress bar
  html = html.replace(/<p>\s*[ÉéEe]tape\s+\d{1,2}\s*\/\s*11\s*<\/p>/gi, '');
  html = html.replace(/^[ÉéEe]tape\s+\d{1,2}\s*\/\s*11\s*<br\/>/gim, '');

  return `<p>${html}</p>`;
}

function renderInline(text) {
  return text
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`([^`]+)`/g, '<code>$1</code>');
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
