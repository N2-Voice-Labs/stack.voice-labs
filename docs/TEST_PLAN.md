# Test Plan

## Goal

Determine whether the voice agent handles English-Russian code-switched speech accurately and quickly enough for natural conversation. Speech recognition quality and end-to-end latency will be measured separately.

## 1. Speech Recognition Accuracy

Create a manually transcribed test dataset containing English-only, Russian-only, and English-Russian code-switched speech. Use the same evaluation process for every STT model.

Primary metric:

- Word Error Rate (WER)

Additional metrics:

- domain-term accuracy;
- code-switched word accuracy;
- named-entity accuracy.

Compare monolingual WER, code-switched WER, and the difference between them. The initial target is a 15–20% relative reduction in code-switched WER compared with the baseline without significantly reducing monolingual accuracy. Revise the target after collecting the first real dataset.

## 2. Domain Vocabulary

Create utterances containing visa categories, residence documents, appointments, and common immigration terms. Compare normal recognition with vocabulary/context prompting, multilingual decoding, and language-aware processing. Success means fewer important terminology errors without significant degradation on normal speech.

## 3. Code Switching

Test English → Russian, Russian → English, multiple switches in one sentence, and language changes between sentences. Reference transcripts preserve the language actually spoken. The system should retain words from both languages rather than translating, deleting, or replacing them.

## 4. Latency

Measure:

```text
user stops speaking
  → usable STT result
  → LLM first token
  → TTS first audio
  → audio reaches user
```

Track STT latency, LLM time-to-first-token, TTS time-to-first-audio, and end-to-end response latency. The initial prototype goal is median end-of-turn to first-audio latency below approximately two seconds; revise it after measuring the baseline.

## 5. Conversation Tests

Create scripted scenarios for required documents, office hours, appointments, mid-sentence corrections, and mixed-language questions. A test succeeds when the system understands the request and produces a relevant answer grounded in the available knowledge.

## 6. Turn Detection and Interruptions

Once the baseline pipeline is stable, test natural pauses, false end-of-turn detection, user interruption while the agent speaks, and cancellation of generated speech.

## 7. Test Reporting

Record model/provider, configuration, dataset version, WER, code-switch WER, domain-term accuracy, STT latency, LLM latency, TTS latency, end-to-end latency, and hardware/environment for every experiment.

## Initial Success Criteria

- A complete speech-to-AI-to-speech conversation works.
- English-Russian code-switched utterances can be processed without manually selecting a language.
- Mixed-language recognition can be evaluated consistently against reference transcripts.
- Latency can be measured for each major stage.
- Monolingual and mixed-language performance can be compared.
