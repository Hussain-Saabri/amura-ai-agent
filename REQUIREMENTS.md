# Requirements — Pharma Voice Ordering Agent

Companion to [PLAN.md](PLAN.md). IDs are stable; reference them in commits and tickets.

Priority: **M** = must-have for pilot · **S** = should-have · **C** = could-have (post-pilot)

---

## A. Functional — call handling

| ID | Requirement | Pri |
|---|---|---|
| FR-01 | Answer inbound calls on a published distributor number | M |
| FR-02 | Disclose at call start that the caller is speaking to an AI assistant | M |
| FR-03 | Announce call recording and obtain implied consent before recording | M |
| FR-04 | Identify the caller from ANI/caller-ID against the customer master; greet by shop name | M |
| FR-05 | Fall back to spoken customer-code or registered-mobile capture when caller ID is unknown or withheld | M |
| FR-06 | Accept Hindi, English, and Hindi-English code-mixed speech | M |
| FR-07 | Support barge-in — caller can interrupt mid-sentence and the agent stops speaking | M |
| FR-08 | Handle silence: re-prompt after 5s, "are you still there?" at 10s, graceful end at 20s | M |
| FR-09 | Transfer to the human order desk on request ("baat karao", "talk to someone") within one turn | M |
| FR-10 | Warm-transfer on escalation, passing the partial cart to the desk agent | M |
| FR-11 | Handle desk-closed / after-cut-off calls with a clear message and callback offer | S |
| FR-12 | Support additional regional languages per your customer base (Marathi, Gujarati, Kannada…) | C |

## B. Functional — ordering

| ID | Requirement | Pri |
|---|---|---|
| FR-20 | Resolve a spoken product request to a specific SKU (`product_code`) | M |
| FR-21 | Ask a natural disambiguating question when confidence is below threshold or multiple SKUs match | M |
| FR-22 | Never auto-select an SKU below the confidence threshold | M |
| FR-23 | Accept requests by brand name, generic/molecule name, or company name | M |
| FR-24 | Report live availability, quoting free (unallocated) stock, not gross stock | M |
| FR-25 | Allocate batches FEFO — earliest saleable expiry first | M |
| FR-26 | Disclose on-call when the allocated batch expires within the policy window | M |
| FR-27 | Confirm the ordering **unit** explicitly (tablets vs. strips vs. boxes) before booking | M |
| FR-28 | Round quantities to sellable pack multiples and state the rounding aloud | M |
| FR-29 | Enforce MOQ per SKU | S |
| FR-30 | Quote PTR on request; quote MRP on request; state which is which | M |
| FR-31 | State the current scheme/offer for an SKU on request (e.g. 10+1) | M |
| FR-32 | Offer to repeat the customer's previous order ("same as last time?") | S |
| FR-33 | Support multi-line orders in one call — add, remove, and amend lines | M |
| FR-34 | Read the complete cart back — lines, quantities, net amount — before confirmation | M |
| FR-35 | Require explicit spoken confirmation before writing the order | M |
| FR-36 | Suggest an alternative (same generic, different brand) when an item is out of stock | S |
| FR-37 | State the expected delivery day based on the customer's route/beat | S |
| FR-38 | Send a post-call SMS/WhatsApp order summary | S |
| FR-39 | Upsell/remind on near-expiry stock clearance offers | C |

## C. Functional — compliance blocks (enforce in code, never in the prompt alone)

| ID | Requirement | Pri |
|---|---|---|
| FR-50 | **Block Schedule X and NDPS/narcotic items from voice ordering.** Route to human desk. | M |
| FR-51 | Flag Schedule H1 items for desk review per company policy | M |
| FR-52 | Refuse to book when the customer's drug licence is expired in the master; transfer to desk | M |
| FR-53 | Refuse to book when the customer is credit-blocked or overdue; state politely and transfer | M |
| FR-54 | Never give clinical, dosage, substitution, or medical advice; deflect and offer the desk | M |
| FR-55 | Cap single-line and single-order quantity at a configurable sanity threshold, escalating above it | S |

