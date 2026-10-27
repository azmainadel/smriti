import type { Metadata, Viewport } from "next";
import { Hanken_Grotesk, Newsreader } from "next/font/google";
import localFont from "next/font/local";
import type { ReactNode } from "react";
import { Providers } from "@/components/Providers";
import { themeScript } from "@/lib/theme";
import "./globals.css";

const sans = Hanken_Grotesk({ subsets: ["latin"], variable: "--font-hanken", display: "swap" });
// Fraunces is the voice of the app (search, titles, quotes). It is self-hosted as a subset
// with the SOFT axis pinned at 100: the full variable font is 3x the size for axes we never move.
const display = localFont({
  src: [
    { path: "../fonts/fraunces-soft-normal.woff2", style: "normal", weight: "400 600" },
    { path: "../fonts/fraunces-soft-italic.woff2", style: "italic", weight: "400 600" },
  ],
  variable: "--font-fraunces",
  display: "swap",
});
// Only the reader uses Newsreader, so it loads on demand instead of on every page.
const serif = Newsreader({ subsets: ["latin"], variable: "--font-newsreader", display: "swap", preload: false });

const description = "A quiet place for everything you save.";

export const metadata: Metadata = {
  // Share cards need absolute image URLs.
  metadataBase: new URL(process.env.NEXT_PUBLIC_WEB_URL ?? "http://localhost:3000"),
  title: { default: "Smriti", template: "%s · Smriti" },
  description,
  manifest: "/manifest.webmanifest",
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "48x48" },
      { url: "/icon.svg", type: "image/svg+xml" },
    ],
    apple: "/apple-icon.png",
  },
  openGraph: { type: "website", siteName: "Smriti", title: "Smriti", description },
  twitter: { card: "summary_large_image", title: "Smriti", description },
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
