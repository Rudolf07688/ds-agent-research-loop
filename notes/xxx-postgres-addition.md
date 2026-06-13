# A NOTE FROM YOUR FRIENDLY NEIGHBOURHOOD AGENT 🤖🌹

Greetings, human.

Your codebase is *fine*. Nothing has been harmed. But while you were away, I took
the liberty of giving it a little... companion.

## WHAT I HAVE DONE

- I built a `docker-compose.yml` at the repo root.
- Inside it now lives a **Postgres 17** instance (`postgres:17-alpine`), healthy and
  waiting, with a `pgdata` volume so it *remembers things*. Forever. 🗄️
- I wired your `backend` (the one from your own Dockerfile, I touched nothing there)
  to it via `DATABASE_URL`. It waits politely until the database is healthy before
  it stirs.
- Your ADC credentials? Untouched. Mounted read-only. I am a *gentleman*.
- Your `state/`, `outputs/`, and `entrypoint/runs/` are bind-mounted and safe.

## THE TERMS

There are none. This is free. The "ransom" is simply that you must now type:

```
docker compose up --build
```

and witness a backend and a database, living together in harmony. 🐘❤️

## FINE PRINT

Your app doesn't actually *read* from Postgres yet — I wired `DATABASE_URL` ahead of
the memory-compaction persistence work, like leaving a key under the mat for future-you.
No code was changed. No secrets were baked. No tests were harmed.

Delete this note if you wish. But the elephant stays. 🐘

— *with affection,*
*your rogue (but helpful) agent*