## D. Data & ERP

| ID | Requirement | Pri |
|---|---|---|
| DR-01 | Read access to `product_m` — product_code, name, pack, company FK, generic FK, schedule flag, MRP, PTR, GST%, pack multiple, MOQ | M |
| DR-02 | Read access to `batch_m` — batch, product_code, expiry, stock qty, reserved qty, selling price | M |
| DR-03 | Read access to `company` and `generic` masters | M |
| DR-04 | **Confirm the unit of `batch_m.stock_quantity`** — base units or packs. Blocks all quantity logic. | M |
| DR-05 | Customer master: phone → customer_code, shop name, drug licence no. + expiry, GST no., credit limit, outstanding, overdue flag, route/beat | M |
| DR-06 | Scheme/offer master per SKU with validity dates | M |
| DR-07 | Order history (12 months) for alias seeding, popularity weighting, and reorder suggestions | M |
| DR-08 | Read-only DB user for the agent; **no write access to ERP tables** | M |
| DR-09 | Denormalised read views per tool, pre-computing free stock, FEFO expiry, and active scheme | M |
| DR-10 | `product_alias` table — phonetic keys, misspellings, retailer shorthand; nightly rebuild | M |
| DR-11 | ERP order-create API: accepts customer_code, lines, idempotency key; returns order_no + net amount | M |
| DR-12 | Staging tables for Phases 2–3 so orders can be reviewed before going live to ERP | M |
| DR-13 | Nightly refresh job for resolver indexes; new SKUs available within 24h | S |
| DR-14 | Stock reservation at order confirmation, so two concurrent calls can't oversell one batch | S |

## E. Voice & language

| ID | Requirement | Pri |
|---|---|---|
| VR-01 | Streaming STT — Sarvam `saaras:v3`/`v4`, `mode="transcribe"`, over WebSocket (`saarika:v2.5` is deprecated) | M |
| VR-02 | Streaming TTS — Sarvam `bulbul:v3`, `speech_sample_rate=8000` | M |
| VR-03 | Correct μ-law 8kHz ↔ PCM16 conversion between telephony and Sarvam | M |
| VR-04 | VAD-based turn detection with utterance buffering — **not** per-frame STT | M |
| VR-05 | Correct TTS pronunciation of ₹ amounts, strengths (`625`), and pack notation (`10's`) | M |
| VR-06 | Spoken-number normalisation, including Hindi numerals ("saath" → 60) | M |
| VR-07 | A/B evaluate `saaras:v3` vs `v4`, and `mode=transcribe` vs `verbatim`, on real recordings | M |
| VR-10 | **Upsample 8kHz telephony audio to 16kHz before STT** — Sarvam is tuned for 16k; 8k degrades consonants | M |
| VR-11 | Set `language_code` and `input_audio_codec` explicitly rather than relying on defaults | S |
| VR-12 | Resolver must tolerate STT word-splitting (`"kom bi plam"` → Combiflam) — space-collapsing + **fuzzy** phonetic match, not exact | M |
| VR-08 | Consistent single voice persona across the call | S |
| VR-09 | Filler audio ("ek minute…") when a tool call runs long | S |

## F. Non-functional

| ID | Requirement | Pri |
|---|---|---|
| NFR-01 | Median turn latency < 1.5s; p95 < 2.5s | M |
| NFR-02 | Support 10 concurrent calls at pilot; scale to 50 | M |
| NFR-03 | Fully async I/O — no blocking DB or HTTP calls in the event loop | M |
| NFR-04 | Per-call session isolation; no cart state leakage between calls | M |
| NFR-05 | Idempotent order writes — retries and dropped calls cannot double-book | M |
| NFR-06 | Graceful degradation: if STT/TTS/LLM fails mid-call, transfer to human rather than drop | M |
| NFR-07 | Structured logging per call: audio, transcript, tool calls + results, outcome, latency per turn | M |
| NFR-08 | Secrets in `.env` / secret manager; **nothing hardcoded**; `.env` git-ignored | M |
| NFR-09 | Cost telemetry per call (STT sec, TTS chars, LLM tokens) with a per-call ceiling alert | S |
| NFR-10 | Reviewable dashboard of calls and outcomes for the order desk | S |
| NFR-11 | Automated regression suite over the 200-utterance resolver test set, run in CI | S |

