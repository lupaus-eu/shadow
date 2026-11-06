import { Fragment } from "react";

import { parseRichText, type Block, type Inline } from "./rich-text";

function Inlines({ nodes }: { nodes: Inline[] }) {
  return (
    <>
      {nodes.map((node, index) => {
        if (typeof node === "string") return <Fragment key={index}>{node}</Fragment>;
        if ("b" in node) return <strong key={index}><Inlines nodes={node.b} /></strong>;
        if ("i" in node) return <em key={index}><Inlines nodes={node.i} /></em>;
        return <a key={index} href={node.href} rel="noopener noreferrer" target="_blank">{node.a}</a>;
      })}
    </>
  );
}

function Lines({ lines }: { lines: Inline[][] }) {
  return <>{lines.map((line, index) => <Fragment key={index}>{index > 0 ? <br /> : null}<Inlines nodes={line} /></Fragment>)}</>;
}

function BlockView({ block }: { block: Block }) {
  if ("p" in block) return <p className="m-0"><Lines lines={block.p} /></p>;
  const Tag = "ul" in block ? "ul" : "ol";
  const items = "ul" in block ? block.ul : block.ol;
  return <Tag className="m-0 flex flex-col gap-0.5 pl-5">{items.map((item, index) => <li key={index}><Inlines nodes={item} /></li>)}</Tag>;
}

/** A formatted description as React elements: nothing is ever injected as HTML. */
export function RichText({ text }: { text: string }) {
  return <div className="yc-description flex flex-col gap-2 text-[13px]">{parseRichText(text).map((block, index) => <BlockView key={index} block={block} />)}</div>;
}
