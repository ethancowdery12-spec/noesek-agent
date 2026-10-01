# Noesek paywall and business plan
Research checked September 30, 2026. Written proposal only. No code, deployment, purchases, account access, or ad launch performed.

## Decision

Keep the personal/self-hosted route free of a Noesek subscription, with the user paying their own infrastructure and inference costs. For a future hosted product, start with a small, capped free experience followed by a clear paid offer. Do not copy the videos' blanket hard-paywall, higher-price, longer-trial rules. First prove that a specific audience returns for a useful, reliable task and that serving them has positive contribution margin. Keep the hosted offer separate from Ethan's existing personal installation. [V1, V2, S1, S4, S5]

Before charging anyone, resolve two launch gates: channel eligibility and per-user identity/data isolation. Meta currently restricts general-purpose AI assistants on WhatsApp Business Platform to permitted markets. Do not assume the existing personal adapter establishes commercial eligibility, and do not use unofficial automation to bypass the restriction. A different compliant channel or Ethan's planned app can be evaluated, but this research did not verify those channels' current rules. [S10, S11]

## All five videos: takeaways, corrections, action

### V1. Only 5 Out Of 100 Apps Make $10K A Month, Here's What They Do
https://youtu.be/5nKThsb8bO0

The transcript recommends hard paywalls, trials longer than three days, higher prices, and persistence to day 109. Useful takeaway: measure monetization and allow enough time for product learning. Plan action: run separate paywall, trial-length, and pricing tests rather than importing all three at once. [S1, S4]

Corrections from the original RevenueCat report:
- 4.6% of newly launched apps in its benchmark reach $10K monthly revenue within their first two years. This is not the chance that any random app makes $10K in its first month.
- $3.09 versus $0.38 is median revenue per install at day 60, hard-paywall versus freemium. It is not profit, not lifetime revenue, and not a causal effect of switching the same app.
- The report's 42.5% versus 25.5% trial comparison is long trials of 17-32 days versus the short-trial bucket around four days or fewer, not proof that every trial longer than three days nearly doubles conversion.
- 109 days is the median time to $10K among apps that reach the milestone, not a guaranteed payoff from waiting. The video supplies no evidence that most founders quit before day 100.
- The report does not establish that the successful 4.6% all share the four claimed behaviors. [S1, S2]

### V2. Only 5 Out Of 100 AI Apps Make $10K A Month, Here's What They Do Differently
https://youtu.be/O5JMMjqqydM

The transcript repeats V1 and warns that free AI users spend the founder's money. Useful takeaway: meter inference, tools, retries, storage, and support before offering free hosted access. Plan action: bounded free quota, model routing, job budgets, and no automatic paid overage. [S1, S5, S6]

Corrections: 4.6% and the 109-day figure above are all-category benchmarks, not established AI-only figures. Non-AI apps also incur infrastructure/support costs. AI cost varies by tokens, model, cache, tools, and retry behavior; a BYOK user may bear inference cost directly. "Nobody choosing between two AI apps is choosing on price" is an unsupported absolute. The report also says AI apps generate 41% more revenue per payer but churn 30% faster, so retention matters alongside sales. [S1]

### V3. The "Infinite Rent" Method by Graham Stephen
https://youtu.be/R5gxIDPmkxE

The transcript describes Graham Stephan retaining good tenants by never increasing their rent and repricing when tenants change. Useful analogy: predictable pricing can protect trust and reduce churn. Plan action: offer a limited founding-member price protection period for the same plan and allowance, then review economics. Do not promise lifetime unlimited AI at a fixed price. Define upgrade, lapse, reactivation, and allowance rules before selling the offer. [V3, S5, S6]

Correction: a landlord story is not causal evidence for software retention, nor proof that never raising subscription prices maximizes profit. Inference/data/channel costs can change. Noesek should keep cancellation and export easy rather than seek "never stop paying" lock-in. [V3; proposed business judgment]

