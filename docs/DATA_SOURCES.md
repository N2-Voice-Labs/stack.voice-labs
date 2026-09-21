# Data Sources

This project combines team-recorded speech data, official immigration information, and existing AI models.

## Code-Switched Speech Dataset

Our main evaluation dataset will be recorded by the team with participants who agree to take part. The first version will focus on English, Russian, and English-Russian code-switching, with both monolingual and mixed-language utterances.

Each recording will have a manually verified reference transcript, language annotations, and useful immigration-related vocabulary. Examples should include natural pauses, corrections, and language switching.

### Access and limitations

The dataset does not exist yet and must be collected and annotated by the team. Participants must consent to project use. Recordings should not contain unnecessary personal or sensitive information.

The first dataset will be relatively small, so results describe our prototype rather than all English-Russian speakers.

## Immigration Information

The prototype will use official information published by the [Korea Immigration Service](https://www.immigration.go.kr/immigration_eng/index) and related government services, including:

- visa information;
- immigration procedures and required documents;
- office and appointment information;
- application forms and frequently requested information.

For the first prototype, we will use a small manually selected and verified knowledge set rather than ingesting the entire website.

### Access and limitations

Official information may change over time. Agent answers must be grounded in the information available to the system and must not be presented as legal advice. We do not currently assume that a public API exists for every immigration service.

## Models and External Components

The project will evaluate existing technologies rather than training every model from scratch. Initial candidates include:

- Qwen3-ASR for multilingual speech recognition;
- Silero VAD for voice activity detection;
- Smart Turn for conversational turn detection;
- multilingual LLMs for response generation;
- multilingual TTS models for speech generation.

External APIs may be used as comparison baselines. Final choices will be based on measured accuracy and latency rather than published benchmarks alone.
