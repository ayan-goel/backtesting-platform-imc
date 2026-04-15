import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const mono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Prosperity Platform",
  description: "IMC Prosperity 4 backtesting + replay",
};

const NAV_LINKS = [
  { href: "/", label: "runs" },
  { href: "/batches", label: "batches" },
  { href: "/studies", label: "studies" },
  { href: "/compare", label: "compare" },
  { href: "/strategies", label: "strategies" },
  { href: "/datasets", label: "datasets" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${mono.variable}`}>
      <body className="min-h-screen antialiased">
        <header className="sticky top-0 z-40 border-b border-border bg-bg/80 px-6 py-3 backdrop-blur-md">
          <div className="mx-auto flex max-w-7xl items-center gap-8">
            <Link
              href="/"
              className="font-mono text-sm font-semibold tracking-tight transition-colors duration-fast hover:text-accent"
            >
              prosperity.platform
            </Link>
            <nav className="flex gap-5 text-sm text-muted-fg">
              {NAV_LINKS.map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  className="transition-colors duration-fast hover:text-fg focus-visible:text-fg focus-visible:outline-none"
                >
                  {link.label}
                </Link>
              ))}
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
