# Evaluation

The evaluation set, metrics and runner live in the `evals` project of the backend
workspace (`backend.voice-labs/evals`). This page describes dataset v1, how to run it, and
the first small results. See the [Test Plan](TEST_PLAN.md) for the longer-term goals and
[Data Sources](DATA_SOURCES.md) for how real recordings will be collected.

!!! warning "Read the numbers with care"
    The first results use **synthetic voices (macOS `say`)** and a **tiny sample (3 items
    per category)**. They prove that the pipeline works and show where to look; they are
    not an accuracy claim about real speakers, phone lines or any provider. Clean synthetic
    speech is easy for modern STT, so STT error rates are close to zero.

## Dataset v1

`datasets/v1/manifest.jsonl` holds 140 items as committed text. No audio is stored in git;
audio is rendered locally from the manifest.

| Category | Items | Direction / content |
| --- | ---: | --- |
| `en-ko` | 20 | English to Korean: clinic, immigration, booking, support |
| `ko-en` | 20 | Korean to English |
| `ru-en` | 20 | Russian to English |
| `en-ru` | 20 | English to Russian |
| `mixed` | 20 | Russian with English words, e.g. "Мне нужно book an appointment на завтра"; 10 to English, 10 to Russian |
| `names-numbers` | 10 | dates, times, amounts, names, addresses |
| `domain-terms` | 10 | visas, residence permits, appointments, clinic and booking terms |
| `noisy-phone` | 10 | derived from other items: white noise at 5, 10 or 15 dB SNR and/or telephone band (300-3400 Hz, 8 kHz, mu-law) |
| `interruptions` | 10 | two utterances in one clip, the second one correcting the first |

Each item has `id`, `category`, `source_language`, `target_language`, `text` (what is
spoken), `reference_translation`, `key_terms` and a `tts_voice` hint. The spoken text has no
digits (numbers are words), so WER does not test number formatting. References were written
by hand and should get a native-speaker review before being used for decisions.

Real, consented recordings can be added later with the same manifest fields: place
`<id>.wav` (16 kHz mono) files in the audio folder and run the same commands. New material
should be a new dataset version so results stay comparable.

## Metrics

| Metric | Used for | Notes |
| --- | --- | --- |
| WER | STT for English and Russian | casefolded, punctuation ignored, `ё` equals `е` |
| Code-switch WER | mixed items | same alignment, errors charged to the script of the word that failed (Latin, Cyrillic, Hangul) |
| CER | STT for Korean | letters and digits only; spacing in Korean is too inconsistent for WER |
| chrF | translation quality | character n-grams 1-6, beta 2, scale 0-100; a similarity score, so a correct paraphrase is below 100 |
| Terminology recall | STT and translation | share of `key_terms` found; `a|b` lists acceptable alternatives |
| Latency p50 / p95 | STT, translation | seconds; time to first token and total for translation; end-to-end is STT plus translation |

## How to run

```bash
cd backend.voice-labs/evals
python -m pytest -q                               # unit tests, no network
python -m src.evals.generate_audio                # render audio locally (free, about 2 min)
set -a; source ../../stack.voice-labs/.env; set +a
python -m src.evals.run cascade --confirm-billable --limit 3
```

The runner has three modes: `stt` (Deepgram `nova-3`), `translate` (OpenAI on the gold text
with the same strict interpreter prompt as the runtime) and `cascade` (both, with per-stage
latency). It needs `--confirm-billable` because it calls paid APIs. Results (JSONL and a
Markdown summary with dataset version, models, date and machine) are written to
`~/.cache/voice-labs-evals/results/`. The full README is in `evals/README.md`.

## Live latency report

The `cascade` run above times single requests. The live report measures what a listener
actually experiences: it plays dataset audio into a real interpreter call and writes p50 and
p95 of the time to the first translated audio, per engine and latency mode (NS-01).

Start Platform and Runtime on free ports (for example `8300` and `8301`) with LiveKit and
provider keys loaded from `.env`, then run from `backend.voice-labs/evals`:

```bash
python -m src.evals.generate_audio                 # once: render the audio (free)
set -a; source ../../stack.voice-labs/.env; set +a  # only the servers need provider keys
python -m src.evals.live_latency --platform http://localhost:8300 \
    --engines realtime,cascaded --modes instant,balanced,accurate --pairs ko-en \
    --utterances 30 --confirm-billable --out report.md
```

Add `--dry-run` to see the planned cells and a rough cost estimate without any network call
(the default full run is 6 cells x 30 utterances, about 35 minutes and about $1 at list
prices). Without `--confirm-billable` the command only prints the plan and refuses. For each
engine x mode x direction x pair the runner creates an interpreter agent, joins the room as
a simulated participant that plays the utterances with pauses, waits for each translation,
ends the session and reads the Runtime's `utterance_timeline` statistics back from
`GET /analytics/summary`. It writes `report.md` and `report.json` (per-utterance times).