### V4. How to Build a System That Can Produce 1,000 Ads a Month
https://youtu.be/qAIBT6myWtA

The transcript proposes AI creative via Claude/Meta/Higgsfield connectors, creator UGC, reusable in-house templates, and a separate testing pipeline. Useful takeaway: create a repeatable brief-to-asset-to-result workflow. Plan action: start with a small batch of founder demonstrations and reusable templates, document results, then add paid AI generation or creators only after retention and acquisition economics justify them. [V4, S7, S8, S9]

Corrections: 1,000 assets is a production-volume claim, not evidence of profitable growth. Every creator getting a separate ad set is not a controlled comparison if audiences/budgets differ. Meta documents mutually exclusive audiences and one variable per split test. Higgsfield MCP exists but ALWAYS spends credits; its website's free or unlimited generations do not carry over to MCP. Its API is a separate dollar-funded product, not free inference. Automated publication, campaign budgets, and spend need approval, not autonomous connector access. [S7, S8, S9]

### V5. ChatGPT and Claude Are Guessing on Real Estate Deals - This AI Actually Knows the Numbers
https://youtu.be/PZHaHHqpOnw

The transcript names "Lisa," claims rent/sales comps and market data "from X," and calls it the new industry standard. Useful takeaway: sell a narrowly defined workflow backed by traceable data, not generic chat. Plan action: Noesek outputs should carry source, freshness, assumptions, deterministic calculations, and a refusal/qualification when evidence is missing. Start with a lower-risk task rather than financial underwriting. [V5, S12, S13]

Unresolved vendor identity: searches returned multiple unrelated Lisa products; the video offers no canonical link or precise provider for "X." I inspected lisaprop.com, which describes commercial property leasing/workflow software, but could not bind it to this video. Do not recommend or price a guessed Lisa service. No verified evidence establishes "industry standard." General-purpose models can analyze supplied files or connected sources; specificity alone does not guarantee accurate data or analysis. RealQuant's own site illustrates connected-data and provenance features, but those are vendor claims, not independent accuracy benchmarks and not proof of Lisa's identity. [S12, S13]

## What the evidence actually supports

RevenueCat's original 2026 report covers over 115,000 apps, more than $16B revenue, and over a billion transactions. Its methodology selects RevenueCat-integrated apps with active subscription revenue and minimum installs/revenue; metrics mainly concern 2025 and include iOS, Android, and web. This is a selected commercial sample, not every app or a messaging-agent study. Published aggregates were inspected directly; underlying app-level data is anonymized and unavailable for independent reanalysis. [S1]

Hard-paywall day-35 download-to-paid medians are 10.7% versus 2.1% for freemium. These are observational between-app comparisons: category, audience intent, acquisition mix, price, and product quality may confound them. RevenueCat says one-year retention is nearly identical between access models. None of this establishes what will happen to Noesek. [S1]

There is real randomized trial evidence pointing in the opposite direction from "longer always wins." Yoganarasimhan, Barzegary, and Pani studied 337,724 users randomly assigned to 7-, 14-, or 30-day trials at one SaaS firm, with outcomes followed for two years. Their paper reports the seven-day uniform policy produced a 5.59% subscription gain over the 30-day baseline in its test data. This supports testing, not a universal seven-day rule: the experiment began in 2015, concerned a different product, and predates today's AI cost profile. [S4]

RevenueCat's 2026 case study reports a 75% LTV increase for one freemium transition and a greater than 50% conversion decline for another. The favorable case changed pricing and packaging too. Treat both as anecdotes/observational case evidence, not clean randomized proof of paywall layout. Apple gives presentation and disclosure requirements, not proof of conversion uplift. [S3, S14]

## Implementable product and paywall design

### 1. Establish one audience and one paid job

