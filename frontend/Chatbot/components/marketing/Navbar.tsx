"use client";

import { Menu } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { AnimatedThemeToggler } from "@/components/ui/animated-theme-toggler";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { RailSection } from "./Frame";
import { Logo } from "./Logo";
import { SlideButton } from "./SlideButton";

const menuItems = [
  { name: "Features", href: "#features" },
  { name: "Use cases", href: "#use-cases" },
  { name: "Integrations", href: "#integrations" },
  { name: "Pricing", href: "#pricing" },
  { name: "FAQ", href: "#faq" },
];

const toggleClass =
  "flex size-9 items-center justify-center rounded-[4px] text-muted-foreground transition-colors hover:text-foreground [&_svg]:size-[18px]";

export function Navbar() {
  const [menuOpen, setMenuOpen] = useState(false);
  const closeMenu = () => setMenuOpen(false);

  return (
    <RailSection as="header">
      <nav aria-label="Main" className="flex h-[72px] items-center justify-between gap-6 px-5 md:px-6">
        <Logo />

        <ul className="hidden items-center gap-8 lg:flex">
          {menuItems.map((item) => (
            <li key={item.href}>
              <a href={item.href} className="text-sm text-foreground/85 transition-colors hover:text-foreground">
                {item.name}
              </a>
            </li>
          ))}
        </ul>

        <div className="hidden items-center gap-2 lg:flex">
          <AnimatedThemeToggler className={toggleClass} />
          <Link
            href="/login"
            prefetch={false}
            className="px-3 text-sm text-foreground/85 transition-colors hover:text-foreground"
          >
            Sign in
          </Link>
          <SlideButton href="/register">Get started</SlideButton>
        </div>

        {/* The menu is portaled out of the header, so opening it can't resize the bar. */}
        <div className="flex items-center gap-1 lg:hidden">
          <AnimatedThemeToggler className={toggleClass} />
          <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
            <SheetTrigger asChild>
              <button type="button" aria-label="Open menu" className={toggleClass}>
                <Menu />
              </button>
            </SheetTrigger>
            <SheetContent side="right" className="landing w-72 border-l border-dashed border-line sm:max-w-xs">
              <SheetHeader>
                <SheetTitle className="font-display">Menu</SheetTitle>
                <SheetDescription className="sr-only">Site navigation</SheetDescription>
              </SheetHeader>
              <div className="flex flex-col gap-8 px-4 pb-6">
                <ul className="space-y-5 text-base">
                  {menuItems.map((item) => (
                    <li key={item.href}>
                      <a
                        href={item.href}
                        onClick={closeMenu}
                        className="block text-muted-foreground transition-colors hover:text-foreground"
                      >
                        {item.name}
                      </a>
                    </li>
                  ))}
                </ul>
                <div className="flex flex-col gap-3">
                  <SlideButton href="/register" className="justify-center">
                    Get started
                  </SlideButton>
                  <SlideButton href="/login" variant="outline" className="justify-center">
                    Sign in
                  </SlideButton>
                </div>
              </div>
            </SheetContent>
          </Sheet>
        </div>
      </nav>
    </RailSection>
  );
}
