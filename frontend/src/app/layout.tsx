import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Aqua Voice — O'zbekcha Ovozli Muharrir",
  description:
    "O'zbek tilida bosib turib gapirish, jonli AI tahrirlash va rus/ingliz tillariga tezkor tarjima.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="uz">
      <body className="min-h-screen antialiased selection:bg-teal-500/20 selection:text-slate-950">
        {children}
      </body>
    </html>
  );
}
