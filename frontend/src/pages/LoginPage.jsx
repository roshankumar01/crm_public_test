import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";

export default function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  if (user) return <Navigate to="/crm" replace />;

  async function handleSubmit(event) {
    event.preventDefault();
    try {
      setLoading(true);
      setError("");
      await login(username, password);
      navigate("/crm", { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return <div className="login-page">
    <form className="login-card" onSubmit={handleSubmit}>
      <div className="brand-mark login-brand">C</div>
      <div className="eyebrow">COURSE UPSELL SYSTEM · GWG</div>
      <h1>Sign in</h1>
      <p>Sign in to manage course opportunities, leads, and campaign follow-up.</p>
      <label>Username</label>
      <input value={username} onChange={e => setUsername(e.target.value)} autoComplete="username" required />
      <label>Password</label>
      <input type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete="current-password" required />
      <button className="primary-button" type="submit" disabled={loading}>{loading ? "Signing in..." : "Sign in"}</button>
      {error && <div className="form-error">{error}</div>}
    </form>
  </div>;
}
