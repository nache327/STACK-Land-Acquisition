import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { QueryProvider } from "@/components/QueryProvider";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Zoning Finder",
  description:
    "Find vacant parcels zoned for self-storage, mini-warehouse, light industrial, and luxury garage condominiums.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${inter.className} min-h-screen bg-background antialiased`}>
        <QueryProvider>{children}</QueryProvider>
      </body>
    </html>
  );
}
