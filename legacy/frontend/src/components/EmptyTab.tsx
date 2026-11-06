export default function EmptyTab(props: { title: string; description: string }) {
  return (
    <section className="empty-state" aria-labelledby="empty-tab-title">
      <p className="eyebrow">Empty state</p>
      <h1 id="empty-tab-title" className="page-title">
        {props.title}
      </h1>
      <p className="muted">{props.description}</p>
    </section>
  );
}
