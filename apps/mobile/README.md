# Scene.ai on a phone (`/m/`)

The studio's site for phones. Open the studio on a phone and you land here; tablets and computers get the full
studio. It is a website, not an app: nothing to install. Added to the home screen (browser menu, *Add to Home
screen*), it opens full screen like an app.

| Screen | What it does |
|---|---|
| **Home** | A greeting with your credits; a live "rendering now" card (opens **Activity**: every job, retry, cancel); plans the agent is waiting on; quick Video / Image / Music; your latest projects and work. The avatar opens **Account**. |
| **Projects** | Every project, yours and shared ones; search (finds modules too), Recent / A–Z. A project shows its stats, members and modules. |
| **Module** | In place of the infinite canvas: the latest cut, **Play Story** (all shots back to back), **Story** (shots in order, each with its takes; touch and hold one to make it the best take), **Boards** (Characters, Locations, Props, Styles, Outputs), **Cast** (NeuralCore) and **All**. **Ask Agent** opens the module's agent chat. |
| **Agent chat** | The same conversations as the studio's agent tabs, both ways. Plans show each step and the price; **Approve** queues them (keep the page open until every step is in line), with live status as they finish. |
| **Create** | A video, picture or song from a prompt, or from a photo or clip on the phone (reference slots); see the price, Generate. |
| **Library** | Everything you made: filters, search, endless scrolling; **+** adds a photo, video or file from the phone. |
| **Skills** | What the agent knows how to do, with each recipe and its `/command`. |
| **Player** | Full screen; pinch to zoom pictures, swipe between items, steps through a story. Star, Share (the phone's share sheet, or a link anyone can open), Download, Remix, Details. |
| **Account** | Credits and what they went on, Ask for More, appearance (Automatic / Dark / Light), **Open the Full Studio**, sign out. |

## How it works

- **Built with** Expo (React Native for the web) + Expo Router + TypeScript, TanStack Query, Reanimated. Screens in
  `src/app/`, the rest in `src/` (`components/`, `hooks/`, `lib/`, `theme/`); the API client (one file per backend
  area), its types and formatting are in `packages/shared`.
- **Served by the studio.** `npm run build` writes the site to `apps/mobile/dist/`; the studio serves it at `/m/`
  (`backend/scene/phone_site.py`, setting `mobile_site_dir`). `scripts/start.bat` builds it the first time.
- **Under the studio's Content-Security-Policy** (no inline script, no inline style). The page's reset is a file
  (`public/reset.css`), and the entry (`index.ts`) first runs `src/lib/cspStyles.ts`: the `<style>` elements React
  Native Web, Reanimated, expo-font and expo-image make are held out of the page and their CSS goes into adopted
  constructed style sheets, which the policy allows. A library that writes styles some other way would show up in
  `apps/web/tests/e2e/phone.spec.ts` (a CSP violation, or the page drawn unstyled).
- **Phones are sent here.** A phone (not a tablet) opening one of the studio's pages is redirected to the same place on
  `/m/` (a project's or module's link too). `/?desktop=1` (Account › Open the Full Studio) keeps that phone on the full
  studio until it opens `/m/` again.
- **Signed in by the studio's own session** (cookie): signed in on the studio, signed in here, and back. Live updates
  come over the studio's `/api/events` socket.
- **The backend** for it: `backend/scene/api/mobile.py` (lighter lists, modules, retry, credits, waiting plans) and
  `api/shares.py` (share links), with tests in `backend/tests/test_mobile_api.py`.

## Working on it

The site is one workspace of the repository's npm workspaces (`apps/*`, `packages/*`): `npm install` runs once at the
repository root. The API client, its types and the formatting helpers are in `packages/shared` (`@scene/shared/...`),
shared with the desktop studio (`apps/web`).

```
npm install          # first time, at the repository root
cd apps/mobile
npm run build        # then reload /m/ on the studio (the studio must be running)
npm test             # the site's tests (Jest, in __tests__/)
npm run typecheck    # TypeScript
```

After adding or moving a screen, run `bash scripts/route-types.sh` before the type check (Expo's typed routes go stale).

To look at it on a computer, open `http://localhost:8081/m/` and switch the browser's dev tools to a phone size.

**Releasing a change:** raise `version` in `app.json` and add the release at the top of `src/lib/whatsNew.ts` (people
see it once, after the update; a test checks the two agree), then `npm run build`.

## Design

After Apple's Human Interface Guidelines, in the studio's colours: Apple's layered greys, paper white for the main
action, the blue of the logo's frame as the one tint; Inter (close to SF Pro) in the HIG text styles; large titles that
fold into a frosted bar; calm fades and eased presses; inset grouped lists, segmented controls, switches, sheets. Text
grows with the phone's text size, every control has a label for screen readers, and both themes keep AA contrast.
The icons are drawn from the studio's logo by `scripts/make-icon.py`.