| Column | Meaning |
| --- | --- |
| Runtime T4-T0 | Platform p50 / p95 of `utterance_timeline` `value_ms`: speech start to first audible audio, and the number of events |
| Heard from speech start | measured by the runner on the received translation track; includes network |
| Heard after speech end | the same minus the end of the utterance audio; the cascaded target (p95 <= 1.5 s). Negative means the translation started before the speaker stopped |
| Missing | utterances with no translated audio within `--wait` seconds |
| p95 target | realtime p95 <= 1.2 s from speech start, cascaded p95 <= 1.5 s after speech end |
| NS-02, NS-03 | empty columns for interruption and audio-quality results |

Useful options: `--two-person` (cascaded only: a second participant listens on
`translation-for-<identity>`), `--directions one_way,auto` (`auto` needs languages in
Deepgram's code-switching set, so not Korean), `--record-dir DIR` (save the received
translation tracks as wav for the NS-03 audio checks), `--api-key` when the Platform has
`PLATFORM_API_KEYS` set. The dataset has 20 items per direction, so 30 utterances replay
some items. Results use synthetic voices over a local network; they show regressions and
the engine gap, not real-world latency.

### First smoke run (2026-10-21, KO → EN, one speaker)

Small runs to check the runner, not a benchmark (n is too small for p95).

| Engine | Mode | n | Runtime T4−T0 p50 / p95 | Heard after speech end p50 / p95 |
| --- | --- | --- | --- | --- |
| cascaded | balanced | 3 | 5.06 / 5.15 s | 1.86 / 1.88 s |
| realtime | instant | 5 | 3.24 / 4.04 s | 0.23 / 1.67 s |

Both are over target for Korean. Earlier Russian and English runs were faster (realtime about
0.8 s from speech start, cascaded 0.8–1.1 s after speech end), so Korean needs its own
investigation in the full NS-01 run. The realtime engine speaks in bursts with pauses of 2–3
s, so the runner waits 3 s of silence before the next utterance (`--settle`); with a shorter
wait, the tail of one translation was counted as the start of the next.

## First results

Run `20261018T131805Z-cascade` on 2026-10-18: `cascade` mode, 3 items per category (27
items, about 2.1 minutes of audio), Deepgram `nova-3` with the spoken language fixed
(`multi` for code-switched items), translation with `gpt-4.1-mini` and `gpt-4.1-nano`,
dataset v1 (manifest hash `aca79f587074`), run sequentially from an Apple-silicon Mac over
the home network. Latencies are in seconds, shown as p50 / p95.

### gpt-4.1-mini

| Category | Items | WER (non-ko) | CER (ko) | STT term recall | STT s | chrF | Term recall | TTFT s | Translate s | End-to-end s |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | --- | --- | --- |
| en-ko | 3 | 0.0% | - | 100.0% | 0.27 / 1.12 | 33.2 | 83.3% | 0.56 / 0.65 | 0.75 / 0.91 | 1.02 / 2.03 |
| ko-en | 3 | - | 0.0% | 83.3% | 1.24 / 1.50 | 70.7 | 100.0% | 0.54 / 0.58 | 0.73 / 0.76 | 2.00 / 2.16 |
| ru-en | 3 | 3.0% | - | 100.0% | 0.43 / 0.49 | 92.2 | 100.0% | 0.63 / 0.67 | 0.81 / 0.85 | 1.25 / 1.29 |
| en-ru | 3 | 0.0% | - | 100.0% | 0.34 / 0.59 | 76.9 | 66.7% | 0.54 / 0.58 | 0.68 / 0.71 | 1.01 / 1.31 |
| mixed | 3 | 7.9% | - | 66.7% | 0.34 / 0.36 | 86.0 | 100.0% | 0.59 / 0.89 | 0.75 / 1.05 | 1.11 / 1.31 |
| names-numbers | 3 | 0.0% | - | 100.0% | 0.27 / 0.32 | 80.0 | 100.0% | 0.54 / 0.57 | 0.72 / 0.75 | 1.02 / 1.05 |
| domain-terms | 3 | 0.0% | - | 100.0% | 0.28 / 0.28 | 79.5 | 83.3% | 0.69 / 0.73 | 1.01 / 1.02 | 1.24 / 1.30 |
| noisy-phone | 3 | 5.2% | - | 100.0% | 0.26 / 0.37 | 61.7 | 88.9% | 0.63 / 0.69 | 0.81 / 0.95 | 1.20 / 1.21 |
| interruptions | 3 | 0.0% | 0.0% | 100.0% | 0.34 / 0.37 | 54.9 | 100.0% | 0.56 / 0.57 | 0.78 / 0.85 | 1.11 / 1.22 |
| **all** | 27 | 2.1% | 0.0% | 94.4% | 0.34 / 1.23 | 70.6 | 91.4% | 0.57 / 0.72 | 0.75 / 1.02 | 1.11 / 2.10 |

