import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <main className="center-page">
      <section className="home-panel">
        <p className="eyebrow">Not found</p>
        <h1 className="page-title">Page not found</h1>
        <p className="muted">The requested Shadow page does not exist.</p>
        <Link className="btn btn--primary" to="/">
          Go home
        </Link>
      </section>
    </main>
  );
}
