# Contributing to SCRIBE

Thanks for your interest in contributing! SCRIBE is a personal open-source project, but contributions are very welcome.

## Ways to contribute

### 🐛 Report a bug

Open an issue at [github.com/nocomp/scribe/issues](https://github.com/nocomp/scribe/issues) with:
- **What you did** (steps to reproduce)
- **What you expected**
- **What happened** (error messages, screenshots if relevant)
- **Your environment** (OS, Python version, browser)

### 💡 Suggest a feature

Open an issue tagged `enhancement`. Be specific about the use case — SCRIBE is built for real hospital crisis teams, so concrete needs are easier to evaluate than abstract feature requests.

### 🌍 Translate

The internationalization system covers all 24 EU languages with native UI for FR/EN/IT/DE/ES (619 keys each) and ~111 essential keys for the 19 others (the rest falls back to English).

**To complete a language:**

1. Open `app/lang/<code>.json` (where `<code>` is e.g. `pl`, `nl`, `el`...)
2. Find keys that still match the English version — those are the fallback ones
3. Translate them natively
4. Submit a PR with the diff

Native speakers and healthcare professionals are especially welcome — context matters in medical/crisis terminology.

### 🔧 Code contribution

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Follow existing patterns — vanilla JS, FastAPI routes, SQLAlchemy models
4. Test your changes locally
5. Submit a PR

## Code conventions

- **Python**: PEP 8, type hints where helpful
- **JavaScript**: vanilla, no framework, no build step
- **HTML**: semantic, accessible (ARIA labels)
- **CSS**: DSFR variables (`--bleu-france`, `--rouge-marianne`, etc.) — see existing styles
- **i18n**: any new UI string MUST be in `app/lang/*.json`, referenced via `data-i18n` attribute or `t('key')` in JS
- **Security**: no hardcoded secrets, no patient data in logs, no telemetry

## Code of conduct

Be respectful. SCRIBE is used by real people coordinating real crises. The bar for tone is high — disagreements are fine, condescension is not.

## License

By contributing, you agree your contributions will be licensed under the AGPL-3.0.
