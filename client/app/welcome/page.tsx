// client/app/welcome/page.tsx
"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";

const TEXTS = {
  ru: {
    tagline: "Интеллектуальный поиск тем для научных работ",
    sub: "Система анализирует тысячи актуальных публикаций arXiv и предлагает перспективные исследовательские направления — конкретно, с обоснованием и ссылками на источники.",
    login: "Войти", register: "Начать",
    feature1: "Актуальные публикации", feature1_sub: "Анализ свежих статей arXiv",
    feature2: "Точные рекомендации",   feature2_sub: "5-ступенчатый RAG-пайплайн",
    feature3: "Локальный инференс",    feature3_sub: "Без внешних API",
    footer: "TopicAdvisor · arXiv RAG Pipeline",
  },
  en: {
    tagline: "Intelligent research topic discovery",
    sub: "The system analyzes thousands of recent arXiv publications and suggests promising research directions — specific, justified, with source references.",
    login: "Sign in", register: "Get started",
    feature1: "Recent publications", feature1_sub: "Analyzes fresh arXiv papers",
    feature2: "Precise recommendations", feature2_sub: "5-stage RAG pipeline",
    feature3: "Local inference",         feature3_sub: "No external APIs",
    footer: "TopicAdvisor · arXiv RAG Pipeline",
  },
};

function Particles() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    const particles = Array.from({ length: 80 }, () => ({
      x: Math.random() * canvas.width, y: Math.random() * canvas.height,
      vx: (Math.random() - 0.5) * 0.3, vy: (Math.random() - 0.5) * 0.3,
      r: Math.random() * 1.5 + 0.5, alpha: Math.random() * 0.4 + 0.1,
    }));
    let animId: number;
    function draw() {
      if (!canvas || !ctx) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const dx = particles[i].x - particles[j].x;
          const dy = particles[i].y - particles[j].y;
          const dist = Math.sqrt(dx*dx + dy*dy);
          if (dist < 120) {
            ctx.beginPath();
            ctx.strokeStyle = `rgba(96,165,250,${0.08*(1-dist/120)})`;
            ctx.lineWidth = 0.5;
            ctx.moveTo(particles[i].x, particles[i].y);
            ctx.lineTo(particles[j].x, particles[j].y);
            ctx.stroke();
          }
        }
      }
      particles.forEach(p => {
        p.x += p.vx; p.y += p.vy;
        if (p.x < 0 || p.x > canvas.width)  p.vx *= -1;
        if (p.y < 0 || p.y > canvas.height) p.vy *= -1;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI*2);
        ctx.fillStyle = `rgba(147,197,253,${p.alpha})`;
        ctx.fill();
      });
      animId = requestAnimationFrame(draw);
    }
    draw();
    const onResize = () => { canvas.width = window.innerWidth; canvas.height = window.innerHeight; };
    window.addEventListener("resize", onResize);
    return () => { cancelAnimationFrame(animId); window.removeEventListener("resize", onResize); };
  }, []);
  return <canvas ref={canvasRef} className="fixed inset-0 pointer-events-none" style={{ zIndex: 0 }} />;
}

