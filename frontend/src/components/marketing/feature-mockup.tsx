import { Bot, FileText, Search, TrendingUp, User, Wrench } from "lucide-react";

import { cn } from "@/lib/utils";

type MockupKind = "agents" | "rag" | "billing";

interface FeatureMockupProps {
  kind: MockupKind;
  className?: string;
  copy?: FeatureMockupCopy;
}

export interface FeatureMockupCopy {
  agentQuestion: string;
  agentTool: string;
  assistant: string;
  agentAnswer: string;
  askAnything: string;
  ragQuery: string;
  ragResults: { title: string; snippet: string }[];
  activityTitle: string;
  activityTrend: string;
  activityLabels: [string, string, string];
}

const DEFAULT_COPY: FeatureMockupCopy = {
  agentQuestion: "Summarize the key points from the uploaded documents.",
  agentTool: "knowledge.search · 4 documents",
  assistant: "Assistant",
  agentAnswer: "The documents highlight three priorities: improve onboarding, clarify responsibilities, and shorten review cycles.",
  askAnything: "Ask anything…",
  ragQuery: "project requirements",
  ragResults: [
    { title: "project-overview.pdf", snippet: "...goals, scope, milestones, and delivery requirements..." },
    { title: "team-notes.md", snippet: "...decisions and action items from the latest review..." },
    { title: "product-guide.docx", snippet: "...usage instructions and frequently asked questions..." },
  ],
  activityTitle: "Workspace activity",
  activityTrend: "+18% from last week",
  activityLabels: ["Active", "Chats", "Documents"],
};

/** Stylized mini-UIs that hint at the actual product. Pure CSS/SVG, no real data. */
export function FeatureMockup({ kind, className, copy = DEFAULT_COPY }: FeatureMockupProps) {
  if (kind === "agents") return <AgentMockup className={className} copy={copy} />;
  if (kind === "rag") return <RagMockup className={className} copy={copy} />;
  return <BillingMockup className={className} copy={copy} />;
}

function MockFrame({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        "border-foreground/15 bg-card relative w-full max-w-lg overflow-hidden rounded-2xl border shadow-2xl",
        className,
      )}
    >
      <div className="border-foreground/10 flex items-center gap-1.5 border-b px-4 py-2.5">
        <span className="bg-foreground/20 h-2 w-2 rounded-full" />
        <span className="bg-foreground/20 h-2 w-2 rounded-full" />
        <span className="bg-foreground/20 h-2 w-2 rounded-full" />
      </div>
      {children}
    </div>
  );
}

function AgentMockup({ className, copy }: { className?: string; copy: FeatureMockupCopy }) {
  return (
    <MockFrame className={className}>
      <div className="space-y-3 p-4">
        <div className="flex justify-end">
          <div className="bg-foreground text-background flex max-w-[80%] items-center gap-2 rounded-2xl rounded-tr-sm px-3 py-2 text-xs">
            <span>{copy.agentQuestion}</span>
            <User className="h-3 w-3 opacity-60" />
          </div>
        </div>

        <div className="flex">
          <div className="border-brand/40 bg-brand/15 flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[10px]">
            <Wrench className="h-3 w-3" />
            <span className="text-foreground/80">{copy.agentTool}</span>
          </div>
        </div>

        <div className="flex">
          <div className="bg-card border-foreground/10 max-w-[88%] rounded-2xl rounded-tl-sm border p-3">
            <div className="text-foreground/55 mb-1.5 flex items-center gap-1.5">
              <Bot className="h-3 w-3" />
              <span className="font-mono text-[10px] tracking-wider uppercase">{copy.assistant}</span>
            </div>
            <p className="text-foreground text-xs leading-relaxed">
              {copy.agentAnswer}
            </p>
          </div>
        </div>

        <div className="border-foreground/10 mt-2 flex items-center gap-2 rounded-lg border px-3 py-2">
          <span className="text-foreground/40 flex-1 text-xs">{copy.askAnything}</span>
          <kbd className="border-foreground/15 text-foreground/50 inline-flex items-center gap-0.5 rounded border px-1.5 py-0.5 font-mono text-[10px]">
            ⌘ ↵
          </kbd>
        </div>
      </div>
    </MockFrame>
  );
}

function RagMockup({ className, copy }: { className?: string; copy: FeatureMockupCopy }) {
  const scores = [0.94, 0.87, 0.82];
  const results = copy.ragResults.map((result, index) => ({ ...result, score: scores[index] ?? 0.8 }));
  return (
    <MockFrame className={className}>
      <div className="p-4">
        <div className="border-foreground/10 mb-3 flex items-center gap-2 rounded-lg border px-3 py-2">
          <Search className="text-foreground/40 h-3.5 w-3.5" />
          <span className="text-foreground text-xs">{copy.ragQuery}</span>
        </div>
        <ul className="space-y-2.5">
          {results.map((r) => (
            <li key={r.title} className="border-foreground/10 rounded-lg border p-3">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5">
                  <FileText className="text-foreground/50 h-3 w-3" />
                  <span className="text-foreground font-mono text-[11px]">{r.title}</span>
                </div>
                <span className="bg-brand text-brand-foreground rounded-full px-1.5 py-0.5 font-mono text-[10px] tabular-nums">
                  {r.score.toFixed(2)}
                </span>
              </div>
              <p className="text-foreground/65 mt-1.5 text-[11px] leading-snug">{r.snippet}</p>
            </li>
          ))}
        </ul>
      </div>
    </MockFrame>
  );
}

function BillingMockup({ className, copy }: { className?: string; copy: FeatureMockupCopy }) {
  const bars = [22, 28, 32, 30, 38, 42, 48, 45, 52, 58, 64, 72];
  const max = Math.max(...bars);
  return (
    <MockFrame className={className}>
      <div className="space-y-4 p-4">
        <div>
          <p className="text-foreground/55 font-mono text-[10px] tracking-wider uppercase">
            {copy.activityTitle}
          </p>
          <p className="text-foreground font-display mt-1 text-3xl font-bold tracking-tight">
            2,840
          </p>
          <p className="text-brand mt-0.5 flex items-center gap-1 text-xs font-medium">
            <TrendingUp className="h-3 w-3" />
            {copy.activityTrend}
          </p>
        </div>

        <div className="flex h-20 items-end gap-1">
          {bars.map((b, i) => (
            <div
              key={i}
              className="bg-foreground/15 flex-1 rounded-sm"
              style={{ height: `${(b / max) * 100}%` }}
            >
              <div
                className="bg-brand h-1 w-full"
                style={{ display: i === bars.length - 1 ? "block" : "none" }}
              />
            </div>
          ))}
        </div>

        <div className="border-foreground/10 grid grid-cols-3 gap-2 border-t pt-3">
          <div>
            <p className="text-foreground/45 font-mono text-[10px] uppercase">{copy.activityLabels[0]}</p>
            <p className="text-foreground font-mono text-sm font-medium">186</p>
          </div>
          <div>
            <p className="text-foreground/45 font-mono text-[10px] uppercase">{copy.activityLabels[1]}</p>
            <p className="text-foreground font-mono text-sm font-medium">42</p>
          </div>
          <div>
            <p className="text-foreground/45 font-mono text-[10px] uppercase">{copy.activityLabels[2]}</p>
            <p className="text-foreground font-mono text-sm font-medium">2.1%</p>
          </div>
        </div>
      </div>
    </MockFrame>
  );
}
