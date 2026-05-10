// client/app/page.tsx
"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { topicsApi, TopicsResponse } from "@/lib/api";
import { PageBackground } from "@/components/PageBackground";

const LEVELS = {
  ru: [
    { value: "bachelor", label: "Бакалавриат" },
    { value: "master",   label: "Магистратура" },
    { value: "phd",      label: "Аспирантура" },
    { value: "postdoc",  label: "Исследователь" },
  ],
  en: [
    { value: "bachelor", label: "Bachelor" },
    { value: "master",   label: "Master" },
    { value: "phd",      label: "PhD" },
    { value: "postdoc",  label: "Researcher" },
  ],
};

const STEPS = {
  ru: [
    { key: "planner",   label: "Расширяем запрос"  },
    { key: "retriever", label: "Ищем статьи"        },
    { key: "reranker",  label: "Отбираем лучшие"   },
    { key: "extractor", label: "Извлекаем факты"   },
    { key: "generator", label: "Генерируем темы"   },
  ],
  en: [
    { key: "planner",   label: "Expanding query"   },
    { key: "retriever", label: "Searching articles" },
    { key: "reranker",  label: "Selecting best"    },
    { key: "extractor", label: "Extracting facts"  },
    { key: "generator", label: "Generating topics" },
  ],
};

const T = {
  ru: {
    nav_history: "История", nav_account: "Аккаунт", nav_logout: "Выйти",
    hero_title: "Найди свою тему научной работы",
    hero_sub: "Интеллектуальная система поиска перспективных исследовательских тем на основе актуальных публикаций arXiv",
    placeholder: "Опишите ваши интересы, область знаний и цели исследования...",
    label_level: "Уровень", label_duration: "Срок (мес.)", label_topics: "Тем",
    btn_find: "Найти темы", btn_searching: "Анализируем...", btn_new: "Новый запрос",
    meta_articles: "статей найдено", meta_subq: "подзапросов", meta_time: "с",
    no_topics: "Темы не найдены. Попробуйте переформулировать запрос.",
    section_why: "ПОЧЕМУ СЕЙЧАС", section_approach: "ПОДХОД",
    section_datasets: "ДАТАСЕТЫ", section_sources: "ИСТОЧНИКИ",
    error_default: "Что-то пошло не так. Попробуйте снова.",
  },
  en: {
    nav_history: "History", nav_account: "Account", nav_logout: "Log out",
    hero_title: "Find your research topic",
    hero_sub: "Intelligent system for finding promising research directions based on recent arXiv publications",
    placeholder: "Describe your interests, field of study and research goals...",
    label_level: "Level", label_duration: "Duration (mon.)", label_topics: "Topics",
    btn_find: "Find topics", btn_searching: "Analyzing...", btn_new: "New search",
    meta_articles: "articles found", meta_subq: "subqueries", meta_time: "s",
    no_topics: "No topics found. Try rephrasing your query.",
    section_why: "WHY NOW", section_approach: "APPROACH",
    section_datasets: "DATASETS", section_sources: "SOURCES",
    error_default: "Something went wrong. Please try again.",
  },
};

interface ChatEntry {
  id: string;
  query: string;
  result: TopicsResponse;
  timestamp: Date;
}

