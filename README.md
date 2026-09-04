# AI Job Radar v7

A personal job-discovery workspace focused on Hyderabad-first Senior SRE / DevOps / Cloud / Platform / Software / DBRE roles.

## Included

- **5-minute background scanner by default** for enabled company career pages and configured public ATS/RSS sources.
- **Greenhouse + Lever + RSS adapters** where a company is configured for them.
- **LinkedIn + Naukri alert imports** without storing account credentials or using authenticated scraping.
- **Persistent Settings**: scanner cadence, request timeout, dashboard refresh, default location and source enable/disable controls.
- **Resume Intelligence**:
  - PDF / DOCX / TXT upload and parsing
  - editable master resume
  - version history + restore
  - job-specific resume evidence coverage
  - **Resume ↔ Job Compatibility %**
  - Job Match % vs Resume Coverage % shown separately
  - AI optimization when an OpenAI API key is configured
  - safe fallback suggestions when AI isn't configured
  - DOCX/PDF/TXT export
- **Dashboard** with match bands, freshness, source filters, location filters, shortlist/applied tracking and scanner health.
- **Dark / light mode**.
- Dashboard-only automatic refresh; detail pages don't unexpectedly reload.

## Compatibility score

`Compatibility = Job Match × 55% + Resume Coverage × 45%`, with a small role-title evidence bonus capped at 5 points.

This is intentionally transparent: a high Job Match score does not automatically mean the uploaded resume proves the required skills.

## Run with Docker

```bash
docker compose up --build
```

Then open `http://localhost:3000`.

Backend health: `http://localhost:8000/health`

## AI configuration

Copy `.env.example` to `.env` and set:

```env
OPENAI_API_KEY=your_key
OPENAI_MODEL=your_model
```

AI optimization is optional. Resume matching and rule-based optimization suggestions work without an API key.

## Source policy

The scanner uses public career/ATS/RSS endpoints that are configured in `data/companies.json`. LinkedIn and Naukri are supported through alert import rather than authenticated account scraping.

## Testing

Install backend requirements and run:

```bash
cd backend
pytest -q
```

## 7.0.1 UI changes
- Dashboard match bands are now four primary cards: 91–100%, 81–90%, 71–80%, and 61–70%.
- Each match card links to its corresponding filtered job list.
- Removed match-band shortcuts from the left navigation; Jobs is now a single navigation entry.
- Applied and Shortlisted remain as dashboard cards and link to their respective views.
- Career scan controls now enforce a 5-minute minimum: 5m, 10m, 15m, 30m, 1h.

## v7.0.2 changes
- Publication dates now prioritize explicit `datePosted` / `Posted Date` values and support ordinal dates such as `August 5th 2026`.
- `dateModified` is no longer used as a publication-date fallback.
- Job descriptions preserve paragraph, heading, and bullet structure when extracted from employer HTML.
- AI API key errors are presented as a friendly configuration message instead of raw provider JSON.
- Dashboard match bands are first-class clickable cards for 91–100%, 81–90%, 71–80%, and 61–70%.
- Added Electronic Arts, CIBC, McDonald's, Lloyds Technology Centre, and Marriott Technology Accelerator.

## v7.0.3 changes
- Job-detail pages refresh the source URL on open so the original publication date and cleaned description are re-extracted from the employer page.
- Explicit visible `Posted Date` now takes precedence over generic JSON-LD/update timestamps; `dateModified` is never treated as publication date.
- Repeatedly escaped employer HTML is decoded and sanitized before storage/API output, preventing literal `<p>`, `<li>`, `<b>`, etc. from leaking into the job description.
- Dashboard greeting now starts with the user's name, and the scanner source summary is presented as a single compact line.
- Settings redesigned around scanner overview, source controls, dashboard refresh, location and appearance; scanner minimum is enforced at 5 minutes server-side.
- Companies redesigned as searchable/filterable monitoring cards and expanded with 30 additional Hyderabad-relevant GCC/product/deep-tech employers.
- Resume workspace visual styling improved for the master resume, editor, tailoring and history workflow.
- Job detail freshness metadata is compacted into a single line on desktop.

## v7.0.4 changes
- Automatic scanner no longer starts immediately on every backend restart; the first scheduled scan runs after the configured interval, while Run Scan Now remains available.
- Career-site generic crawling is capped to 12 job-detail candidates per company instead of 80, and company collection concurrency is increased to 24 workers to prevent the scanner from appearing permanently busy.
- OpenAI analysis is now on-demand and never blocks a career-site scan; this prevents one AI request per newly discovered job from keeping the scanner running.
- Added an on-demand `/jobs/{job_id}/analyze` endpoint and a cleaner AI analysis panel on job details.
- Dashboard redesigned into a cleaner overview → match quality → live feed hierarchy, with four overview cards, four clickable match bands, simplified filters and a compact monitoring rail.
- Legacy invalid API-key analysis responses are shown as a friendly configuration message rather than raw provider JSON.

## v7.0.5
- Fixed the Next.js syntax error in the Job Detail AI analysis panel that prevented the frontend production build.
- Kept AI analysis optional/on-demand and preserved deterministic Job Match scoring when OpenAI is unavailable.
