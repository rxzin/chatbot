"use client";

import { Check } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { RailSection, SectionHeading } from "./Frame";
import { SlideButton } from "./SlideButton";

// Example plans. Chat is free while in development and has no billing.
const plans = [
  {
    name: "Free",
    description: "For trying Chat with your own documents.",
    monthly: 0,
    yearly: 0,
    features: ["200 messages a day", "30 web searches a day", "PDF and TXT uploads", "Answers with citations"],
    popular: false,
  },
  {
    name: "Pro",
    description: "For people who chat with documents every day.",
    monthly: 12,
    yearly: 10,
    features: ["Everything in Free", "Higher daily limits", "Larger uploads", "Longer conversation memory"],
    popular: true,
  },
  {
    name: "Team",
    description: "For teams that need oversight and support.",
    monthly: 49,
    yearly: 39,
    features: ["Everything in Pro", "Admin dashboard", "Audit log and session control", "Bug reports to Jira"],
    popular: false,
  },
];

export function PricingSection() {
  const [yearly, setYearly] = useState(true);

  return (
    <RailSection id="pricing" aria-labelledby="pricing-heading">
      <div className="grid gap-10 px-5 pt-24 pb-16 sm:px-12 sm:pt-28 lg:grid-cols-[1fr_auto]">
        <div>
          <SectionHeading id="pricing-heading" className="max-w-[26rem]">
            Simple pricing for every way you chat.
          </SectionHeading>
          <div
            role="group"
            aria-label="Billing period"
            className="mt-8 inline-flex items-center gap-1 rounded-full border border-line p-1 text-sm"
          >
            <button
              type="button"
              aria-pressed={yearly}
              onClick={() => setYearly(true)}
              className={cn(
                "rounded-full px-4 py-1.5 transition-colors",
                yearly ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground",
              )}
            >
              Annually
            </button>
            <button
              type="button"
              aria-pressed={!yearly}
              onClick={() => setYearly(false)}
              className={cn(
                "rounded-full px-4 py-1.5 transition-colors",
                !yearly ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground",
              )}
            >
              Monthly
            </button>
          </div>
        </div>
        <div className="max-w-[19rem] text-sm leading-relaxed text-muted-foreground">
          <p>
            Chat is free while it&apos;s in development, with 200 messages and 30 web searches a
            day for every account. These plans are examples of how pricing could work.
          </p>
          <p className="mt-3 flex items-center gap-2.5 text-foreground/85">
            <span className="flex size-5 items-center justify-center rounded-[4px] border border-line">
              <Check aria-hidden className="size-3" />
            </span>
            No billing is set up yet
          </p>
        </div>
      </div>

      <ul className="grid gap-y-4 px-5 pb-24 sm:px-12 sm:pb-28 md:grid-cols-3">
        {plans.map((plan) => {
          const price = yearly ? plan.yearly : plan.monthly;
          return (
            <li
              key={plan.name}
              className={cn(
                "flex flex-col px-6 py-8 md:px-8",
                plan.popular && "border border-dashed border-muted-foreground/40",
              )}
            >
              <div className="flex items-center justify-between gap-3">
                <h3 className="text-base font-medium">{plan.name}</h3>
                <span className="rounded-[4px] border border-line px-2 py-0.5 text-xs text-muted-foreground">
                  Example
                </span>
              </div>
              <p className="mt-5 flex items-baseline gap-1">
                <span className="font-display text-[2rem] font-medium tabular-nums">${price}</span>
                <span className="text-sm text-muted-foreground">/month</span>
              </p>
              <p className="mt-2 min-h-10 text-sm leading-relaxed text-muted-foreground">{plan.description}</p>
              <ul className="mt-6 space-y-3 border-t border-line pt-6 text-sm">
                {plan.features.map((feature) => (
                  <li key={feature} className="flex items-center gap-3">
                    <Check aria-hidden className="size-4 shrink-0 text-live" />
                    {feature}
                  </li>
                ))}
              </ul>
              <SlideButton
                href="/register"
                variant={plan.popular ? "solid" : "outline"}
                className="mt-8 justify-center"
              >
                Create free account
              </SlideButton>
            </li>
          );
        })}
      </ul>
    </RailSection>
  );
}