### gpt-4.1-nano

| Category | Items | WER (non-ko) | CER (ko) | STT term recall | STT s | chrF | Term recall | TTFT s | Translate s | End-to-end s |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: | --- | --- | --- |
| en-ko | 3 | 0.0% | - | 100.0% | 0.27 / 1.12 | 36.7 | 83.3% | 0.55 / 0.81 | 0.73 / 0.87 | 1.00 / 1.98 |
| ko-en | 3 | - | 0.0% | 83.3% | 1.24 / 1.50 | 61.7 | 83.3% | 0.47 / 0.63 | 0.59 / 0.84 | 2.03 / 2.10 |
| ru-en | 3 | 3.0% | - | 100.0% | 0.43 / 0.49 | 94.6 | 100.0% | 0.62 / 0.66 | 0.77 / 0.94 | 1.20 / 1.33 |
| en-ru | 3 | 0.0% | - | 100.0% | 0.34 / 0.59 | 57.2 | 16.7% | 0.76 / 1.17 | 0.88 / 1.19 | 1.22 / 1.78 |
| mixed | 3 | 7.9% | - | 66.7% | 0.34 / 0.36 | 78.2 | 100.0% | 0.70 / 0.71 | 0.90 / 0.98 | 1.16 / 1.31 |
| names-numbers | 3 | 0.0% | - | 100.0% | 0.27 / 0.32 | 81.3 | 100.0% | 0.54 / 0.63 | 0.83 / 0.85 | 1.12 / 1.15 |
| domain-terms | 3 | 0.0% | - | 100.0% | 0.28 / 0.28 | 63.3 | 83.3% | 0.56 / 0.58 | 0.76 / 0.79 | 0.99 / 1.06 |
| noisy-phone | 3 | 5.2% | - | 100.0% | 0.26 / 0.37 | 67.4 | 72.2% | 0.61 / 0.68 | 0.70 / 0.85 | 0.94 / 1.22 |
| interruptions | 3 | 0.0% | 0.0% | 100.0% | 0.34 / 0.37 | 56.3 | 100.0% | 0.54 / 0.60 | 0.74 / 0.84 | 1.06 / 1.21 |
| **all** | 27 | 2.1% | 0.0% | 94.4% | 0.34 / 1.23 | 66.3 | 82.1% | 0.58 / 0.81 | 0.77 / 0.98 | 1.14 / 2.07 |

Code-switch WER by script, pooled over the 3 mixed items (STT is the same for both
models): Cyrillic 0 errors in 40 words (0.0%), Latin 4 errors in 10 words (40.0%).

### What the first run suggests

- **STT on clean synthetic speech is near perfect**, so it cannot separate configurations
  yet. The one visible weakness is code-switching: Russian words were recognised correctly
  but the English words were not (for example "book" became "like", and the English word
  "visa" was written as Russian "виза"). That is the pattern the real dataset needs to
  measure with human voices.
- **Terminology differs between translation models** more than chrF shows. On English to
  Russian the mean term recall was 16.7% for `gpt-4.1-nano` against 66.7% for
  `gpt-4.1-mini`. Both rendered "residence permit" as "разрешение на проживание" instead of
  the standard "вид на жительство" (and `nano` made a gender error, "свою разрешение");
  `nano` also translated "appointment" as "встреча" (a meeting) instead of "приём" or
  "запись". Three items are too few to rank the models, but this is exactly the kind of
  error the dataset is meant to surface.
- **Latency**: STT about 0.3 to 0.5 s per short clip (Korean was slower, about 1.2 s),
  translation first token about 0.55 to 0.6 s, so cascade end-to-end is about 1.1 s at the
  median. This is request time from one machine and excludes TTS; it is not the
  streaming end-of-turn to first-audio metric from the test plan. The p95 values come from
  three samples per category and are not stable.
- chrF is low for English to Korean (33 to 37) mostly because Korean character n-grams are
  rarely identical across valid wordings. Compare models within a direction, not across
  directions.

### Known limits of v1

- Synthetic voices only, one voice per language, no accents, no overlapping speech.
- References are single hand-written translations; correct alternatives are penalised by
  chrF, and term recall depends on the listed alternatives. Names such as
  "Ivanov" or "Seoul Central Clinic" are transliterated in the reference, which a model may
  legitimately keep in Latin (the alternatives in `key_terms` cover some of this).
- Interruption items hold both utterances in one clip, so cascade does not test turn
  detection or cancellation of speech. That needs the live pipeline.
- No TTS or voice-similarity metrics yet (RM-022).

Deterministic tests validate contracts and lifecycle behavior without proving speech
quality. Do not report STT, LLM, or TTS acceptance until configured real providers process
real audio end to end. Keep private recordings out of the repository unless explicitly
approved.
