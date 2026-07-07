import { useMemo } from "react";
import type { JSX } from "react";

/** Minimal dependency-free markdown renderer for workflow artifacts.
 *  Supports: headings, bold/italic/inline-code, fenced code blocks,
 *  bullet/numbered lists, blockquotes, hr, tables, paragraphs. */

function renderInline(text: string): (string | JSX.Element)[] {
  const out: (string | JSX.Element)[] = [];
  // tokens: `code`, **bold**, *italic*
  const re = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let key = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith("`")) out.push(<code key={key++}>{tok.slice(1, -1)}</code>);
    else if (tok.startsWith("**")) out.push(<strong key={key++}>{tok.slice(2, -2)}</strong>);
    else out.push(<em key={key++}>{tok.slice(1, -1)}</em>);
    last = m.index + tok.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

function parse(md: string): JSX.Element[] {
  const lines = md.split(/\r?\n/);
  const blocks: JSX.Element[] = [];
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (line.trim() === "") { i++; continue; }

    // fenced code block
    if (line.trimStart().startsWith("```")) {
      const code: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trimStart().startsWith("```")) {
        code.push(lines[i]);
        i++;
      }
      i++; // closing fence
      blocks.push(<pre key={key++} className="md-code">{code.join("\n")}</pre>);
      continue;
    }

    // heading
    const h = /^(#{1,4})\s+(.*)$/.exec(line);
    if (h) {
      const level = h[1].length;
      const content = renderInline(h[2]);
      if (level === 1) blocks.push(<h1 key={key++}>{content}</h1>);
      else if (level === 2) blocks.push(<h2 key={key++}>{content}</h2>);
      else if (level === 3) blocks.push(<h3 key={key++}>{content}</h3>);
      else blocks.push(<h4 key={key++}>{content}</h4>);
      i++;
      continue;
    }

    // hr
    if (/^\s*(-{3,}|\*{3,})\s*$/.test(line)) {
      blocks.push(<hr key={key++} />);
      i++;
      continue;
    }

    // blockquote
    if (line.trimStart().startsWith(">")) {
      const quote: string[] = [];
      while (i < lines.length && lines[i].trimStart().startsWith(">")) {
        quote.push(lines[i].replace(/^\s*>\s?/, ""));
        i++;
      }
      blocks.push(<blockquote key={key++}>{renderInline(quote.join(" "))}</blockquote>);
      continue;
    }

    // table
    if (line.includes("|") && i + 1 < lines.length && /^\s*\|?[\s:|-]+\|?\s*$/.test(lines[i + 1]) && lines[i + 1].includes("-")) {
      const cells = (l: string) => l.split("|").map((c) => c.trim()).filter((c, idx, arr) => !(c === "" && (idx === 0 || idx === arr.length - 1)));
      const headers = cells(line);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && lines[i].includes("|")) {
        rows.push(cells(lines[i]));
        i++;
      }
      blocks.push(
        <table key={key++} className="md-table">
          <thead><tr>{headers.map((hc, j) => <th key={j}>{renderInline(hc)}</th>)}</tr></thead>
          <tbody>{rows.map((r, ri) => <tr key={ri}>{r.map((c, ci) => <td key={ci}>{renderInline(c)}</td>)}</tr>)}</tbody>
        </table>,
      );
      continue;
    }

    // list (bullet or numbered)
    if (/^\s*([-*+]|\d+\.)\s+/.test(line)) {
      const ordered = /^\s*\d+\./.test(line);
      const items: string[] = [];
      while (i < lines.length && /^\s*([-*+]|\d+\.)\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*([-*+]|\d+\.)\s+/, ""));
        i++;
      }
      const li = items.map((it, j) => <li key={j}>{renderInline(it)}</li>);
      blocks.push(ordered ? <ol key={key++}>{li}</ol> : <ul key={key++}>{li}</ul>);
      continue;
    }

    // paragraph (merge consecutive non-empty plain lines)
    const para: string[] = [line];
    i++;
    while (
      i < lines.length && lines[i].trim() !== "" &&
      !/^(#{1,4})\s/.test(lines[i]) && !lines[i].trimStart().startsWith("```") &&
      !/^\s*([-*+]|\d+\.)\s+/.test(lines[i]) && !lines[i].trimStart().startsWith(">")
    ) {
      para.push(lines[i]);
      i++;
    }
    blocks.push(<p key={key++}>{renderInline(para.join(" "))}</p>);
  }

  return blocks;
}

export function Markdown({ source }: { source: string }) {
  const blocks = useMemo(() => parse(source), [source]);
  return <div className="markdown">{blocks}</div>;
}
