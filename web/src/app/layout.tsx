import type { Metadata, Viewport } from "next";
import { Fraunces, Hanken_Grotesk, Newsreader } from "next/font/google";
import type { ReactNode } from "react";
import { Providers } from "@/components/Providers";
import { themeScript } from "@/lib/theme";
import "./globals.css";

const sans = Hanken_Grotesk({ subsets: ["latin"], variable: "--font-hanken", display: "swap" });
// Fraunces for the voice of the app (search, titles, quotes); Newsreader for long reading.
const display = Fraunces({ subsets: ["latin"], style: ["normal", "italic"], axes: ["SOFT", "opsz"], variable: "--font-fraunces", display: "swap" });
// Only the reader uses Newsreader, so it loads on demand instead of on every page.
const serif = Newsreader({ subsets: ["latin"], variable: "--font-newsreader", display: "swap", preload: false });

export const metadata: Metadata = {
  title: { default: "Smriti", template: "%s · Smriti" },
  description: "Save anything. Find it by meaning.",
  manifest: "/manifest.webmanifest",
  icons: { icon: "/icon.svg", apple: "/icon-192.png" },
  appleWebApp: { capable: true, title: "Smriti", statusBarStyle: "default" },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#efebe2" },
    { media: "(prefers-color-scheme: dark)", color: "#13131b" },
  ],
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${display.variable} ${serif.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="min-h-dvh">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
