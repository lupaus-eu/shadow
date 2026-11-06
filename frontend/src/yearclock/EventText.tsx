const URL_PATTERN = /(https?:\/\/[^\s<>"]+)/g;
// Sentence punctuation right after a link belongs to the text, not the URL.
const TRAILING_PUNCTUATION = /[).,;:!?\]]+$/;

/** Plain-text description with preserved line breaks and safe http(s) links. */
export function EventText({ text }: { text: string }) {
  const parts = text.split(URL_PATTERN);
  return (
    <p className="yc-description m-0 whitespace-pre-wrap text-[13px]">
      {parts.map((part, index) => {
        if (index % 2 === 0) return <span key={index}>{part}</span>;
        const trailing = part.match(TRAILING_PUNCTUATION)?.[0] ?? "";
        const url = trailing ? part.slice(0, -trailing.length) : part;
        return (
          <span key={index}>
            <a href={url} rel="noopener noreferrer" target="_blank">
              {url}
            </a>
            {trailing}
          </span>
        );
      })}
    </p>
  );
}
