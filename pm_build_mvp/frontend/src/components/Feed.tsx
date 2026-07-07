import { useEffect, useRef, useState } from "react";
import type { FeedMessage } from "../lib/types";

const DOMAIN_AVATAR: Record<string, string> = {
  workflow: "#3f86d8",
  decision: "#8b60d2",
  qa: "#b3821d",
  system: "#278839",
  patch: "#d3453e",
  translation: "#30a7b0",
  cognition: "#30a7b0",
};

function Avatar({ agent, domain }: { agent: string; domain: string }) {
  const initials = agent
    .split(/[\s·/]+/)
    .slice(0, 2)
    .map((w) => w[0] ?? "")
    .join("")
    .toUpperCase();
  return (
    <div className="avatar" style={{ background: DOMAIN_AVATAR[domain] ?? "#51555c" }}>
      {initials}
    </div>
  );
}

function MessageRow({
  msg,
  selected,
  onSelect,
}: {
  msg: FeedMessage;
  selected: boolean;
  onSelect: (msg: FeedMessage) => void;
}) {
  return (
    <div
      className={`msg-row msg-clickable ${selected ? "selected" : ""} ${msg.status === "warn" || msg.status === "fail" ? msg.status : ""}`}
      onClick={() => onSelect(msg)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect(msg);
        }
      }}
    >
      <div className={`status-bar ${msg.status}`} />
      <Avatar agent={msg.agent} domain={msg.domain} />
      <div className="msg-body">
        <div className="msg-head">
          <span className="msg-agent">{msg.agent}</span>
          <span className={`pill ${msg.domain}`}>{msg.domain}</span>
          <span className="msg-time">{msg.timestamp}</span>
        </div>
        <div className="msg-content">{msg.content}</div>
        {msg.artifact && (
          <div className="msg-artifact">
            artifact · <code>{msg.artifact}</code>
          </div>
        )}
      </div>
    </div>
  );
}

export function Feed({
  messages,
  selectedPhase,
  onSelectAgent,
}: {
  messages: FeedMessage[];
  selectedPhase?: string | null;
  onSelectAgent?: (msg: FeedMessage) => void;
}) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (autoScroll) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, autoScroll]);

  const onScroll = () => {
    const el = containerRef.current;
    if (!el) return;
    setAutoScroll(el.scrollHeight - el.scrollTop - el.clientHeight < 80);
  };

  const handleSelect = (msg: FeedMessage) => {
    onSelectAgent?.(msg);
  };

  if (messages.length === 0) {
    return (
      <div className="feed-canvas">
        <div className="feed-empty">
          <div className="feed-empty-icon">◌</div>
          <div>아직 진행 이벤트가 없습니다. Run을 시작하면 실시간 상태가 표시됩니다.</div>
        </div>
      </div>
    );
  }

  let lastRole = "";
  return (
    <div ref={containerRef} className="feed-canvas" onScroll={onScroll}>
      <div className="feed-inner">
        {messages.map((msg) => {
          const divider = msg.roleTitle !== lastRole;
          lastRole = msg.roleTitle;
          return (
            <div key={msg.id}>
              {divider && (
                <div
                  className="phase-divider phase-divider-clickable"
                  onClick={() => onSelectAgent?.({ ...msg, phase: msg.phase })}
                  role={onSelectAgent ? "button" : undefined}
                  tabIndex={onSelectAgent ? 0 : undefined}
                >
                  {msg.roleTitle.toUpperCase()}
                </div>
              )}
              <MessageRow
                msg={msg}
                selected={selectedPhase === msg.phase}
                onSelect={handleSelect}
              />
            </div>
          );
        })}
        <div ref={bottomRef} style={{ height: 24 }} />
      </div>
    </div>
  );
}
