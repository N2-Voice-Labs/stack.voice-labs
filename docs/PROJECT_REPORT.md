# Project report: sections 6 to 9

The latency figures in section 7 come from a single test call. We will replace them with
benchmark results once the evaluation dataset is ready.

## 6. Technical approach, system design, and task breakdown

### 6.1 Technical approach

Voice Labs is a platform for building real-time voice agents that speak more than one
language. We focus on English–Russian code-switching: callers who move between the two
languages in the same conversation, or in the same sentence.

We did not build speech infrastructure ourselves. The system uses existing open-source
components (FastAPI, Pipecat, LiveKit, Silero VAD, Smart Turn and PostgreSQL) and adds
its own platform layer on top. That layer talks to speech-to-text (STT), language model
(LLM) and text-to-speech (TTS) providers through common interfaces, so we can swap and
benchmark providers without changing the business logic.

### 6.2 System architecture

The system has two parts. A control plane stores everything that has to persist, and a
real-time media plane handles the live audio.

| Component | Technology | Responsibility |
| --- | --- | --- |
| Web client | Next.js on Cloudflare Workers | Agent setup, voice playground, conversation history |
| Platform API | FastAPI, SQLAlchemy, Alembic, PostgreSQL | Stores agents, voices, deployments, conversations, outcomes and analytics. It never handles audio |
| Runtime | Pipecat and LiveKit | Runs each live call: voice activity detection, turn detection, STT, LLM with tools, TTS, and interruptions |
| Media transport | LiveKit (WebRTC now, SIP planned) | Carries audio between the caller and the Runtime |
| Providers | Deepgram (STT), OpenAI (LLM), Cartesia (TTS) | Replaceable through the provider interfaces |

A call works like this. The browser asks the Platform for a session. The Platform checks
the agent and its voice, issues a short-lived LiveKit token, and hands the session to the
Runtime. The Runtime joins the LiveKit room and processes the caller's speech. As the call
goes on, it sends events back to the Platform: transcripts, latency measurements, tool
calls and outcomes. Each event carries a version number and a service token, and the
Platform stores each event only once, even if the Runtime retries.

```text
Browser mic --WebRTC--> LiveKit <--> Runtime (Pipecat)
                                       VAD, Smart Turn, STT, LLM + tools, TTS
     ^                                   |
     | session and token                 | authenticated events
     +---------- Platform API <----------+
                     |
                 PostgreSQL
```

The data model follows the same order: a voice belongs to an agent, an agent has
deployments, and each call becomes a conversation. Voices come from a provider library,
from a cloned recording (only with recorded consent), or from a text description, and
several agents can share one voice. An agent adds instructions, tools and knowledge
documents. A deployment says where the agent answers: the web, a phone line over SIP, or
an API. A conversation stores the transcript with the languages detected in each message,
plus the call's outcome and any handoff to a person. [Concepts](concepts.md) and
[Contracts](contracts.md) describe each object in detail.

### 6.3 Task breakdown

| Milestone | Scope | Status |
| --- | --- | --- |
| M0–M1 | Workspace, API contracts, local infrastructure with Docker Compose, and the Platform (agents, providers, sessions, event ingestion) | Done |
| M2–M3 | Runtime: LiveKit transport, Pipecat pipeline, voice activity and turn detection, STT/LLM/TTS adapters, interruptions | Done, tested with stub and real providers |
| M5 | Latency measurement for STT, LLM time to first token, TTS, and the whole turn | Done |
| M8 | Voice Studio: voice library, cloning and design records, deployments, campaigns, tools, knowledge, templates, outcomes, analytics ([plan](BACKEND_STUDIO_PLAN.md)) | Backend done |
| M9 | Live features: voice preview, latency events, knowledge search, tool use during calls ([plan](BACKEND_LIVE_PLAN.md)) | Done. SIP dialing, live transfer and provider-side cloning are still open |
| Next | User authentication, cloud deployment, evaluation dataset and benchmarks | Planned |

## 7. Testing and AI output evaluation

### 7.1 Software testing

The Platform has about 120 automated tests and the Runtime about 100, covering the API,
the pipeline, events, tools and latency reporting. We ran the database migrations up, down
and up again on PostgreSQL 16, and ran a separate concurrency test there.

Cross-service acceptance tests start the Platform and Runtime together with LiveKit. They
check the session handoff, send synthetic audio, and confirm that events are stored and
that interruptions and disconnects are handled. Playwright tests drive a real browser
through creating an agent, starting a voice session, interrupting the agent and viewing
the conversation.

We also tested once with real providers. We played a recorded spoken request into a live
session; the agent transcribed it, generated a relevant answer and spoke the answer back.

### 7.2 AI output evaluation

