import type { Metadata } from "next";
import { JetBrains_Mono, Manrope } from "next/font/google";
import "./globals.css";
import { SessionProvider } from "@/lib/session-context";
import { StatusRail } from "@/components/status-rail";

const manrope = Manrope({
  variable: "--font-manrope",
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
});

const jb = JetBrains_Mono({
  variable: "--font-jb",
  subsets: ["latin"],
  weight: ["300", "400", "500", "700"],
});

export const metadata: Metadata = {
  title: "BUY·THE·DIP — Trading Agent",
  description: "Live agent terminal for option trade proposals.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${manrope.variable} ${jb.variable} h-full antialiased dark`}
    >
      <body className="min-h-full flex flex-col bg-[var(--ink)] text-[color:var(--fg)]">
        <SessionProvider>
          <StatusRail />
          {children}
        </SessionProvider>
      </body>
    </html>
  );
}