export default function Home() {
  const router = useRouter();
  const chatEndRef = useRef<HTMLDivElement>(null);

  const [query,         setQuery]         = useState("");
  const [level,         setLevel]         = useState("master");
  const [duration,      setDuration]      = useState(6);
  const [numTopics,     setNumTopics]     = useState(5);
  const [loading,       setLoading]       = useState(false);
  const [currentStep,   setCurrentStep]   = useState(0);
  const [error,         setError]         = useState<string | null>(null);
  const [expandedTopic, setExpandedTopic] = useState<Record<string, number | null>>({});
  const [lang,          setLang]          = useState<"ru" | "en">("ru");
  const [chatHistory,   setChatHistory]   = useState<ChatEntry[]>([]);
  const [accountOpen,   setAccountOpen]   = useState(false);
  const [userEmail,     setUserEmail]     = useState<string>("");

  const t      = T[lang];
  const steps  = STEPS[lang];
  const levels = LEVELS[lang];

  useEffect(() => {
    const saved = localStorage.getItem("lang") as "ru" | "en" | null;
    if (saved === "ru" || saved === "en") setLang(saved);
    // Читаем email из токена
    const token = localStorage.getItem("token");
    if (token) {
      try {
        const payload = JSON.parse(atob(token.split(".")[1]));
        setUserEmail(payload.email || "");
      } catch {}
    }
    // Загружаем историю чата из sessionStorage
    const savedChat = sessionStorage.getItem("chatHistory");
    if (savedChat) {
      try {
        const parsed = JSON.parse(savedChat);
        setChatHistory(parsed.map((e: any) => ({ ...e, timestamp: new Date(e.timestamp) })));
      } catch {}
    }
  }, []);

  const toggleLang = () => {
    const next = lang === "ru" ? "en" : "ru";
    setLang(next);
    localStorage.setItem("lang", next);
  };

  const handleLogout = () => {
    localStorage.removeItem("token");
    router.push("/welcome");
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim() || loading) return;

    const effectiveNumTopics = Math.max(numTopics, 2);
    setLoading(true);
    setError(null);
    setCurrentStep(0);

    const interval = setInterval(() => {
      setCurrentStep((s) => Math.min(s + 1, steps.length - 1));
    }, 8000);

    try {
      const data = await topicsApi.generate({
        query, level, duration,
        num_topics: effectiveNumTopics,
        locale: lang,
      });
      const entry: ChatEntry = {
        id: Date.now().toString(),
        query,
        result: data,
        timestamp: new Date(),
      };
      const newHistory = [...chatHistory, entry];
      setChatHistory(newHistory);
      sessionStorage.setItem("chatHistory", JSON.stringify(newHistory));
      setQuery("");
      setCurrentStep(steps.length);
      setTimeout(() => chatEndRef.current?.scrollIntoView({ behavior: "smooth" }), 100);
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      const message = Array.isArray(detail)
        ? detail.map((e: any) => e.msg).join(", ")
        : typeof detail === "string" ? detail : t.error_default;
      setError(message);
    } finally {
      clearInterval(interval);
      setLoading(false);
    }
  };

  const toggleTopic = (entryId: string, topicIdx: number) => {
    setExpandedTopic(prev => ({
      ...prev,
      [entryId]: prev[entryId] === topicIdx ? null : topicIdx,
    }));
  };

  return (
    <PageBackground>
      <div className="min-h-screen text-[var(--text)]">

        {/* Навбар */}
        <nav className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-6 py-4 border-b border-blue-400/20 bg-black/30 backdrop-blur-md">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-300 to-blue-500 flex items-center justify-center text-xs font-bold text-white">TA</div>
            <span className="text-base font-medium tracking-widest text-blue-100">TopicAdvisor</span>
          </div>
          <div className="flex items-center gap-4 text-sm">
            <button onClick={() => router.push("/history")}
              className="text-blue-200/60 hover:text-blue-200 transition-colors tracking-wide border-2 border-blue-400/20 hover:border-blue-400/40 px-3 py-1 rounded-lg">
              {t.nav_history}
            </button>
            <button onClick={toggleLang}
              className="text-blue-200/50 hover:text-blue-200 transition-colors border-2 border-blue-400/20 hover:border-blue-400/40 px-2.5 py-1 rounded-lg tracking-widest font-medium">
              {lang === "ru" ? "RU" : "EN"}
            </button>

            {/* Аккаунт-кнопка */}
            <div className="relative">
              <button onClick={() => setAccountOpen(!accountOpen)}
                className="flex items-center gap-2 text-blue-200/60 hover:text-blue-200 transition-colors border-2 border-blue-400/20 hover:border-blue-400/40 px-3 py-1 rounded-lg">
                <div className="w-5 h-5 rounded-full bg-blue-500/40 flex items-center justify-center text-xs text-blue-200">
                  {userEmail ? userEmail[0].toUpperCase() : "?"}
                </div>
                <span className="tracking-wide">{t.nav_account}</span>
              </button>

              {accountOpen && (
                <div className="absolute right-0 top-full mt-2 w-56 rounded-xl border-2 border-blue-400/25 bg-[#0d1b2e]/95 backdrop-blur-md shadow-xl z-50 overflow-hidden">
                  <div className="px-4 py-3 border-b border-blue-400/15">
                    <div className="text-xs text-blue-400/50 tracking-widest uppercase mb-1">Email</div>
                    <div className="text-sm text-blue-100 tracking-wide truncate">{userEmail || "—"}</div>
                  </div>
                  <button onClick={handleLogout}
                    className="w-full text-left px-4 py-3 text-sm text-red-400/80 hover:text-red-300 hover:bg-red-500/5 transition-colors tracking-wide">
                    {t.nav_logout}
                  </button>
                </div>
              )}
            </div>
          </div>
        </nav>

        <main className="max-w-2xl mx-auto px-4 pt-20 pb-48">

          {/* Hero — только если нет истории */}
          {chatHistory.length === 0 && !loading && (
            <div className="text-center mb-12 pt-10">
              <div className="w-16 h-16 mx-auto mb-6 flex items-center justify-center">
                <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg" className="w-16 h-16">
                  <rect width="64" height="64" rx="16" fill="#1a3a6e"/>
                  <path d="M32 14L10 26L32 38L54 26L32 14Z" fill="#60a5fa" opacity="0.9"/>
                  <path d="M18 32V44C18 44 24 50 32 50C40 50 46 44 46 44V32L32 40L18 32Z" fill="#3b82f6" opacity="0.8"/>
                  <rect x="50" y="26" width="3" height="14" rx="1.5" fill="#93c5fd"/>
                  <circle cx="51.5" cy="42" r="2.5" fill="#93c5fd"/>
                </svg>
              </div>
              <h1 className="text-3xl font-light text-white mb-3 tracking-tight">{t.hero_title}</h1>
              <p className="text-base text-blue-300/50 leading-relaxed max-w-lg mx-auto tracking-wide">{t.hero_sub}</p>
            </div>
          )}

          {/* История чата */}
          {chatHistory.map((entry) => (
            <div key={entry.id} className="mb-10">
              {/* Запрос пользователя */}
              <div className="flex justify-end mb-4">
                <div className="max-w-lg bg-blue-600/20 border-2 border-blue-500/30 rounded-2xl px-5 py-3">
                  <p className="text-base text-blue-50 tracking-wide">{entry.query}</p>
                  <div className="flex gap-3 mt-1.5 text-xs text-blue-400/40 tracking-wide">
                    <span>{entry.result.articles.length} {t.meta_articles}</span>
                    <span>·</span>
                    <span>{entry.result.duration_seconds}{t.meta_time}</span>
                  </div>
                </div>
              </div>

              {/* Ответ системы */}
              <div className="space-y-3">
                {entry.result.topics.map((topic, i) => (
                  <div key={i} className="rounded-2xl border-2 border-blue-400/20 bg-white/3 overflow-hidden hover:border-blue-400/40 transition-all">
                    <button onClick={() => toggleTopic(entry.id, i)}
                      className="w-full text-left px-5 py-4 flex items-start gap-3">
                      <span className="text-sm font-mono text-blue-500/50 shrink-0 mt-0.5 w-6">
                        {String(i + 1).padStart(2, "0")}
                      </span>
                      <span className="text-base text-blue-50 leading-relaxed flex-1 tracking-wide">{topic.title}</span>
                      <span className="shrink-0 text-blue-400/30 text-xs mt-0.5">
                        {expandedTopic[entry.id] === i ? "▲" : "▼"}
                      </span>
                    </button>

                    {expandedTopic[entry.id] === i && (
                      <div className="px-5 pb-5 space-y-4 border-t border-blue-400/10 pt-4">
                        {topic.rationale && (
                          <div>
                            <div className="text-xs text-blue-400/60 mb-1.5 tracking-widest uppercase">{t.section_why}</div>
                            <p className="text-sm text-blue-100/75 leading-relaxed tracking-wide">{topic.rationale}</p>
                          </div>
                        )}
                        {topic.approach && (
                          <div>
                            <div className="text-xs text-blue-400/60 mb-1.5 tracking-widest uppercase">{t.section_approach}</div>
                            <p className="text-sm text-blue-100/75 leading-relaxed tracking-wide">{topic.approach}</p>
                          </div>
                        )}
                        {topic.datasets && topic.datasets.length > 0 && (
                          <div>
                            <div className="text-xs text-blue-400/60 mb-1.5 tracking-widest uppercase">{t.section_datasets}</div>
                            <div className="flex flex-wrap gap-1.5">
                              {topic.datasets.map((ds, j) => (
                                <span key={j} className="text-xs px-2.5 py-1 rounded-lg bg-blue-400/10 text-blue-200/60 border-2 border-blue-400/15">{ds}</span>
                              ))}
                            </div>
                          </div>
                        )}
                        {topic.sources && topic.sources.length > 0 && (
                          <div>
                            <div className="text-xs text-blue-400/60 mb-1.5 tracking-widest uppercase">{t.section_sources}</div>
                            <div className="space-y-1">
                              {topic.sources.map((src, j) => (
                                <a key={j} href={src} target="_blank" rel="noopener noreferrer"
                                  className="block text-sm text-blue-300/70 hover:text-blue-200 transition-colors truncate tracking-wide underline underline-offset-2">{src}</a>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}

          {/* Прогресс */}
          {loading && (
            <div className="mb-6 p-5 rounded-2xl bg-white/3 border-2 border-blue-400/20">
              <div className="space-y-3">
                {steps.map((step, i) => (
                  <div key={step.key} className="flex items-center gap-3">
                    <div className={`w-7 h-7 rounded-lg flex items-center justify-center text-xs font-mono transition-all duration-500 ${
                      i < currentStep ? "bg-blue-400/25 text-blue-300" :
                      i === currentStep ? "bg-blue-400/35 text-blue-200 animate-pulse" : "bg-white/5 text-blue-900/40"
                    }`}>
                      {i < currentStep ? "✓" : String(i+1).padStart(2,"0")}
                    </div>
                    <span className={`text-sm tracking-wide transition-colors duration-300 ${i <= currentStep ? "text-blue-100" : "text-blue-900/40"}`}>
                      {step.label}
                    </span>
                    {i === currentStep && (
                      <div className="ml-auto flex gap-1">
                        {[0,1,2].map(d => (
                          <div key={d} className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-bounce"
                            style={{ animationDelay: `${d*0.15}s` }} />
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {error && (
            <div className="mb-4 p-4 rounded-xl bg-red-500/10 border-2 border-red-400/30 text-sm text-red-300 tracking-wide">{error}</div>
          )}

          <div ref={chatEndRef} />
        </main>

        {/* Форма — фиксированная снизу */}
        <div className="fixed bottom-0 left-0 right-0 z-40 bg-black/40 backdrop-blur-md border-t border-blue-400/15 px-4 py-4">
          <form onSubmit={handleSubmit} className="max-w-2xl mx-auto space-y-3">
            {/* Параметры */}
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="block text-xs text-blue-300/50 mb-1 tracking-widest uppercase">{t.label_level}</label>
                <select value={level} onChange={(e) => setLevel(e.target.value)} disabled={loading}
                  className="w-full bg-white/5 border-2 border-blue-400/25 rounded-xl px-3 py-2 text-sm text-blue-100 focus:outline-none focus:border-blue-400/60 transition-all disabled:opacity-50 appearance-none cursor-pointer">
                  {levels.map(l => <option key={l.value} value={l.value}>{l.label}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs text-blue-300/50 mb-1 tracking-widest uppercase">{t.label_duration}</label>
                <input type="number" value={duration} onChange={(e) => setDuration(Number(e.target.value))}
                  min={1} max={60} disabled={loading}
                  className="w-full bg-white/5 border-2 border-blue-400/25 rounded-xl px-3 py-2 text-sm text-blue-100 focus:outline-none focus:border-blue-400/60 transition-all disabled:opacity-50" />
              </div>
              <div>
                <label className="block text-xs text-blue-300/50 mb-1 tracking-widest uppercase">{t.label_topics}</label>
                <input type="number" value={numTopics} onChange={(e) => setNumTopics(Math.max(2, Number(e.target.value)))}
                  min={2} max={6} disabled={loading}
                  className="w-full bg-white/5 border-2 border-blue-400/25 rounded-xl px-3 py-2 text-sm text-blue-100 focus:outline-none focus:border-blue-400/60 transition-all disabled:opacity-50" />
              </div>
            </div>

            {/* Поле запроса + кнопка */}
            <div className="flex gap-2">
              <textarea value={query} onChange={(e) => setQuery(e.target.value)}
                placeholder={t.placeholder} disabled={loading} rows={2}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSubmit(e as any); } }}
                className="flex-1 bg-white/5 border-2 border-blue-400/25 rounded-xl px-4 py-3 text-base text-blue-50 placeholder-blue-400/30 resize-none focus:outline-none focus:border-blue-400/60 transition-all disabled:opacity-50 tracking-wide" />
              <button type="submit" disabled={!query.trim() || loading}
                className="px-5 rounded-xl text-base font-medium tracking-widest transition-all border-2 self-stretch"
                style={{
                  background:  query.trim() && !loading ? "linear-gradient(135deg, #2563eb, #1d4ed8)" : "rgba(96,165,250,0.12)",
                  color:       query.trim() && !loading ? "white" : "rgba(147,197,253,0.5)",
                  borderColor: query.trim() && !loading ? "rgba(59,130,246,0.5)" : "rgba(96,165,250,0.2)",
                  cursor:      query.trim() && !loading ? "pointer" : "not-allowed",
                }}>
                {loading ? "..." : t.btn_find}
              </button>
            </div>
          </form>
        </div>

        {/* Закрытие дропдауна при клике вне */}
        {accountOpen && (
          <div className="fixed inset-0 z-40" onClick={() => setAccountOpen(false)} />
        )}
      </div>
    </PageBackground>
  );
}