| Dimension | Metric | Method |
| --- | --- | --- |
| Speech recognition | Word error rate (WER), measured separately for English, Russian and mixed speech | Manually transcribed reference dataset |
| Code-switching | WER on mixed speech, and whether words stay in the language the speaker used rather than being translated or dropped | English to Russian, Russian to English, and several switches in one sentence |
| Domain vocabulary | Recall of key terms such as visa and appointment vocabulary | Metric implemented in the `evals` package |
| Latency | STT time, LLM time to first token, TTS time to first audio, and end of turn to first audio | The Runtime reports these on every call; the analytics API returns p50 and p95 |
| Conversation quality | Task success, relevance, and whether answers stay within the knowledge documents | Scripted scenarios: booking, mid-sentence corrections, mixed-language questions |
| Turn-taking | How often the system ends a turn too early, and whether interruptions stop the agent | Natural pauses and barge-in scenarios |

We aim for a median delay under about 2 seconds from the end of the caller's turn to the
agent's first audio. For recognition, the target is a 15 to 20 percent relative reduction
in WER on mixed speech compared with the baseline, without losing accuracy on
single-language speech. The [Test Plan](TEST_PLAN.md) has the full procedure.

One test call gave these preliminary numbers:

| Stage | Latency |
| --- | --- |
| STT, time to first result | about 445 ms |
| LLM, time to first token | about 340 ms |
| End of turn to first agent audio | about 1.65 s, inside the 2 s target |

Running the full benchmark on the dataset is the next step.

## 8. Prototype development and demo plan

### 8.1 Current prototype

The prototype runs end to end on a local machine. A user talks to a configured agent in
the browser; the system recognizes the speech, generates a reply with the LLM and speaks
it. The user can interrupt the agent mid-answer. The system saves each transcript with the
detected languages, records the call's outcome, measures latency and can play a voice
preview. Any team member can start the whole stack by following the
[local setup guide](run-locally.md).

### 8.2 Demo scenario (about five minutes)

1. Pick a voice from the library and play a preview ("Hello! Привет!").
2. Create an agent from the receptionist template and give it the voice, its tools and a
   knowledge document.
3. Start a call and speak in mixed English and Russian: "Мне нужно book an appointment на
   завтра". The agent answers.
4. Interrupt the agent while it is talking. It stops and listens.
5. Ask a question the knowledge document answers. The agent looks it up and records the
   outcome as "booked".
6. Open the conversation: the transcript shows RU and EN language tags for each message,
   with the outcome, summary and per-stage latency.

### 8.3 Remaining work before the final demo

Before the final demo we need user authentication, a cloud deployment on Cloudflare
Containers and LiveKit Cloud so the demo works from any device, and the benchmark results.

## 9. Data protection, responsible AI, and operational feasibility

### 9.1 Data protection

Provider API keys stay in environment configuration. The database never stores them and
the API never returns them, and the Platform rejects any configuration that contains a key
whose name looks like a secret.

The services authenticate each other. The Runtime signs its events to the Platform with a
shared service token, and each browser gets a short-lived LiveKit token that only opens its
own room.

The Platform does not store raw audio. A voice sample is stored as a link to where the
recording lives, not as a file in the database, and private recordings stay out of the
repositories.

Transcripts can contain personal information. We have not built user authentication or
authorization yet, and the system cannot go public without them. We also plan a retention
policy and deletion on request.

### 9.2 Responsible AI

The Platform refuses to create a cloned voice without a consent record. The record names
the speaker, includes their statement, says whether it is the speaker's own voice or one
they authorized, and stores the time it was given.

The agent templates tell the agent to say it is an AI assistant when a caller asks. Agents
can hand a call to a person, and the system records every handoff.

When an agent answers from knowledge documents, it draws on documents the team approved,
which lowers the risk of invented answers in areas such as immigration. The agent gives
information; it does not make legal decisions.

We measure recognition accuracy separately for English, Russian and mixed speech, so a
weakness on mixed speech shows up in the results instead of being averaged away.

### 9.3 Operational feasibility

| Item | Approach | Estimated cost |
| --- | --- | --- |
| LLM | OpenAI `gpt-4.1` or `gpt-4.1-mini` | About $0.0003 to $0.0015 per turn of conversation |
| STT and TTS | Deepgram and Cartesia, billed by usage; trial credits cover development | Low at prototype scale |
| Hosting | Cloudflare Workers for the frontend, Cloudflare Containers for the backend, LiveKit Cloud and managed PostgreSQL on free tiers | About $5 to $10 a month at prototype scale |
| Maintenance | Provider interfaces, versioned event contracts, database migrations, automated tests and a documentation site | A new team member can run the project from the local setup guide |

To handle more calls we can add Runtime instances. Each instance holds only the calls it
is serving, and all lasting state lives in PostgreSQL. We can change STT, LLM or TTS
providers for cost, quality or speed without changing the platform code.
