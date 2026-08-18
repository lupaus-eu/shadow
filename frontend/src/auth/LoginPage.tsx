import { useAuth } from "./AuthContext";

export default function LoginPage(props: {
  returnTo: string;
  authenticationFailed?: boolean;
}) {
  const { authError, login } = useAuth();
  const message = props.authenticationFailed
    ? "Authentication failed. Please try again."
    : authError;

  return (
    <main className="center-page">
      <section className="home-panel" aria-labelledby="login-title">
        <p className="eyebrow">Schatten</p>
        <h1 id="login-title" className="display-title">
          Sign in
        </h1>
        <p className="muted">Sign in with your organisation account.</p>
        {message ? (
          <div className="alert alert--danger" role="alert">
            <p className="alert__title">Authentication error</p>
            <p className="alert__text">{message}</p>
          </div>
        ) : null}
        <button
          className="btn btn--primary"
          type="button"
          onClick={() => login(props.returnTo)}
        >
          Sign in
        </button>
      </section>
    </main>
  );
}
