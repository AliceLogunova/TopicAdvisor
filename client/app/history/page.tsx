// client/app/history/page.tsx — История запросов (timeline)
"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { topicsApi } from "@/lib/api";
import { PageBackground } from "@/components/PageBackground";

interface HistoryItem {
  id: number;
  query_text: string;
  level?: string;
  term?: number;
  created_at?: string;
  topics?: { id: number; title: string; rationale?: string; approach?: string; datasets?: string; sources?: string; rank?: number; }[];
}

const LEVEL_LABELS: Record<string, Record<string, string>> = {
  ru: { bachelor: "Бакалавриат", master: "Магистратура", phd: "Аспирантура", postdoc: "Исследователь" },
  en: { bachelor: "Bachelor", master: "Master", phd: "PhD", postdoc: "Researcher" },
};

const T = {
  ru: {
    title: "История запросов", home: "Главная",
    loading: "Загружаем...", empty: "История пуста. Сделайте первый запрос.",
    error: "Не удалось загрузить историю.",
    topics_loading: "Загружаем темы...", no_topics: "Темы не сохранены.",
    section_why: "ПОЧЕМУ СЕЙЧАС", section_approach: "ПОДХОД", section_datasets: "ДАТАСЕТЫ", section_sources: "ИСТОЧНИКИ",
    months: "мес.",
  },
  en: {
    title: "Request history", home: "Home",
    loading: "Loading...", empty: "History is empty. Make your first request.",
    error: "Failed to load history.",
    topics_loading: "Loading topics...", no_topics: "No topics saved.",
    section_why: "WHY NOW", section_approach: "APPROACH", section_datasets: "DATASETS", section_sources: "SOURCES",
    months: "mon.",
  },
};

function formatDate(dateStr?: string, lang = "ru") {
  if (!dateStr) return { date: "—", year: "", time: "" };

  const hasTimezone =
    dateStr.endsWith("Z") ||
    /[+-]\d{2}:\d{2}$/.test(dateStr);

  const normalized = hasTimezone
    ? dateStr
    : dateStr.replace(" ", "T") + "Z";

  const d = new Date(normalized);
  const locale = lang === "ru" ? "ru-RU" : "en-US";

  return {
    date: d.toLocaleDateString(locale, { day: "numeric", month: "short" }),
    year: d.toLocaleDateString(locale, { year: "numeric" }),
    time: d.toLocaleTimeString(locale, {
      hour: "2-digit",
      minute: "2-digit",
    }),
  };
}

function TopicCard({ topic, t }: { topic: NonNullable<HistoryItem["topics"]>[number]; t: typeof T["ru"] }) {
  let sources: string[] = [];
  let datasets: string[] = [];
  try { sources = topic.sources ? JSON.parse(topic.sources) : []; } catch { sources = []; }
  try { datasets = topic.datasets ? JSON.parse(topic.datasets) : []; } catch { datasets = []; }

  return (
    <div className="rounded-xl border-2 border-blue-400/15 bg-white/3 px-4 py-4 space-y-3">
      <div className="flex items-start gap-2">
        <span className="text-xs font-mono text-blue-500/50 shrink-0 mt-0.5 w-5">
          {String(topic.rank ?? 1).padStart(2, "0")}        
        </span>
        <span className="text-sm text-blue-100/90 leading-relaxed flex-1 tracking-wide font-medium">{topic.title}</span>
      </div>
      {topic.rationale && (
        <div className="pl-7">
          <div className="text-xs text-blue-400/50 mb-1 tracking-widest uppercase">{t.section_why}</div>
          <p className="text-sm text-blue-200/60 leading-relaxed">{topic.rationale}</p>
        </div>
      )}
      {topic.approach && (
        <div className="pl-7">
          <div className="text-xs text-blue-400/50 mb-1 tracking-widest uppercase">{t.section_approach}</div>
          <p className="text-sm text-blue-200/60 leading-relaxed">{topic.approach}</p>
        </div>
      )}
      {datasets.length > 0 && (
        <div className="pl-7">
          <div className="text-xs text-blue-400/50 mb-1 tracking-widest uppercase">{t.section_datasets}</div>
          <div className="flex flex-wrap gap-1.5">
            {datasets.map((ds, j) => (
              <span key={j} className="text-xs text-blue-200/60 border border-blue-400/20 px-2 py-0.5 rounded-full">{ds}</span>
            ))}
          </div>
        </div>
      )}
      {sources.length > 0 && (
        <div className="pl-7">
          <div className="text-xs text-blue-400/50 mb-1 tracking-widest uppercase">{t.section_sources}</div>
          {sources.map((src, j) => (
            <a key={j} href={src} target="_blank" rel="noopener noreferrer"
              className="block text-xs text-blue-300/60 hover:text-blue-300 transition-colors truncate">{src}</a>
          ))}
        </div>
      )}
    </div>
  );
}

