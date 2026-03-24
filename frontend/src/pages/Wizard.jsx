import { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { wizard } from "../services/api";
import WizardChat from "../components/WizardChat";
import styles from "../styles/Wizard.module.css";

export default function Wizard() {
  const { sessionId } = useParams();
  const navigate = useNavigate();

  const [messages, setMessages] = useState([]);
  const [step, setStep] = useState(1);
  const [isLoading, setIsLoading] = useState(false);
  const [isFinalized, setIsFinalized] = useState(false);
  const [worldId, setWorldId] = useState(null);
  const [error, setError] = useState(null);
  const [initializing, setInitializing] = useState(true);

  // Start new session if no sessionId
  useEffect(() => {
    if (!sessionId) {
      wizard
        .start()
        .then((data) => {
          navigate(`/wizard/${data.session_id}`, { replace: true });
        })
        .catch((err) => {
          setError(err.message);
          setInitializing(false);
        });
    }
  }, [sessionId, navigate]);

  // Load history when sessionId is present
  useEffect(() => {
    if (!sessionId) return;
    setInitializing(true);
    wizard
      .getHistory(sessionId)
      .then((data) => {
        setMessages(data.messages || []);
        setStep(data.current_step || 1);
        setIsFinalized(data.is_finalized || false);
        setWorldId(data.world_id || null);
        setInitializing(false);
      })
      .catch((err) => {
        setError(err.message);
        setInitializing(false);
      });
  }, [sessionId]);

  const handleSend = useCallback(
    async (content) => {
      if (!sessionId || isLoading) return;

      const userMsg = { role: "user", content };
      setMessages((prev) => [...prev, userMsg]);
      setIsLoading(true);
      setError(null);

      try {
        const data = await wizard.sendMessage(sessionId, content);
        const assistantMsg = {
          role: "assistant",
          content: data.response || data.message,
        };
        setMessages((prev) => [...prev, assistantMsg]);
        if (data.current_step) setStep(data.current_step);
      } catch (err) {
        setError(err.message);
      } finally {
        setIsLoading(false);
      }
    },
    [sessionId, isLoading]
  );

  const handleFinalize = useCallback(async () => {
    if (!sessionId) return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await wizard.finalize(sessionId);
      setIsFinalized(true);
      if (data.summary) {
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: data.summary,
          },
        ]);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  }, [sessionId]);

  const handleValidate = useCallback(async () => {
    if (!sessionId) return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await wizard.validate(sessionId);
      if (data.world_id) {
        navigate(`/world/${data.world_id}`);
      }
    } catch (err) {
      setError(err.message);
      setIsLoading(false);
    }
  }, [sessionId, navigate]);

  if (!sessionId || initializing) {
    return (
      <div className={styles.loadingPage}>
        <div className={styles.spinner} />
        Initialisation du wizard...
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1 className={styles.title}>Forge de Monde</h1>
        <Link to="/dashboard" className={styles.backLink}>
          Retour au tableau de bord
        </Link>
      </div>

      <WizardChat
        messages={messages}
        onSend={handleSend}
        isLoading={isLoading}
        step={step}
      />

      {error && <div className={styles.error}>{error}</div>}

      {(step >= 10 || isFinalized) && (
        <div className={styles.actions}>
          {!isFinalized && (
            <button
              className={styles.finalizeBtn}
              onClick={handleFinalize}
              disabled={isLoading}
            >
              Finaliser la configuration
            </button>
          )}
          {isFinalized && (
            <button
              className={styles.validateBtn}
              onClick={handleValidate}
              disabled={isLoading}
            >
              Valider et creer le monde
            </button>
          )}
        </div>
      )}
    </div>
  );
}
