import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Aqua Voice Uzbek — AI Ovozli Matn Muharriri",
  description:
    "O'zbek tilida jonli ovozli diktovka, Intent Detection va Text Diff Engine asosidagi aqlli matn muharriri.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="uz" className="dark">
      <body className="min-h-screen antialiased selection:bg-sky-500/30 selection:text-sky-100">
        {children}
      </body>
    </html>
  );
}
