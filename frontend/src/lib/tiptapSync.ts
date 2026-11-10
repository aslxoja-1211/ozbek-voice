import type { Editor } from "@tiptap/react";
import type { Node as ProseMirrorNode } from "@tiptap/pm/model";

function escapeHtml(raw: string): string {
  return raw
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatInlineMarkdown(line: string): string {
  const escaped = escapeHtml(line);
  return escaped.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

function serializeInlineNode(node: ProseMirrorNode): string {
  let out = "";
  node.forEach((child) => {
    if (child.isText) {
      const text = child.text ?? "";
      const isBold = child.marks.some((m) => m.type.name === "bold");
      out += isBold ? `**${text}**` : text;
    } else if (child.type.name === "hardBreak") {
      out += "\n";
    }
  });
  return out;
}

/**
 * Serialize Tiptap document into clean text preserving headings, lists, and bold marks
 * so the LLM Intent Engine understands structure accurately.
 */
export function serializeEditorState(editor: Editor): string {
  const blocks: string[] = [];

  editor.state.doc.forEach((node) => {
    if (node.type.name === "heading") {
      const level = Number(node.attrs.level ?? 1);
      const prefix = "#".repeat(Math.min(Math.max(level, 1), 3));
      blocks.push(`${prefix} ${serializeInlineNode(node)}`);
    } else if (node.type.name === "bulletList") {
      const items: string[] = [];
      node.forEach((listItem) => {
        const line = listItem.textContent.trim();
        if (line) items.push(`- ${line}`);
      });
      if (items.length > 0) blocks.push(items.join("\n"));
    } else if (node.type.name === "orderedList") {
      const items: string[] = [];
      let idx = 1;
      node.forEach((listItem) => {
        const line = listItem.textContent.trim();
        if (line) {
          items.push(`${idx}. ${line}`);
          idx++;
        }
      });
      if (items.length > 0) blocks.push(items.join("\n"));
    } else if (node.type.name === "paragraph") {
      const text = serializeInlineNode(node);
      if (text.length > 0) blocks.push(text);
    } else {
      const fallback = node.textContent;
      if (fallback) blocks.push(fallback);
    }
  });

  return blocks.join("\n\n");
}

/**
 * Convert plain / lightly formatted Markdown output from Diff Engine to safe Tiptap HTML.
 */
export function markdownTextToTiptapHtml(text: string): string {
  if (!text.trim()) return "";

  const lines = text.split(/\r?\n/);
  const htmlChunks: string[] = [];
  let inList = false;

  const closeList = () => {
    if (inList) {
      htmlChunks.push("</ul>");
      inList = false;
    }
  };

  for (const rawLine of lines) {
    const trimmed = rawLine.trim();
    if (!trimmed) {
      closeList();
      continue;
    }

    if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
      if (!inList) {
        htmlChunks.push("<ul>");
        inList = true;
      }
      htmlChunks.push(`<li>${formatInlineMarkdown(trimmed.slice(2))}</li>`);
      continue;
    }

    closeList();

    if (trimmed.startsWith("## ")) {
      htmlChunks.push(`<h2>${formatInlineMarkdown(trimmed.slice(3))}</h2>`);
    } else if (trimmed.startsWith("# ")) {
      htmlChunks.push(`<h1>${formatInlineMarkdown(trimmed.slice(2))}</h1>`);
    } else {
      htmlChunks.push(`<p>${formatInlineMarkdown(rawLine)}</p>`);
    }
  }

  closeList();
  return htmlChunks.join("");
}

/**
 * Apply updated text to Tiptap without breaking undo/redo history.
 */
export function applyTextToTiptap(editor: Editor, newText: string): void {
  if (!newText.trim()) {
    editor.commands.clearContent(true);
    return;
  }
  const html = markdownTextToTiptapHtml(newText);
  editor.commands.setContent(html, true);
  editor.commands.focus("end");
}