Interview a small group of likely users about an actual repeated task. Candidate positioning: "A messaging assistant that turns a request into a sourced result and keeps you in control of outside actions." Test this against one concrete outcome such as a sourced research brief or a document workflow. Measure successful completion without user correction, time to first value, and weekly repeat use. Avoid "does everything better" and real-estate-return claims without evidence. Treat this as a proposed positioning experiment, not a proven niche. [V5, S1]

Onboarding should ask which job they want done, show one real example with sources, explain connected-account permissions, and obtain narrow consent only when needed. Show progress, pending approval, completed result, and a useful failure explanation. The product's trust signal is visible correctness and control, not a long capability list. [V2, V5; proposed design]

### 2. Separate offers

- Personal/self-hosted: no Noesek subscription proposed. Clearly disclose that BYOK, compute, storage, channels, and paid data may still cost the user. Recheck applicable upstream licenses before promising a commercial distribution offer; this research did not audit licensing. [V2, S5, S6]
- Hosted free: enough bounded usage to complete a meaningful job, with an enforceable server-side cost ceiling and a clearly visible reset. Set the allowance from measured costs, not an arbitrary "unlimited" message count. Prototype job bundles, but include spend/runtime caps because ten cheap tasks and ten expensive tasks are not equivalent. [V2, S5, S6]
- Hosted paid: one monthly plan at first, with explicit allowance and feature differences. Price and quota remain hypotheses until measured usage and willingness-to-pay research. Optional extra use requires a deliberate purchase; no default automatic overage. [V1, V2]
- Annual: add only after retention and cost variance support the promise. Display the full annual amount and billing cadence, even when showing a monthly equivalent. No lifetime-unlimited inference offer. [V1, V3, S14]

### 3. Paywall moment and information order

Default candidate: offer the upgrade after a verified useful result, or immediately before a costly feature with a preview of what it does. Keep a hard gate after an honest product demonstration as an alternative to test; do not start by forcing every personal/self-hosted user to pay. [V1, V2, S1, S3]

Use this information order:
1. The job the plan helps finish, with one truthful example.
2. Paid allowance/features and what remains free.
3. Monthly total, or annual total and billing cadence; applicable taxes or checkout caveat.
4. Trial duration and exactly when/what the user will be charged. For a cardless trial, state that it ends without charging.
5. Clear "Continue free" where applicable, "Subscribe," restore purchases where applicable, and manage/cancel access. No hidden close button, fake countdown, invented discount, or misleading testimonial. [S14, S15]

Start with a cost-capped, cardless evaluation to learn whether users reach value. Then test 7 versus 14 days with the same total cost allowance, or another trial shape supported by the task's cadence. Do not change price, quota, and trial length in the same experiment. The 17-32-day benchmark can motivate a later test for workflows that need several weeks; it does not justify unlimited free AI for a month. [V1, V2, S1, S2, S4]

### 4. Price stability without a dangerous promise

Candidate founding offer: protect the same plan's subscription price for a stated period, such as 12 months, with explicit lapse/reactivation terms. Keep usage allowances bounded and do not silently erode them. Price new cohorts separately, then compare contribution margin, satisfaction, and retention. Any subsequent price change needs clear notice and cancellation/export options. The 12-month duration is a proposal, not research-backed optimum. [V3, S5, S6]

## Implementation specification for a later build

These are acceptance criteria, not changes made in this assignment. [V2, V4, V5; proposed engineering plan]