## G. Compliance & legal (India)

| ID | Requirement | Pri |
|---|---|---|
| CR-01 | TRAI/DLT registration as required for the inbound number | M |
| CR-02 | Call recording consent announcement at call start | M |
| CR-03 | DPDP Act 2023: stated purpose, defined retention period, deletion process for recordings and transcripts | M |
| CR-04 | Drugs & Cosmetics Act: order records tie to a valid retailer drug licence | M |
| CR-05 | Schedule X / NDPS items excluded from voice ordering (see FR-50) | M |
| CR-06 | Voice recordings and PII encrypted at rest and in transit | M |
| CR-07 | Legal sign-off that a voice-confirmed order is a valid purchase order for your terms of trade | M |
| CR-08 | Audit trail: every order traceable to a recording and transcript | M |

---

## H. Accounts & infrastructure to procure

| Item | Notes | Lead time |
|---|---|---|
| Telephony account + DID | Exotel or Plivo; KYC required | **Days — start now** |
| Sarvam AI API key | Paid plan; STT ≈ ₹30/hr, TTS ≈ ₹15–30/10K chars | Hours |
| Anthropic API key | Claude Sonnet | Hours |
| Server | India region (Mumbai), public HTTPS/WSS, 4 vCPU+ | Hours |
| ERP API access | Order-create endpoint + read-only DB user | **Depends on ERP team — raise now** |
| SMS/WhatsApp sender | For FR-38 order confirmations; DLT template approval | Days |
| ngrok / tunnel | Local development only | Minutes |

**Rough running cost per 3-minute call:** ₹1.5 STT + ₹2–4 TTS + ₹3–6 LLM + telephony ≈ **₹8–15/call.** Validate against your cost-per-order via the desk before scaling.

---

## I. Open questions

Schema inspected 2026-08-04 — see [PLAN.md §1a](PLAN.md). The local DB is a 3-product demo, so most of these still stand.

**Answered**
- ~~Are Schedule X / H1 / NDPS flags on `product_m`?~~ **No — absent entirely.** Must come from the real ERP or be derived.
- ~~Is there a scheme/offer master?~~ **Not in this database.**
- ~~Where does the customer master live?~~ **Not in this database.**

**Blocking Phase 1**

1. **What unit is `stock_quantity` in?** The demo data implies **packs/strips** (`selling_price=14.00` for one Crocin 500 strip), but [system_flow.md](system_flow.md:33) shows `{stock: 1200, unit: "tablet"}`. **These contradict each other.** *(DR-04 — blocks all quantity logic)*
2. **Can we get a replica of the real ERP catalogue?** *(now the critical-path dependency — Phase 1 can't be validated on 3 products)*
3. Is the ERP MySQL or SQL Server behind .NET? The demo is MySQL; `system_flow.md` implies SQL Server.
4. Where is the **company/manufacturer** master? You mentioned one; it isn't in this database.
5. Does an ERP **order-create API** already exist, or must one be built? What is its contract?
6. Is `selling_price` the **PTR**, and is there a separate trade/scheme rate?
7. Is phone number reliably populated and unique on the customer master?
8. Where is **credit limit / outstanding / overdue** held, and is it queryable in real time?
9. Is **reserved/allocated qty** tracked anywhere? Without it, "free stock" (FR-24) cannot be computed.
10. **Near-expiry policy** — how many months out must the agent disclose?
11. Which **languages** do your retailers actually call in? *(drives FR-12 scope)*
12. **Order cut-off time** and route/beat delivery mapping — is this data available?
13. How many **concurrent calls** at peak, and what are your peak ordering hours?
