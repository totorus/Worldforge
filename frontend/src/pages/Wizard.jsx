import { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { wizard } from "../services/api";
import WizardChat from "../components/WizardChat";
import styles from "../styles/Wizard.module.css";

const GENERATION_STEPS = [
  "Conversation avec le conteur...",
  "Création de la configuration du monde...",
  "Validation du monde...",
  "C'est prêt !",
];

export default function Wizard() {
  const { sessionId } = useParams();
  const navigate = useNavigate();

  const [messages, setMessages] = useState([]);
  const [step, setStep] = useState(1);
  const [isLoading, setIsLoading] = useState(false);
  const [worldId, setWorldId] = useState(null);
  const [error, setError] = useState(null);
  const [initializing, setInitializing] = useState(true);

  // Generation overlay state
  const [generating, setGenerating] = useState(false);
  const [genStep, setGenStep] = useState(0);
  const [genError, setGenError] = useState(null);

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
        setStep(data.step || 1);
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
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: data.message },
        ]);
        if (data.step) setStep(data.step);
      } catch (err) {
        setError(err.message);
      } finally {
        setIsLoading(false);
      }
    },
    [sessionId, isLoading]
  );

  const handleCreateWorld = useCallback(async () => {
    if (!sessionId) return;
    setGenerating(true);
    setGenStep(0);
    setGenError(null);

    try {
      // Step 1: Finalize — ask Kimi to generate the JSON
      setGenStep(1);
      await wizard.finalize(sessionId);

      // Step 2: Validate — check the JSON and save to world
      setGenStep(2);
      const data = await wizard.validate(sessionId);

      if (data.valid === false) {
        setGenError(
          "Le monde généré n'est pas valide. Relance la création ou continue la conversation pour ajuster."
        );
        setGenerating(false);
        return;
      }

      // Step 3: Done!
      setGenStep(3);
      setTimeout(() => {
        navigate(`/world/${data.world_id}`);
      }, 1500);
    } catch (err) {
      setGenError(err.message || "Erreur lors de la création du monde");
      setGenerating(false);
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
      {/* Generation overlay */}
      {generating && (
        <div className={styles.genOverlay}>
          <div className={styles.genCard}>
            <h2 className={styles.genTitle}>Création de ton monde</h2>
            <div className={styles.genSteps}>
              {GENERATION_STEPS.map((label, i) => (
                <div
                  key={i}
                  className={`${styles.genStepRow} ${
                    i < genStep
                      ? styles.genDone
                      : i === genStep
                      ? styles.genActive
                      : ""
                  }`}
                >
                  <div className={styles.genDot}>
                    {i < genStep ? "✓" : i === genStep ? "" : ""}
                  </div>
                  <span>{label}</span>
                  {i === genStep && !genError && (
                    <div className={styles.genSpinner} />
                  )}
                </div>
              ))}
            </div>
            {genError && (
              <div className={styles.genError}>
                <p>{genError}</p>
                <button
                  className={styles.finalizeBtn}
                  onClick={() => {
                    setGenerating(false);
                    setGenError(null);
                  }}
                >
                  Retour à la conversation
                </button>
              </div>
            )}
          </div>
        </div>
      )}

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

      {step >= 8 && !generating && (
        <div className={styles.actions}>
          <button
            className={styles.createBtn}
            onClick={handleCreateWorld}
            disabled={isLoading}
          >
            Créer mon monde
          </button>
          <span className={styles.actionsHint}>
            Tu peux aussi continuer la conversation
          </span>
        </div>
      )}
    </div>
  );
}