function TimelineItem({ item, isLast, lang, t }: { item: HistoryItem; isLast: boolean; lang: string; t: typeof T["ru"] }) {
  const [expanded, setExpanded] = useState(false);
  const [topics,   setTopics]   = useState<HistoryItem["topics"]>([]);
  const [loading,  setLoading]  = useState(false);
  const { date, year, time } = formatDate(item.created_at, lang);
  const levelLabels = LEVEL_LABELS[lang] || LEVEL_LABELS.ru;

  const handleExpand = async () => {
    if (!expanded && topics!.length === 0) {
      setLoading(true);
      try {
        const data = await topicsApi.getById(item.id);
        setTopics(data.topics || []);
      } catch { setTopics([]); }
      finally { setLoading(false); }
    }
    setExpanded(!expanded);
  };

  return (
    <div className="flex gap-5">
      {/* Левая колонка — дата */}
      <div className="flex flex-col items-end shrink-0 pt-1" style={{ width: "72px" }}>
        <div className="text-base text-blue-200/80 font-medium tracking-wide leading-tight">{date}</div>
        <div className="text-xs text-blue-300/45 tracking-wide">{year}</div>
        <div className="text-sm text-blue-300/80 font-medium tracking-wide mt-0.5">{time}</div>
      </div>

      {/* Точка и линия */}
      <div className="flex flex-col items-center shrink-0">
        <div className="w-3 h-3 rounded-full border-2 border-blue-400/60 bg-black/20 shrink-0 mt-2 z-10" />
        {!isLast && <div className="w-px flex-1 bg-blue-400/20 mt-1" />}
      </div>

      {/* Контент */}
      <div className="flex-1 pb-8">
        <button onClick={handleExpand}
          className="w-full text-left rounded-2xl border-2 border-blue-400/25 bg-white/3 px-5 py-4 hover:border-blue-400/45 transition-all">
          <div className="flex items-start justify-between gap-3">
            <p className="text-base text-blue-100 leading-relaxed tracking-wide flex-1">{item.query_text}</p>
            <span className="shrink-0 text-blue-400/40 text-xs mt-1">{expanded ? "▲" : "▼"}</span>
          </div>
          <div className="flex items-center gap-3 mt-2 flex-wrap">
            {item.level && (
              <span className="text-xs text-blue-400/60 tracking-wide border-2 border-blue-400/20 px-2 py-0.5 rounded-full">
                {levelLabels[item.level] || item.level}
              </span>
            )}
            {item.term && <span className="text-xs text-blue-400/50 tracking-wide">{item.term} {t.months}</span>}
          </div>
        </button>

        {expanded && (
          <div className="mt-3 space-y-2">
            {loading && <div className="text-sm text-blue-400/40 tracking-wide px-2">{t.topics_loading}</div>}
            {!loading && topics!.length === 0 && <div className="text-sm text-blue-400/30 tracking-wide px-2">{t.no_topics}</div>}
            {!loading && topics!.map((topic, i) => <TopicCard key={i} topic={topic} t={t} />)}
          </div>
        )}
      </div>
    </div>
  );
}

export default function HistoryPage() {
  const router = useRouter();
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState<string | null>(null);
  const [lang,    setLang]    = useState<"ru" | "en">("ru");

  useEffect(() => {
    const saved = localStorage.getItem("lang") as "ru" | "en" | null;
    if (saved === "ru" || saved === "en") setLang(saved);
    topicsApi.getHistory(50)
      .then((data) => setHistory(data as HistoryItem[]))
      .catch(() => setError(T[saved || "ru"].error))
      .finally(() => setLoading(false));
  }, []);

  const t = T[lang];

  return (
    <PageBackground>
      <div className="min-h-screen text-[var(--text)]">
        <nav className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-6 py-4 border-b border-blue-400/20 bg-black/30 backdrop-blur-md">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-300 to-blue-500 flex items-center justify-center text-xs font-bold text-white">TA</div>
            <span className="text-base font-medium tracking-widest text-blue-100">TopicAdvisor</span>
          </div>
          <button onClick={() => router.push("/")}
            className="text-sm text-blue-300/60 hover:text-blue-200 transition-colors tracking-wide border-2 border-blue-400/20 hover:border-blue-400/40 px-3 py-1 rounded-lg">
            {t.home}
          </button>
        </nav>

        <main className="max-w-3xl mx-auto px-4 pt-24 pb-20">
          <h1 className="text-2xl font-light text-blue-50 mb-10 tracking-wide">{t.title}</h1>

          {loading && <div className="text-center py-16 text-blue-300/40 text-base tracking-wide">{t.loading}</div>}
          {error && <div className="p-4 rounded-xl bg-red-500/10 border-2 border-red-400/30 text-base text-red-300">{error}</div>}
          {!loading && !error && history.length === 0 && (
            <div className="text-center py-16 text-blue-300/40 text-base tracking-wide">{t.empty}</div>
          )}
          {!loading && history.length > 0 && (
            <div>
              {history.map((item, i) => (
                <TimelineItem key={item.id} item={item} isLast={i === history.length - 1} lang={lang} t={t} />
              ))}
            </div>
          )}
        </main>
      </div>
    </PageBackground>
  );
}
