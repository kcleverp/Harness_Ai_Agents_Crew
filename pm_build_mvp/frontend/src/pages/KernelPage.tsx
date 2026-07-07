import { useEffect, useState } from "react";
import { api, type KernelDoc } from "../lib/api";

const KERNEL_FIELDS: { key: keyof Omit<KernelDoc, "kernel_hash">; label: string; hint: string }[] = [
  { key: "core_thesis", label: "Core Thesis", hint: "한 줄씩 입력 — 제품의 핵심 주장" },
  { key: "non_negotiables", label: "Non-Negotiables", hint: "절대 타협 불가 원칙" },
  { key: "anti_patterns", label: "Anti-Patterns", hint: "하지 말아야 할 것들" },
  { key: "founder_convictions", label: "Founder Convictions", hint: "창업자 확신/근거" },
];

function linesToItems(text: string): string[] {
  return text.split("\n").map((s) => s.trim()).filter(Boolean);
}

function itemsToLines(items: string[]): string {
  return items.join("\n");
}

export function KernelPage() {
  const [kernel, setKernel] = useState<KernelDoc | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.getKernel()
      .then((k) => {
        setKernel(k);
        setDraft({
          core_thesis: itemsToLines(k.core_thesis),
          non_negotiables: itemsToLines(k.non_negotiables),
          anti_patterns: itemsToLines(k.anti_patterns),
          founder_convictions: itemsToLines(k.founder_convictions),
        });
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  const save = async () => {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const body = {
        core_thesis: linesToItems(draft.core_thesis ?? ""),
        non_negotiables: linesToItems(draft.non_negotiables ?? ""),
        anti_patterns: linesToItems(draft.anti_patterns ?? ""),
        founder_convictions: linesToItems(draft.founder_convictions ?? ""),
      };
      const updated = await api.putKernel(body);
      setKernel(updated);
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  if (!kernel && !error) {
    return (
      <div className="page">
        <h2>Founder Kernel</h2>
        <p className="lead">로딩 중…</p>
      </div>
    );
  }

  return (
    <div className="page">
      <h2>Founder Kernel</h2>
      <p className="lead">
        초안은 <code>templates/founder_kernel.sample.json</code>과 같은 To-Do MVP 예시입니다.
        각 필드는 한 줄에 한 항목 · kernel_hash: <code>{kernel?.kernel_hash?.slice(0, 16) ?? "…"}</code>
        {" · "}Run 진행 중에는 Intent Gate의 Edit 경로로만 수정 가능합니다.
      </p>

      {KERNEL_FIELDS.map(({ key, label, hint }) => (
        <div key={key} style={{ marginBottom: 16 }}>
          <div className="review-card-title">{label}</div>
          <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginBottom: 4 }}>{hint}</div>
          <textarea
            className="kernel-editor"
            rows={5}
            value={draft[key] ?? ""}
            onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))}
            spellCheck={false}
          />
        </div>
      ))}

      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <button className="btn primary" onClick={save} disabled={saving}>
          {saving ? "Saving…" : "Save Kernel"}
        </button>
        {saved && <span style={{ fontSize: 12, color: "var(--pass)" }}>저장됨</span>}
      </div>
      {error && <div className="error-banner" style={{ marginTop: 12 }}>{error}</div>}
    </div>
  );
}
