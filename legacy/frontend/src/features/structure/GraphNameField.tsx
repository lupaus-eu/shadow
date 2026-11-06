import { GRAPH_NAME_MAX_LENGTH } from "../../api/orgTwinStructure";
import { graphNameTooLong } from "./graphNames";

export default function GraphNameField(props: {
  idPrefix: string;
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  const inputId = `${props.idPrefix}-name`;
  const helpId = `${props.idPrefix}-name-help`;
  // A stored name may predate the limit; it shows in full and must be shortened.
  const tooLong = graphNameTooLong(props.value);

  return (
    <div className="form-row">
      <label className="form-label form-label--required" htmlFor={inputId}>
        Name
      </label>
      <input
        id={inputId}
        className="input"
        value={props.value}
        maxLength={GRAPH_NAME_MAX_LENGTH}
        aria-describedby={helpId}
        aria-invalid={tooLong ? "true" : undefined}
        onChange={(event) => props.onChange(event.target.value)}
        disabled={props.disabled}
      />
      <p
        id={helpId}
        className={
          tooLong ? "structure-name-help structure-name-help--error" : "structure-name-help"
        }
      >
        {tooLong
          ? `Name must be at most ${GRAPH_NAME_MAX_LENGTH} characters.`
          : `Max ${GRAPH_NAME_MAX_LENGTH} characters.`}
      </p>
    </div>
  );
}
