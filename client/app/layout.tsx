import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TopicAdvisor",
  description: "Интеллектуальная система поиска тем ВКР",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru">
      <body>{children}</body>
    </html>
  );
}