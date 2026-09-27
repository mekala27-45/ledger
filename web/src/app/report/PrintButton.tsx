"use client";

export function PrintButton() {
  return (
    <button type="button" onClick={() => window.print()} className="no-print text-xs px-2 py-1 border border-hairline rounded text-ink2 hover:text-ink">
      Print or save as PDF
    </button>
  );
}
