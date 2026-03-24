import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import styles from "../styles/Login.module.css";

export default function Login() {
  const [isRegister, setIsRegister] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const { login, register } = useAuth();
  const navigate = useNavigate();

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setSubmitting(true);

    try {
      if (isRegister) {
        await register(email, password);
      } else {
        await login(email, password);
      }
      navigate("/dashboard");
    } catch (err) {
      setError(err.detail || err.message || "Une erreur est survenue");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className={styles.container}>
      <div className={styles.card}>
        <h1 className={styles.title}>WorldForge</h1>
        <p className={styles.subtitle}>
          {isRegister ? "Créer un compte" : "Connexion à votre atelier"}
        </p>

        <form className={styles.form} onSubmit={handleSubmit}>
          {error && <div className={styles.error}>{error}</div>}

          <div className={styles.field}>
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="votre@email.com"
              required
              autoFocus
            />
          </div>

          <div className={styles.field}>
            <label htmlFor="password">Mot de passe</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Mot de passe"
              required
              minLength={6}
            />
          </div>

          <button
            type="submit"
            className={`btn-primary ${styles.submit}`}
            disabled={submitting}
          >
            {submitting
              ? "Chargement..."
              : isRegister
                ? "Créer le compte"
                : "Se connecter"}
          </button>
        </form>

        <div className={styles.toggle}>
          {isRegister ? "Déjà un compte ?" : "Pas encore de compte ?"}{" "}
          <button
            type="button"
            onClick={() => {
              setIsRegister(!isRegister);
              setError("");
            }}
          >
            {isRegister ? "Se connecter" : "Créer un compte"}
          </button>
        </div>
      </div>
    </div>
  );
}
