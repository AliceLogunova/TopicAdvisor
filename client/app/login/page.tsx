// client/app/login/page.tsx
"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { authApi } from "@/lib/api";
import { PageBackground } from "@/components/PageBackground";

const TEXTS = {
  ru: {
    subtitle: "Войдите в аккаунт",
    email: "Email", password: "Пароль",
    btn: "Войти", loading: "Входим...",
    no_account: "Нет аккаунта?", register: "Зарегистрироваться",
    errors: {
      wrong_credentials: "Неверный email или пароль",
      not_found: "Пользователь с таким email не найден",
      default: "Ошибка входа. Попробуйте снова.",
    }
  },
  en: {
    subtitle: "Sign in to your account",
    email: "Email", password: "Password",
    btn: "Sign in", loading: "Signing in...",
    no_account: "No account?", register: "Register",
    errors: {
      wrong_credentials: "Invalid email or password",
      not_found: "No account with this email",
      default: "Login error. Please try again.",
    }
  },
};

export default function LoginPage() {
  const router = useRouter();
  const [email,    setEmail]    = useState("");
  const [password, setPassword] = useState("");
  const [error,    setError]    = useState<string | null>(null);
  const [loading,  setLoading]  = useState(false);
  const [lang,     setLang]     = useState<"ru" | "en">("ru");
  const [showPass, setShowPass] = useState(false);

  useEffect(() => {
    const saved = localStorage.getItem("lang") as "ru" | "en" | null;
    if (saved === "ru" || saved === "en") setLang(saved);
  }, []);

  const toggleLang = () => {
    const next = lang === "ru" ? "en" : "ru";
    setLang(next);
    localStorage.setItem("lang", next);
  };

  const t = TEXTS[lang];
  const isReady = !!email && !!password && !loading;

  const parseError = (err: any): string => {
    const detail = err.response?.data?.detail;
    const status = err.response?.status;
    if (Array.isArray(detail)) return detail.map((e: any) => e.msg).join(", ");
    if (typeof detail === "string") {
      if (detail.includes("не найден") || detail.includes("not found")) return t.errors.not_found;
      if (status === 401) return t.errors.wrong_credentials;
      return detail;
    }
    if (status === 401) return t.errors.wrong_credentials;
    return t.errors.default;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isReady) return;
    setLoading(true); setError(null);
    try {
      const token = await authApi.login(email, password);
      localStorage.setItem("token", token.access_token);
      router.push("/");
    } catch (err: any) {
      setError(parseError(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <PageBackground>
      <div className="min-h-screen flex items-center justify-center px-4">
        <div className="w-full max-w-md">

          <div className="text-center mb-10">
            <div className="w-14 h-14 mx-auto mb-5 rounded-full bg-gradient-to-br from-blue-400 to-blue-600 flex items-center justify-center text-base font-bold text-white">TA</div>
            <h1 className="text-2xl font-light text-blue-50 tracking-widest mb-1">TopicAdvisor</h1>
            <p className="text-base text-blue-200/50 tracking-wide">{t.subtitle}</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm text-blue-200/60 mb-2 tracking-widest uppercase">{t.email}</label>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com" disabled={loading}
                className="w-full bg-white/5 border-2 border-blue-400/30 rounded-xl px-5 py-4 text-base text-blue-50 placeholder-blue-400/30 focus:outline-none focus:border-blue-400/70 transition-all disabled:opacity-50 tracking-wide" />
            </div>
            <div>
              <label className="block text-sm text-blue-200/60 mb-2 tracking-widest uppercase">{t.password}</label>
              <div className="relative">
                <input type={showPass ? "text" : "password"} value={password} onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••" disabled={loading}
                  className="w-full bg-white/5 border-2 border-blue-400/30 rounded-xl px-5 py-4 pr-12 text-base text-blue-50 placeholder-blue-400/30 focus:outline-none focus:border-blue-400/70 transition-all disabled:opacity-50 tracking-wide" />
                <button type="button" onClick={() => setShowPass(!showPass)}
                  className="absolute right-4 top-1/2 -translate-y-1/2 text-blue-400/40 hover:text-blue-300 transition-colors">
                  {showPass ? (
                    <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88" />
                    </svg>
                  ) : (
                    <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
                      <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                    </svg>
                  )}
                </button>
              </div>
            </div>

            {error && (
              <div className="p-4 rounded-xl bg-red-500/10 border-2 border-red-400/30 text-sm text-red-300 tracking-wide">{error}</div>
            )}

            <button type="submit" disabled={!isReady}
              className="w-full py-4 rounded-xl text-base font-medium tracking-widest transition-all border-2 mt-2"
              style={{
                background:  isReady ? "linear-gradient(135deg, #2563eb, #1d4ed8)" : "rgba(96,165,250,0.15)",
                color:       isReady ? "white" : "rgba(147,197,253,0.7)",
                borderColor: isReady ? "rgba(59,130,246,0.6)" : "rgba(96,165,250,0.3)",
                cursor:      isReady ? "pointer" : "not-allowed",
              }}>
              {loading ? t.loading : t.btn}
            </button>
          </form>

          <p className="text-center text-sm text-blue-400/40 mt-8 tracking-wide">
            {t.no_account}{" "}
            <a href="/register" className="text-blue-300/80 hover:text-blue-200 transition-colors">{t.register}</a>
          </p>

          <div className="text-center mt-4">
            <button onClick={toggleLang}
              className="text-sm text-blue-400/40 hover:text-blue-300/70 transition-colors border-2 border-blue-500/25 hover:border-blue-500/45 px-3 py-1 rounded-full tracking-widest">
              {lang === "ru" ? "RU" : "EN"}
            </button>
          </div>
        </div>
      </div>
    </PageBackground>
  );
}
