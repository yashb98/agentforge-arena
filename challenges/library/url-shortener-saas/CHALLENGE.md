# Challenge: URL Shortener SaaS

## Difficulty: Medium | Category: SaaS App | Time: 90 minutes

## Brief

Build a production-ready URL shortener service with analytics. Users should be able
to create shortened URLs, track click analytics, and manage their links.

## Requirements

### Functional (Must Have)
1. **Create Short URL** — POST endpoint that accepts a long URL and returns a short URL
2. **Redirect** — GET /{short_code} redirects to the original URL with 301 status
3. **Analytics** — Track clicks per short URL (count, timestamp, referrer, country)
4. **List URLs** — GET endpoint to list all URLs created by a user
5. **Delete URL** — DELETE endpoint to remove a short URL
6. **Custom Slugs** — Allow users to specify custom short codes (if available)

### Non-Functional (Should Have)
7. **Rate Limiting** — Max 100 URL creations per hour per user
8. **Expiration** — URLs can have optional expiration dates
9. **QR Code** — Generate QR code for any short URL
10. **Bulk Create** — Create multiple short URLs in a single request

### Bonus (Nice to Have)
11. **Dashboard UI** — Simple web UI showing URL analytics
12. **Password Protection** — Optional password on short URLs
13. **API Key Auth** — Basic authentication via API keys

## Tech Constraints
- Backend: Python (FastAPI preferred) or Node.js (Express/Fastify)
- Database: PostgreSQL or SQLite
- Must include a Dockerfile
- Must include a README with setup instructions

## Hidden Test Suite Hints
- The judge will test URL creation with 1000+ URLs
- The judge will test redirect latency (target: <50ms p99)
- The judge will test concurrent redirects (100 simultaneous)
- The judge will test custom slug collision handling
- The judge will test URL expiration behavior
- The judge will test invalid URL rejection

## Scoring Weights
| Dimension | Weight |
|-----------|--------|
| Functionality | 30% |
| Code Quality | 20% |
| Test Coverage | 15% |
| UX/Design | 15% |
| Architecture | 10% |
| Innovation | 10% |