1. Identity first: account_id independent of chat_id; verified mapping of approved channels; tenant-scoped memory, files, credentials, usage, and billing. Test cross-user isolation before enabling a shared hosted product. Current memory context indicates a shared memory pool until Ethan's future UI supplies identity; that is not safe to carry unchanged into multi-user commercialization.
2. Catalog: versioned plan_id, currency, billing period, allowance, free reset, trial dates, regional availability, and price-protection terms. Persist the terms accepted by each customer.
3. Entitlements: one server-side record per account; idempotent, authenticated billing webhooks. Never trust a client-reported purchase flag. Handle pending, trial, active, grace, cancelled-but-paid-through, expired, refunded, and revoked states.
4. Metering: estimate/reserve job budget before execution, reconcile actual provider costs, include retry costs, and release unused reservation. Cap tokens, tool calls, execution time, concurrency, and expensive media generation. No paid-provider fallback beyond the agreed budget.
5. Two independent gates: subscription access permits using a feature; it does not authorize messages, account changes, bookings, purchases, or ads. Keep action approvals distinct from entitlements.
6. Recovery: show billing failure/grace states and manage-payment options; export and account deletion remain available. Cancel recurring external jobs when they should stop, rather than leaving silent paid activity.
7. Privacy: do not send personal conversation content, credentials, or connected documents into advertising analytics or creative generation. Use consented, anonymized demonstrations and actor/creator releases.
8. Test fixtures: duplicate/delayed/out-of-order webhooks, cross-channel entitlement consistency, quota reset, refunded purchase, failed billing, cancelled renewal, trial reuse/abuse, model timeout, duplicate job, and paid-fallback cap. Support should be able to explain every deduction and access decision.

## Vendor shortlist and cost reality

Prices observed September 30, 2026, not commitments. Recheck before implementation.

| Vendor | Verified current terms | Proposed role / limitation |
|---|---|---|
| RevenueCat | Free up to $2,500 monthly tracked revenue; then 1% of tracked revenue once threshold is hit. Page does not say charge only the excess. All features included, with SDKs, unified backend, paywalls and tests. [S16] | Candidate if native mobile subscriptions or cross-channel entitlements warrant it. Additional to payment/store and inference costs. Not needed solely to draw a prototype paywall. |
| Stripe | Standard US domestic online cards: 2.9% + $0.30 per successful transaction. Billing has a separate pay-as-you-go volume fee and no recurring fee; its fetched page omitted the numeric percentage, so that rate is not asserted here. [S17, S18] | Candidate for a compliant web purchase route. Do not assume native-app external checkout is allowed everywhere. Hosted portal can reduce custom billing UI work. |
| DeepSeek API | Flash peak: $0.006 cache-hit input, $0.30 cache-miss input, $1.20 output per million tokens. Pro peak: $0.044/$1.32/$3.96 respectively. Off-peak rates half those peak rates. Current page maps legacy Flash names to V4.1-Flash. [S5] | Meter actual model/version and peak/off-peak/cache behavior. Page establishes paid token usage; no free hosted inference allowance verified. |
| Claude | Consumer Free is $0; Pro is $20 monthly or $200 up front annually. API priced separately: Sonnet 5 $2 input/$10 output and Haiku 4.5 $1/$5 per million tokens, before cache/tool adjustments. [S6, S19] | A free chat account or paid Claude consumer subscription is not a free inference backend for Noesek. |
| Higgsfield | MCP always uses plan credits; no automated unlimited/free generations. API is separate prepaid USD billing, $5 minimum top-up, per-model/configuration rates; failed jobs not billed, funds expire after one year. [S7, S8] | Optional later creative production, not required for launch. Website subscription prices could not be verified from its sparse pricing-page response; no invented monthly price. |
| Meta / WhatsApp | Ordinary service-window free messaging must not be assumed to apply to general-purpose AI providers. Official AI-specific terms restrict eligibility and some markets incur per-message charges. [S10, S11] | Verify exact integration and markets before selling messaging-native access. |
| Lisa | No canonical video-linked vendor, pricing, data licensing, coverage, or accuracy evidence verified. [V5, S12] | Not selected. Ask for the creator's exact link only if evaluating this vendor becomes necessary. |

Illustration, not a task quote: 100,000 cache-miss input tokens plus 10,000 output tokens at DeepSeek peak prices costs $0.042 on Flash or $0.1716 on Pro. This arithmetic excludes repeated calls, search/browser APIs, media, infrastructure, messaging, taxes, payment fees, and support. A job's actual total can be much higher. [S5; calculated]

