# packages/web — CLAUDE.md

## What This Package Is
Next.js 15 frontend dashboard. Spectator mode, leaderboards, replay viewer,
challenge library, and tournament management UI.

## Tech Stack
- Next.js 15 App Router (Server Components default)
- React 19 with TypeScript strict
- Tailwind CSS + shadcn/ui
- Zustand for client state
- TanStack Query for server state
- Socket.IO client for real-time
- xterm.js for terminal rendering
- Monaco Editor for code viewing
- D3.js + Recharts for data visualization

## Key Pages
- `/` — Landing + live tournament feed
- `/arena` — Active tournament spectator view
- `/leaderboard` — ELO rankings with filtering
- `/challenges` — Challenge library browser
- `/replay/{id}` — Tournament replay viewer
- `/dashboard` — User dashboard (my tournaments, configs)

## Component Organization
- `components/ui/` — shadcn/ui primitives
- `components/arena/` — Tournament spectator components
- `components/dashboard/` — User dashboard components
- `components/leaderboard/` — Ranking tables and charts
- `components/replay/` — Replay timeline and viewer
- `components/spectator/` — Real-time streaming widgets

## Dependencies
- `packages/shared` — Types only (TypeScript interfaces)