export default function WelcomePage() {
  const router = useRouter();
  const [lang, setLang] = useState<"ru" | "en">("ru");
  const t = TEXTS[lang];

  // Загружаем язык из localStorage при первом рендере
  useEffect(() => {
    const saved = localStorage.getItem("lang") as "ru" | "en" | null;
    if (saved === "ru" || saved === "en") setLang(saved);
  }, []);

  const toggleLang = () => {
    const next = lang === "ru" ? "en" : "ru";
    setLang(next);
    localStorage.setItem("lang", next); // сохраняем в localStorage
  };

  const goLogin    = () => router.push("/login");
  const goRegister = () => router.push("/register");

  return (
    <div className="relative min-h-screen flex flex-col overflow-hidden"
      style={{ background: "radial-gradient(ellipse at 60% 20%, #0f2a4a 0%, #080c14 50%, #020408 100%)" }}>
      <Particles />
      <div className="fixed top-[-10%] right-[-5%] w-[500px] h-[500px] rounded-full pointer-events-none"
        style={{ background: "radial-gradient(circle, rgba(59,130,246,0.08) 0%, transparent 70%)", zIndex: 1 }} />
      <div className="fixed bottom-[-10%] left-[-5%] w-[400px] h-[400px] rounded-full pointer-events-none"
        style={{ background: "radial-gradient(circle, rgba(37,99,235,0.06) 0%, transparent 70%)", zIndex: 1 }} />

      {/* Навбар */}
      <nav className="relative flex items-center justify-between px-8 py-5" style={{ zIndex: 10 }}>
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-300 to-blue-600 flex items-center justify-center text-xs font-bold text-white">TA</div>
          <span className="text-base font-medium tracking-[0.2em] text-blue-200/60 uppercase">TopicAdvisor</span>
        </div>
        <button onClick={toggleLang}
          className="text-sm tracking-widest text-blue-300/60 hover:text-blue-200 transition-colors border-2 border-blue-500/30 hover:border-blue-500/60 px-3 py-1 rounded-full font-medium">
          {lang === "ru" ? "RU" : "EN"}
        </button>
      </nav>

      {/* Контент */}
      <main className="relative flex-1 flex flex-col items-center justify-center px-6 text-center" style={{ zIndex: 10 }}>
        <div className="mb-8 relative">
          <div className="w-20 h-20 mx-auto rounded-2xl flex items-center justify-center"
            style={{ background: "rgba(59,130,246,0.1)", border: "1px solid rgba(96,165,250,0.2)" }}>
            <svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg" className="w-12 h-12">
              <path d="M32 8L6 22L32 36L58 22L32 8Z" fill="#60a5fa" opacity="0.9"/>
              <path d="M14 30V44C14 44 22 54 32 54C42 54 50 44 50 44V30L32 42L14 30Z" fill="#3b82f6" opacity="0.7"/>
              <rect x="54" y="22" width="3" height="16" rx="1.5" fill="#93c5fd"/>
              <circle cx="55.5" cy="40" r="3" fill="#93c5fd"/>
            </svg>
          </div>
          <div className="absolute inset-0 rounded-2xl animate-ping"
            style={{ background: "rgba(59,130,246,0.05)", animationDuration: "3s" }} />
        </div>

        <h1 className="font-light text-white mb-4 tracking-tight leading-none"
          style={{ fontSize: "clamp(3rem, 8vw, 6rem)", letterSpacing: "-0.02em" }}>
          Topic<span style={{ color: "#60a5fa" }}>Advisor</span>
        </h1>

        <p className="text-blue-200/50 mb-4 tracking-wide max-w-lg" style={{ fontSize: "1.1rem" }}>{t.tagline}</p>
        <p className="text-blue-300/35 leading-relaxed max-w-md mb-12 tracking-wide" style={{ fontSize: "0.95rem" }}>{t.sub}</p>

        <div className="flex items-center gap-4 mb-16">
          <button onClick={goRegister}
            className="px-8 py-3.5 rounded-xl text-base font-medium tracking-widest text-white transition-all hover:scale-105 active:scale-95 border-2 border-blue-400/0"
            style={{ background: "linear-gradient(135deg, #3b82f6, #1d4ed8)", boxShadow: "0 0 30px rgba(59,130,246,0.3)" }}>
            {t.register}
          </button>
          <button onClick={goLogin}
            className="px-8 py-3.5 rounded-xl text-base font-medium tracking-widest text-blue-200/80 hover:text-blue-100 transition-all border-2 border-blue-400/40 hover:border-blue-400/70 hover:scale-105 active:scale-95">
            {t.login}
          </button>
        </div>
      </main>

      <footer className="relative text-center py-6 tracking-widest text-blue-400/20" style={{ zIndex: 10, fontSize: "0.8rem" }}>
        {t.footer}
      </footer>
    </div>
  );
}