Use a ledger: net receipts minus inference, data/tool costs, channel fees, infrastructure allocation, refunds, support, and creator/ad spend. Review both average and high-percentile user cost. Contribution per activated user and per paying user matter more than revenue per download. Set the free allowance from an explicit total subsidy budget, and the paid allowance from an explicit margin target. These are business decisions Ethan must set, not numbers inferred from a short video. [V2, S1, S5-S8, S17-S18]

## Measurement and rollout

### Stage A: zero-spend discovery and product audit

Write the exact audience/job, inspect current reliability, resolve identity and channel eligibility, record cost per successful task, and create an honest demo. Do not turn on billing or ads. Use interviews and existing voluntary usage before funding trials. [V2, V5, S10, S11]

### Stage B: bounded pilot

Proposed pilot: a small invited cohort, no unlimited promise, clear personal versus hosted terms, and manual support. Instrument first request, successful task, correction, repeat task, quota warning, offer viewed, purchase, cancellation, refund, and billing recovery. Store experiment IDs and aggregate analytics, not raw private chat. A sample of 10-20 interviews can reveal friction but cannot establish a statistically reliable conversion winner. [S1, S4; proposed pilot sizing]

### Stage C: one test at a time

Test order: (1) onboarding/demo and paywall timing, (2) trial length, (3) price/packaging, (4) annual option. Assign users consistently at account level. Hold audience, channel, and other offer terms constant. Define the minimum meaningful improvement, sample size, observation horizon, and stopping rule before launch. Report uncertainty; do not peek daily and declare a winner at the first favorable day. Track paid conversion, activation, 30/60/90-day retention, refunds, corrections, and contribution margin. A high conversion rate with more complaints or loss-making usage is not a win. [S1, S4, S9]

### Stage D: small creative pipeline, then paid growth if warranted

Adapt the video's three factories in a cheaper order:
- Templates first: a real founder demo, a problem/result comparison, and a sourced workflow walkthrough. Make a few meaningful variations, not 1,000 near-duplicates.
- Creator stories later: consent, rights, compensation, accurate claims, and clear sponsorship. No recruiting hundreds before product fit.
- AI creative last: drafting-only connectors initially, credit checks, cost ceilings, and human review. Never feed customers' private results into ad tools.

Tag each asset with concept, hook, format, rights status, landing offer, and cohort outcomes. For paid tests, use Meta's supported split-test design rather than attributing causality to ad-set ROAS differences. Optimize acquisition for retained, margin-positive users rather than clicks, asset count, or attributed revenue alone. Ad budgets and publishing remain a separate approval decision. [V4, S7-S9]

### Stage E: go/no-go review, not "wait until day 109"

Review learning at regular intervals, including a roughly 90-day checkpoint if a pilot is viable. Continue only if users repeatedly get the intended outcome, high-cost usage fits the offer, trust guardrails work, and acquisition has a plausible payback path. Pivot or stop the hosted offer if these fail. Keep the personal-use route separate. Day 109 is descriptive survivor timing, not a deadline or business guarantee. [V1, V2, S1]

## Decisions still needed before any execution

- Personal-only project, hosted business, or both?
- First paying audience and repeat job.
- Applicable channel/market permission and future app/storefront route.
- Acceptable monthly pilot subsidy, support load, margin target, and price hypotheses.
- Free allowance, trial shape, grandfathering terms, data-retention/export policy.
- Exact Lisa link if that vendor is to be evaluated.

## Source ledger

Videos: all five transcript bodies were retrieved through their supplied page URLs. These are promotional/commentary sources, not experiments. Automated caption download was rate-limited for four; the page fetch returned full transcripts for all five. Numerical claims were checked against the underlying sources below rather than relying on video narration.

