# Run Voice Labs locally (team guide)

This page takes you from nothing to talking with a voice agent in your browser. Everything
runs on your own machine. Expect 20–30 minutes the first time.

```text
Browser (localhost:3000) ──► Platform API (localhost:8000) ──► PostgreSQL (5432)
        │                            │
        │ microphone (WebRTC)        │ starts a session
        ▼                            ▼
LiveKit (localhost:7880) ◄──── Runtime (localhost:8001)
                                 Deepgram STT → OpenAI LLM → Cartesia TTS
```

| What | Port | Started by |
| --- | --- | --- |
| PostgreSQL, Valkey, LiveKit | 5432, 6379, 7880 | `docker compose` (step 3) |
| Platform API | 8000 | terminal 1 (step 5) |
| Runtime API | 8001 | terminal 2 (step 6) |
| Web app | 3000 | terminal 3 (step 7) |
| Docs preview (optional) | 8080 | see [Development](development.md#documentation-site) |

## 1. Install the tools

| Tool | Version | Check |
| --- | --- | --- |
| Git | any | `git --version` |
| Docker | Docker Desktop, or [Colima](https://github.com/abiosoft/colima) on macOS | `docker ps` |
| Python | **3.11+** | `python3.11 --version` |
| Node.js | 20+ (we use 24) | `node -v` |
| `jq`, `curl` | any | used in the smoke test |

### Open a terminal

Every command on this page is typed into a **terminal**:

- **macOS:** press `⌘ Space`, type **Terminal**, press Enter.
- **Windows:** install [WSL 2](https://learn.microsoft.com/windows/wsl/install) (Ubuntu), then
  open **Ubuntu** from the Start menu and follow the Linux notes. Use Docker Desktop with the
  WSL 2 backend.
- **Linux:** open your terminal app.

Copy a command block, paste it into the terminal, and press Enter. Lines starting with `#`
are comments.

### Install the tools (macOS)

1. Install [Homebrew](https://brew.sh), the macOS package manager. Paste this, press Enter,
   and follow the prompts. It asks for your Mac password, and the cursor doesn't move while
   you type it:

    ```bash
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    ```

    When it finishes, run the two `eval ...` lines it prints under **Next steps**, so
    `brew` works in new terminals.

2. Install everything else:

    ```bash
    brew install git gh python@3.11 node jq colima docker docker-compose
    mkdir -p ~/.docker/cli-plugins
    ln -sfn "$(brew --prefix)/opt/docker-compose/bin/docker-compose" ~/.docker/cli-plugins/docker-compose
    colima start          # starts Docker; skip if you use Docker Desktop instead
    ```

3. Check that each tool works. Every command should print a version or a table, not an error:

    ```bash
    git --version; gh --version; python3.11 --version; node -v; docker ps
    ```

On Linux or WSL, install the same tools with your package manager. Use Docker Engine with
the Compose plugin, and get Python 3.11+ and Node 20+.

`uv` is optional. Plain `venv` works, as shown below.

## 2. Get the code

### 2.1 Tell Git who you are (once per computer)

```bash
git config --global user.name "Your Name"
git config --global user.email "you@example.com"     # the email on your GitHub account
```

### 2.2 Clone the three repositories

"Cloning" downloads a copy of a repository to your computer. The three repositories must sit
**side by side** in one folder:

```bash
mkdir -p ~/voice-labs && cd ~/voice-labs
git clone https://github.com/N2-Voice-Labs/stack.voice-labs.git
git clone https://github.com/N2-Voice-Labs/backend.voice-labs.git
git clone https://github.com/N2-Voice-Labs/frontend.voice-labs.git
ls      # should list: backend.voice-labs  frontend.voice-labs  stack.voice-labs
```

You should now have:

```text
voice-labs/                # in your home folder: ~/voice-labs
├── stack.voice-labs/      # Docker Compose, shared .env, these docs
├── backend.voice-labs/    # platform/ (API), runtime/ (voice pipeline), evals/
└── frontend.voice-labs/   # Next.js web app
```

**If `git clone` asks for a username and password:** `backend` and `frontend` are private,
and GitHub doesn't accept your account password in the terminal. Press `Ctrl+C`, log in
once with the GitHub CLI, then run the clone commands again:

```bash
gh auth login
```

Answer the questions like this:

- *Where do you use GitHub?* → **GitHub.com**
- *Preferred protocol?* → **HTTPS**
- *Authenticate Git with your GitHub credentials?* → **Yes**
- *How would you like to authenticate?* → **Login with a web browser**. Copy the one-time
  code it shows, press Enter, and paste the code on the page that opens.

`Repository not found` means your GitHub account doesn't have access yet. Ask the team lead.

### 2.3 Work on your own branch, never on `main`

`main` is the shared, working version of the project. **Never edit, commit or push on
`main`.** Create your own branch in each repository right after cloning. A branch is your
private copy of the code, so nothing you try there can break anyone else's work.

Pick a short branch name with your name in it, e.g. `aida/testing`, and run:

```bash
cd ~/voice-labs
for repo in stack.voice-labs backend.voice-labs frontend.voice-labs; do
  git -C "$repo" switch -c yourname/testing
done
```

`switch -c` creates the branch and moves you onto it, so it's only needed once. (Older
guides write `git checkout -b yourname/testing`, which does the same.)

Check which branch you're on at any time:

```bash
git -C ~/voice-labs/backend.voice-labs branch --show-current     # should print yourname/testing
```

Two settings make accidents unlikely. Run them once per computer:

```bash
git config --global push.default current    # "git push" only ever pushes the branch you're on
git config --global pull.rebase false       # "git pull" merges, which is easier to undo
```

**Just testing?** You don't need to commit or push anything. Run the project and try it out.
`git status` shows any files you changed. To throw away all your local edits in a repository,
run `git -C <repo> restore .`.

**Want to share a change?** Commit on your branch, push the branch, and open a Pull Request
so a teammate reviews it before it reaches `main`:

```bash
cd ~/voice-labs/backend.voice-labs        # the repository you changed
git switch yourname/testing               # make sure you're NOT on main
git add -A
git commit -m "Describe what you changed"
git push -u origin yourname/testing
gh pr create --fill                       # opens a Pull Request; a teammate reviews and merges it
```

> **Team lead:** protect `main` on GitHub in each repository: **Settings → Branches → Add
> branch ruleset** (or *Add rule*) for `main`, with **Require a pull request before merging**
> and **Block force pushes** turned on. GitHub then rejects direct pushes to `main` even if
> someone makes a mistake.

### 2.4 Get the latest code later

Teammates' changes land on `main`. To bring the latest `main` into your branch, in all
three repositories:

```bash
cd ~/voice-labs
for repo in stack.voice-labs backend.voice-labs frontend.voice-labs; do
  git -C "$repo" fetch origin
  git -C "$repo" merge origin/main
done
```

This updates your branch without ever switching to `main`. After pulling backend changes,
re-run the database migration (step 5). If dependencies changed, re-run the install in
step 4.

> If the merge stops because you edited the same files, run `git -C <repo> merge --abort`
> to go back to how it was. If you were only experimenting, `git -C <repo> stash` puts your
> edits aside, `merge origin/main` will then work, and `git -C <repo> stash pop` brings your
> edits back.

## 3. Create the shared `.env` and start infrastructure

All three apps read **one** file: `stack.voice-labs/.env`.

```bash
cd ~/voice-labs/stack.voice-labs
cp .env.example .env
docker compose up -d
docker compose ps        # postgres and valkey should say "healthy"
```

Now open `.env` and fill in the four provider values at the bottom. Get them from the team
lead **privately**, or create your own (all three have free trial credits):

```bash
DEEPGRAM_API_KEY=        # https://console.deepgram.com → API Keys        (speech-to-text)
OPENAI_API_KEY=          # https://platform.openai.com/api-keys            (the agent's brain; needs credits)
CARTESIA_API_KEY=        # https://play.cartesia.ai → API Keys             (text-to-speech)
CARTESIA_VOICE_ID=       # any voice ID from the Cartesia voice library
```

The rest of the file works as-is for local development. The full template:

```bash
POSTGRES_DB=voice_labs
POSTGRES_USER=voice_labs
POSTGRES_PASSWORD=local-only
POSTGRES_PORT=5432
VALKEY_PORT=6379
LIVEKIT_PORT=7880

PLATFORM_DATABASE_URL=postgresql+psycopg://voice_labs:local-only@localhost:5432/voice_labs
PLATFORM_RUNTIME_TOKEN=local-runtime-token-change-me   # must equal RUNTIME_PLATFORM_TOKEN
RUNTIME_PLATFORM_TOKEN=local-runtime-token-change-me
PLATFORM_API_URL=http://localhost:8000
RUNTIME_API_URL=http://localhost:8001
RUNTIME_PLATFORM_URL=http://localhost:8000
NEXT_PUBLIC_PLATFORM_URL=http://localhost:8000
NEXT_PUBLIC_SITE_URL=http://localhost:3000
NEXT_PUBLIC_CAPABILITIES=voicePreview,liveLatency,toolExecution,knowledgeSearch
PLATFORM_WEB_ORIGIN=http://localhost:3000
PLATFORM_ALLOW_PRIVATE_NETWORK=0

LIVEKIT_URL=ws://localhost:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=secret

DEEPGRAM_API_KEY=
OPENAI_API_KEY=
CARTESIA_API_KEY=
CARTESIA_VOICE_ID=
```

> **Never commit `.env` or paste keys into docs, chats or issues.** `.env` is gitignored.
> If a key leaks, rotate it in the provider's dashboard.

`NEXT_PUBLIC_CAPABILITIES` switches on web-app features whose backend support has landed
(voice preview, live latency, tools and knowledge during calls). Leave a feature out to show
it as "Coming soon".

## 4. Create the Python environment (once)

```bash
cd ~/voice-labs
python3.11 -m venv ~/.venvs/voice-labs
~/.venvs/voice-labs/bin/pip install -e "backend.voice-labs/platform[test]" -e "backend.voice-labs/runtime[voice,test]"
cd backend.voice-labs && git checkout -- platform/src/platform_voice_labs.egg-info/ 2>/dev/null; cd ..
```

The `git checkout` line undoes a file that `pip install -e` rewrites. The first install
downloads Pipecat and the voice models' dependencies and takes a few minutes.

Every terminal below starts with the same two lines, which load `.env` and stop Python from
rewriting tracked cache files:

```bash
set -a; source ~/voice-labs/stack.voice-labs/.env; set +a
export PYTHONDONTWRITEBYTECODE=1
```

## 5. Terminal 1 — Platform API

```bash
set -a; source ~/voice-labs/stack.voice-labs/.env; set +a; export PYTHONDONTWRITEBYTECODE=1
cd ~/voice-labs/backend.voice-labs/platform
~/.venvs/voice-labs/bin/python -m alembic upgrade head     # create/update database tables
~/.venvs/voice-labs/bin/python -m uvicorn src.platform.main:app --reload --port 8000
```

Check: <http://localhost:8000/health> returns `{"status":"ok"}`. Interactive API docs are
at <http://localhost:8000/docs>.

## 6. Terminal 2 — Runtime (the voice pipeline)

```bash
set -a; source ~/voice-labs/stack.voice-labs/.env; set +a; export PYTHONDONTWRITEBYTECODE=1
cd ~/voice-labs/backend.voice-labs/runtime
~/.venvs/voice-labs/bin/python -m uvicorn src.runtime.api:app --reload --port 8001
```

Check: <http://localhost:8001/health> returns `{"status":"ok"}`.

## 7. Terminal 3 — Web app

```bash
set -a; source ~/voice-labs/stack.voice-labs/.env; set +a
cd ~/voice-labs/frontend.voice-labs
npm ci
npm run dev
```

Open <http://localhost:3000>. Restart `npm run dev` after changing any `NEXT_PUBLIC_*` value.

## 8. Create a test agent

Use the web app (**Agents → New agent**, or start from a template), or one command:

```bash
curl -s -X POST localhost:8000/agent-templates/receptionist/agents \
  -H 'content-type: application/json' -d '{"name":"Receptionist Demo"}' | jq '{id, name}'
```

An agent with **no voice profile** speaks with `CARTESIA_VOICE_ID` from `.env`. If you
assign a voice profile, its provider voice ID must be a real Cartesia voice. Otherwise the
agent connects but stays silent.

## 9. Talk to it

1. Use **Chrome**. Safari is not supported for this flow.
2. **macOS only:** System Settings → Privacy & Security → **Microphone** → enable Chrome, then
   quit and reopen Chrome. Without this, macOS sends silence and the agent never hears you.
3. Open the agent → **Talk to this agent** → **Start conversation** → allow the microphone.
4. Say, in English, Russian or both: *"Hello, I'd like to book an appointment for tomorrow."*

You should hear an answer within about 2 seconds. Afterwards, open **Conversations** to
see the transcript with language tags, or check the numbers:

```bash
curl -s "localhost:8000/analytics/summary" | jq '.latency'
```

## 10. Smoke test without a browser (optional)

Hear a voice without making a call. This confirms your Cartesia key and voice. Run it in a
terminal where you loaded `.env`, so `$CARTESIA_VOICE_ID` is set:

```bash
TTS=$(curl -s localhost:8000/providers -H 'content-type: application/json' \
  -d '{"kind":"tts","provider":"cartesia"}' | jq -r .id)
VOICE=$(curl -s localhost:8000/voices -H 'content-type: application/json' \
  -d "{\"name\":\"Team voice\",\"tts_provider_id\":\"$TTS\",\"provider_voice_id\":\"$CARTESIA_VOICE_ID\"}" | jq -r .id)
curl -s localhost:8000/voices/$VOICE/preview -H 'content-type: application/json' \
  -d '{"text":"Hello! Привет! This is Voice Labs."}' -o preview.wav && afplay preview.wav   # Linux: aplay
```

For a full API walkthrough that needs no keys, see [Quickstart: API tour](quickstart-api.md).

## 11. Run the tests

```bash
export PYTHONDONTWRITEBYTECODE=1
cd ~/voice-labs/backend.voice-labs/platform && ~/.venvs/voice-labs/bin/python -m pytest -q
cd ../runtime && ~/.venvs/voice-labs/bin/python -m pytest -q
cd ~/voice-labs/frontend.voice-labs && npm test && npm run typecheck
```

Tests use SQLite and fake providers. They never spend provider credits. More options
(PostgreSQL, LiveKit, acceptance tests) are in [Development](development.md).

## 12. Stop everything

`Ctrl+C` in terminals 1–3, then:

```bash
cd ~/voice-labs/stack.voice-labs && docker compose down      # add -v to also wipe the database
colima stop                                                   # if you use Colima
```

## When something is wrong

| Symptom | Most likely fix |
| --- | --- |
| "Can't reach the platform" / "Failed to fetch" | Platform (terminal 1) isn't running, or your browser's origin isn't in `PLATFORM_WEB_ORIGIN`. Restart Platform after editing `.env` |
| Session fails with `runtime_unavailable` | Runtime (terminal 2) isn't running |
| Call connects, agent never answers | Runtime log shows `429 insufficient_quota` → add OpenAI credits. No speech detected at all → check the macOS microphone permission for Chrome |
| Agent answers with silence | The agent's voice ID isn't a real Cartesia voice |
| `Cannot connect to the Docker daemon` | Start Docker Desktop, or run `colima start` |
| Port already in use | `lsof -nP -iTCP:8000 -sTCP:LISTEN` to find the old process |
| The deployed (Cloudflare) site can't reach your local backend | Expected: it renders on Cloudflare's servers. Use <http://localhost:3000> |

More detail: [Troubleshooting](troubleshooting.md).
