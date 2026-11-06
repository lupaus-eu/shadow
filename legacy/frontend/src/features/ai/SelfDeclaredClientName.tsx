// ADR-015: an OAuth client chooses its own name, and any client can copy a
// known name. The name is isolated in <bdi> so bidirectional text cannot
// reorder the label or the surrounding page, and it is always labelled.
export default function SelfDeclaredClientName(props: { name: string }) {
  return (
    <span className="ai-client-name">
      <bdi className="ai-client-name__value">{props.name}</bdi>
      <span className="ai-client-name__label">(self-declared by the client)</span>
    </span>
  );
}