S1. RevenueCat, State of Subscription Apps 2026. Original published benchmark and methodology, chiefly 2025 data. Observational, selected platform sample. https://www.revenuecat.com/state-of-subscription-apps/
S2. RevenueCat, 2026 report summary. Official trial-bucket detail. https://www.revenuecat.com/blog/growth/subscription-app-trends-benchmarks-2026
S3. RevenueCat, Hard paywall vs. freemium: lessons from a 75% LTV lift, April 29, 2026. Case study, concurrent changes, not clean causal proof. https://www.revenuecat.com/blog/growth/hard-paywall-vs-freemium
S4. Yoganarasimhan, Barzegary, Pani, Design and Evaluation of Personalized Free Trials; primary paper, randomized 2015-16 SaaS experiment, 337,724 participants. https://arxiv.org/pdf/2006.13420 . Published article record: https://ideas.repec.org/a/inm/ormnsc/v69y2023i6p3220-3240.html
S5. DeepSeek, Models & Pricing, official current API prices. https://api-docs.deepseek.com/quick_start/pricing
S6. Anthropic, API pricing, official current model prices and adjustments. https://platform.claude.com/docs/en/about-claude/pricing
S7. Higgsfield, official MCP guidance, modified September 24, 2026. https://higgsfield.ai/creator-hub/help-center/integrations/what-is-higgsfield-mcp
S8. Higgsfield, official API billing guidance. https://higgsfield.ai/creator-hub/help-center/integrations/what-is-the-higgsfield-api
S9. Meta, Split Testing, updated March 25, 2026; official experimental-design mechanics, not a measured conversion result. https://developers.facebook.com/docs/marketing-api/guides/split-testing/
S10. Meta, current AI-provider WhatsApp eligibility and pricing guidance. https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing/ai-providers
S11. Meta, Terms for WhatsApp Business Platform, updated September 23, 2026, section 4.7. Page is labeled preview but gives effective terms/date; cross-checked with S10. https://www.facebook.com/legal/Meta-Terms-for-WhatsApp-Business-Platform-preview . Earlier March 6 terms: https://www.whatsapp.com/legal/business-solution-terms/?facet1=pdf
S12. Lisa property-management platform, own site inspected solely as an unbound candidate, not identified as video's vendor. https://www.lisaprop.com/
S13. RealQuant, own site describing connected comps, document extraction and cell-level provenance; vendor marketing, not independent validation. https://www.realquant.ai/
S14. Apple, Auto-renewable Subscriptions; official disclosure, offer, and management guidance. https://developer.apple.com/app-store/subscriptions/
S15. Apple, App Review Guidelines, sections 3.1.1-3.1.3; official storefront/payment rules, must be rechecked for exact distribution. https://developer.apple.com/app-store/review/guidelines/
S16. RevenueCat, official pricing. https://www.revenuecat.com/pricing/
S17. Stripe, official US standard pricing. https://stripe.com/pricing
S18. Stripe Billing, official pricing; dynamic percentage missing from fetched body, numeric percentage left unverified. https://stripe.com/billing/pricing
S19. Anthropic, consumer plans, official pricing. https://www.anthropic.com/pricing
Additional inspected background: RevenueCat's 2023 paywall explanation, not causal evidence: https://www.revenuecat.com/blog/growth/hard-paywall-vs-soft-paywall . Ordinary WhatsApp pricing, not interchangeable with AI-provider rules: https://developers.facebook.com/docs/whatsapp/pricing . Higgsfield website pricing returned navigation without usable plan numbers: https://higgsfield.ai/pricing .

## Post-research identity correction
The original PZHaHHqpOnw description links https://leasetab.com/ask-lisa. That page was opened September 30 and names Ask Lisa on Lease Tab, confirming the video-linked vendor identity. Its sparse content does not establish rent/sales comparables, accuracy, market data access, pricing, or industry-standard status. The earlier unresolved-identity finding is superseded only for identity; no vendor was purchased or connected.
